from app.schemas.stock_candidate import (
    StockCandidateDataQualitySnapshot,
    StockCandidateItem,
    StockCandidateScoreBreakdown,
    StockCandidateScoreRuleResult,
    StockCandidateStrategySignalSnapshot,
)
from app.services.stock_candidate_data_service import StockCandidateDataItem


class StockCandidateScoringService:
    """Score candidate stocks using deterministic quant-style rules.

    This service does not load data and does not call AI.
    It only converts StockCandidateDataItem into StockCandidateItem.
    """

    BASE_SCORE = 50

    DATA_QUALITY_AVAILABLE_SCORE = 5
    DATA_QUALITY_LIMITED_SCORE = -20

    TREND_BULLISH_SCORE = 12
    TREND_BEARISH_SCORE = -12

    MOMENTUM_BULLISH_SCORE = 8
    MOMENTUM_BEARISH_SCORE = -8

    RSI_OVERSOLD_SCORE = 6
    RSI_OVERBOUGHT_SCORE = -8

    MACD_BULLISH_SCORE = 10
    MACD_BEARISH_SCORE = -10

    VOLATILITY_LOW_SCORE = 4
    VOLATILITY_HIGH_RISK_SCORE = -12

    VOLUME_EXPANDING_SCORE = 5
    VOLUME_SHRINKING_SCORE = -5

    STRATEGY_BUY_SCORE = 15
    STRATEGY_HOLD_SCORE = 3
    STRATEGY_OBSERVE_SCORE = 0
    STRATEGY_SELL_SCORE = -18

    MAX_REASON_COUNT = 10
    MAX_RISK_COUNT = 10

    MIN_CANDIDATE_SCORE = 50

    GRADE_PRIORITY = {
        "A": 4,
        "B": 3,
        "C": 2,
        "D": 1,
    }

    SIGNAL_PRIORITY = {
        "buy": 4,
        "hold": 3,
        "observe": 2,
        "sell": 1,
        None: 0,
    }

    def score_candidate(
        self,
        data_item: StockCandidateDataItem,
        *,
        risk_preference: str = "balanced",
        include_score_breakdown: bool = True,
        include_strategy_signal: bool = True,
        include_data_quality: bool = True,
    ) -> StockCandidateItem:
        if self._is_unscorable(data_item):
            return self._build_excluded_candidate(
                data_item=data_item,
                include_data_quality=include_data_quality,
                include_strategy_signal=include_strategy_signal,
            )

        rule_results: list[StockCandidateScoreRuleResult] = []

        data_quality_score = self._score_data_quality(data_item, rule_results)
        trend_score = self._score_trend(data_item, rule_results)
        momentum_score = self._score_momentum(data_item, rule_results)
        rsi_score = self._score_rsi(data_item, rule_results)
        macd_score = self._score_macd(data_item, rule_results)
        volatility_score = self._score_volatility(data_item, rule_results)
        volume_score = self._score_volume(data_item, rule_results)
        strategy_signal_score = self._score_strategy_signal(data_item, rule_results)
        user_preference_score = self._score_user_preference(
            data_item=data_item,
            risk_preference=risk_preference,
            rule_results=rule_results,
        )

        final_score = self._clamp_score(
            self.BASE_SCORE
            + data_quality_score
            + trend_score
            + momentum_score
            + rsi_score
            + macd_score
            + volatility_score
            + volume_score
            + strategy_signal_score
            + user_preference_score
        )

        reasons = self._build_reasons(data_item, rule_results)
        risks = self._build_risks(data_item, rule_results)

        return StockCandidateItem(
            symbol=data_item.symbol,
            market=data_item.market,
            name=data_item.name,
            decision="candidate",
            excluded_reason=None,
            rank=None,
            score=final_score,
            grade=self._grade_from_score(final_score),
            reasons=reasons,
            risks=risks,
            score_breakdown=(
                StockCandidateScoreBreakdown(
                    base_score=self.BASE_SCORE,
                    data_quality_score=data_quality_score,
                    trend_score=trend_score,
                    momentum_score=momentum_score,
                    rsi_score=rsi_score,
                    macd_score=macd_score,
                    volatility_score=volatility_score,
                    volume_score=volume_score,
                    strategy_signal_score=strategy_signal_score,
                    user_preference_score=user_preference_score,
                    final_score=final_score,
                    rule_results=rule_results,
                )
                if include_score_breakdown
                else None
            ),
            data_quality=(
                self._build_data_quality_snapshot(data_item)
                if include_data_quality
                else None
            ),
            strategy_signal=(
                self._build_strategy_signal_snapshot(data_item)
                if include_strategy_signal
                else None
            ),
        )

    def rank_and_filter_candidates(
        self,
        candidates: list[StockCandidateItem],
        *,
        top_n: int,
    ) -> tuple[list[StockCandidateItem], list[StockCandidateItem]]:
        eligible_candidates: list[StockCandidateItem] = []
        excluded_candidates: list[StockCandidateItem] = []

        for candidate in candidates:
            if candidate.decision == "excluded":
                excluded_candidates.append(
                    candidate.model_copy(
                        update={
                            "rank": None,
                        }
                    )
                )
                continue

            if candidate.score < self.MIN_CANDIDATE_SCORE:
                excluded_candidates.append(
                    self._exclude_low_score_candidate(candidate)
                )
                continue

            eligible_candidates.append(candidate)

        sorted_candidates = sorted(
            eligible_candidates,
            key=self._build_candidate_sort_key,
            reverse=True,
        )

        ranked_candidates = [
            candidate.model_copy(
                update={
                    "rank": index + 1,
                }
            )
            for index, candidate in enumerate(sorted_candidates[:top_n])
        ]

        overflow_candidates = [
            self._exclude_overflow_candidate(candidate)
            for candidate in sorted_candidates[top_n:]
        ]

        return ranked_candidates, [*excluded_candidates, *overflow_candidates]

    def _exclude_low_score_candidate(
        self,
        candidate: StockCandidateItem,
    ) -> StockCandidateItem:
        excluded_reason = (
            f"候选评分 {candidate.score} 低于最低候选分数 "
            f"{self.MIN_CANDIDATE_SCORE}，暂不进入候选优先列表。"
        )

        risks = self._limit_text_list(
            [
                excluded_reason,
                *candidate.risks,
            ],
            limit=self.MAX_RISK_COUNT,
        )

        return candidate.model_copy(
            update={
                "decision": "excluded",
                "excluded_reason": excluded_reason,
                "rank": None,
                "risks": risks,
            }
        )

    def _exclude_overflow_candidate(
        self,
        candidate: StockCandidateItem,
    ) -> StockCandidateItem:
        excluded_reason = "候选评分可用，但未进入本次 top_n 候选列表。"

        risks = self._limit_text_list(
            [
                excluded_reason,
                *candidate.risks,
            ],
            limit=self.MAX_RISK_COUNT,
        )

        return candidate.model_copy(
            update={
                "decision": "excluded",
                "excluded_reason": excluded_reason,
                "rank": None,
                "risks": risks,
            }
        )

    def _build_candidate_sort_key(
        self,
        candidate: StockCandidateItem,
    ) -> tuple[int, int, int, str]:
        return (
            candidate.score,
            self.GRADE_PRIORITY.get(candidate.grade, 0),
            self._get_candidate_signal_priority(candidate),
            candidate.symbol,
        )

    def _get_candidate_signal_priority(
        self,
        candidate: StockCandidateItem,
    ) -> int:
        if candidate.strategy_signal is None:
            return 0

        return self.SIGNAL_PRIORITY.get(candidate.strategy_signal.signal, 0)

    def score_candidates(
        self,
        data_items: list[StockCandidateDataItem],
        *,
        risk_preference: str = "balanced",
        include_score_breakdown: bool = True,
        include_strategy_signal: bool = True,
        include_data_quality: bool = True,
    ) -> list[StockCandidateItem]:
        return [
            self.score_candidate(
                data_item,
                risk_preference=risk_preference,
                include_score_breakdown=include_score_breakdown,
                include_strategy_signal=include_strategy_signal,
                include_data_quality=include_data_quality,
            )
            for data_item in data_items
        ]

    def _is_unscorable(
        self,
        data_item: StockCandidateDataItem,
    ) -> bool:
        if data_item.data_quality is None:
            return True

        if data_item.data_quality.is_empty:
            return True

        if data_item.data_quality.errors:
            return True

        if data_item.technical_indicators is None:
            return True

        return False

    def _build_excluded_candidate(
        self,
        *,
        data_item: StockCandidateDataItem,
        include_data_quality: bool,
        include_strategy_signal: bool,
    ) -> StockCandidateItem:
        excluded_reason = self._build_excluded_reason(data_item)

        return StockCandidateItem(
            symbol=data_item.symbol,
            market=data_item.market,
            name=data_item.name,
            decision="excluded",
            excluded_reason=excluded_reason,
            rank=None,
            score=0,
            grade="D",
            reasons=[],
            risks=self._limit_text_list(
                [
                    excluded_reason,
                    *data_item.warnings,
                    *data_item.errors,
                ],
                limit=self.MAX_RISK_COUNT,
            ),
            score_breakdown=None,
            data_quality=(
                self._build_data_quality_snapshot(data_item)
                if include_data_quality
                else None
            ),
            strategy_signal=(
                self._build_strategy_signal_snapshot(data_item)
                if include_strategy_signal
                else None
            ),
        )

    def _build_excluded_reason(
        self,
        data_item: StockCandidateDataItem,
    ) -> str:
        if data_item.data_quality is None:
            return "缺少数据质量报告，无法进行候选评分。"

        if data_item.data_quality.is_empty:
            return "当前没有可用 K 线数据，无法进行候选评分。"

        if data_item.data_quality.errors:
            return "当前 K 线数据存在错误，无法进行候选评分。"

        if data_item.technical_indicators is None:
            return "缺少技术指标结果，无法进行候选评分。"

        return "当前数据不足以完成候选评分。"

    def _score_data_quality(
        self,
        data_item: StockCandidateDataItem,
        rule_results: list[StockCandidateScoreRuleResult],
    ) -> int:
        data_quality = data_item.data_quality
        if data_quality is None:
            score = self.DATA_QUALITY_LIMITED_SCORE
            reason = "缺少数据质量报告，候选评分可信度下降。"
            warnings = ["后续应补充数据质量检查结果。"]
        elif not data_quality.is_enough or data_quality.is_stale:
            score = self.DATA_QUALITY_LIMITED_SCORE
            reason = "K 线数量不足或数据过旧，候选评分需要降级看待。"
            warnings = [*data_quality.warnings, *data_quality.errors]
        else:
            score = self.DATA_QUALITY_AVAILABLE_SCORE
            reason = f"数据质量可用，共 {data_quality.candle_count} 根 K 线。"
            warnings = data_quality.warnings

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="data_quality",
                score_delta=score,
                reason=reason,
                warnings=self._limit_text_list(warnings, limit=5),
            )
        )
        return score

    def _score_trend(
        self,
        data_item: StockCandidateDataItem,
        rule_results: list[StockCandidateScoreRuleResult],
    ) -> int:
        trend = data_item.technical_indicators.summary.moving_average.trend

        if trend == "bullish":
            score = self.TREND_BULLISH_SCORE
            reason = "均线趋势偏多，价格结构对候选评分形成支持。"
            warnings: list[str] = []
        elif trend == "bearish":
            score = self.TREND_BEARISH_SCORE
            reason = "均线趋势偏空，价格结构对候选评分形成压制。"
            warnings = ["趋势偏弱时，不宜只因为低位就提高研究优先级。"]
        else:
            score = 0
            reason = "均线趋势中性，暂不对候选评分做明显调整。"
            warnings = []

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="trend",
                score_delta=score,
                reason=reason,
                warnings=warnings,
            )
        )
        return score

    def _score_momentum(
        self,
        data_item: StockCandidateDataItem,
        rule_results: list[StockCandidateScoreRuleResult],
    ) -> int:
        momentum = data_item.technical_indicators.summary.momentum

        if momentum.direction == "bullish":
            score = self.MOMENTUM_BULLISH_SCORE
            reason = "动量方向偏多，近期价格变化对候选评分形成支持。"
            warnings: list[str] = []
        elif momentum.direction == "bearish":
            score = self.MOMENTUM_BEARISH_SCORE
            reason = "动量方向偏空，近期价格变化显示下行压力。"
            warnings = ["动量偏弱时需要谨慎确认是否仍处于下跌趋势。"]
        else:
            score = 0
            reason = "动量方向中性，暂不对候选评分做明显调整。"
            warnings = []

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="momentum",
                score_delta=score,
                reason=reason,
                warnings=warnings,
            )
        )
        return score

    def _score_rsi(
        self,
        data_item: StockCandidateDataItem,
        rule_results: list[StockCandidateScoreRuleResult],
    ) -> int:
        rsi = data_item.technical_indicators.summary.rsi

        if rsi.status == "oversold":
            score = self.RSI_OVERSOLD_SCORE
            reason = "RSI 处于超卖区域，存在修复观察价值。"
            warnings = ["超卖不等于一定反弹，需要结合趋势和成交量确认。"]
        elif rsi.status == "overbought":
            score = self.RSI_OVERBOUGHT_SCORE
            reason = "RSI 处于超买区域，短期追高风险上升。"
            warnings = ["超买状态下应谨慎对待高分候选。"]
        else:
            score = 0
            reason = "RSI 处于中性区域。"
            warnings = []

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="rsi",
                score_delta=score,
                reason=reason,
                warnings=warnings,
            )
        )
        return score

    def _score_macd(
        self,
        data_item: StockCandidateDataItem,
        rule_results: list[StockCandidateScoreRuleResult],
    ) -> int:
        macd = data_item.technical_indicators.summary.macd

        if macd.signal == "bullish":
            score = self.MACD_BULLISH_SCORE
            reason = "MACD 为多头信号，趋势动能对候选评分形成支持。"
            warnings: list[str] = []
        elif macd.signal == "bearish":
            score = self.MACD_BEARISH_SCORE
            reason = "MACD 为空头信号，趋势动能偏弱。"
            warnings = ["MACD 偏弱时需要谨慎进入候选优先列表。"]
        else:
            score = 0
            reason = "MACD 当前中性。"
            warnings = []

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="macd",
                score_delta=score,
                reason=reason,
                warnings=warnings,
            )
        )
        return score

    def _score_volatility(
        self,
        data_item: StockCandidateDataItem,
        rule_results: list[StockCandidateScoreRuleResult],
    ) -> int:
        volatility = data_item.technical_indicators.summary.volatility

        if volatility.level == "low":
            score = self.VOLATILITY_LOW_SCORE
            reason = "当前波动率较低，价格波动相对可控。"
            warnings: list[str] = []
        elif volatility.level == "high":
            score = self.VOLATILITY_HIGH_RISK_SCORE
            reason = "当前波动率较高，候选风险需要明显扣分。"
            warnings = ["高波动股票不一定不值得研究，但不适合低风险偏好用户。"]
        else:
            score = 0
            reason = "当前波动率中等。"
            warnings = []

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="volatility",
                score_delta=score,
                reason=reason,
                warnings=warnings,
            )
        )
        return score

    def _score_volume(
        self,
        data_item: StockCandidateDataItem,
        rule_results: list[StockCandidateScoreRuleResult],
    ) -> int:
        volume = data_item.technical_indicators.summary.volume_factor

        if volume.status == "expanding":
            score = self.VOLUME_EXPANDING_SCORE
            reason = "成交量处于放量状态，市场参与度提升。"
            warnings: list[str] = []
        elif volume.status == "shrinking":
            score = self.VOLUME_SHRINKING_SCORE
            reason = "成交量处于缩量状态，当前信号确认度不足。"
            warnings = ["缩量状态下的上涨或反弹需要谨慎确认。"]
        else:
            score = 0
            reason = "成交量状态正常。"
            warnings = []

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="volume",
                score_delta=score,
                reason=reason,
                warnings=warnings,
            )
        )
        return score

    def _score_strategy_signal(
        self,
        data_item: StockCandidateDataItem,
        rule_results: list[StockCandidateScoreRuleResult],
    ) -> int:
        strategy_signal = data_item.strategy_signal

        if strategy_signal is None or strategy_signal.status != "available":
            score = 0
            reason = "当前缺少可用策略信号，暂不根据策略信号调整候选评分。"
            warnings = ["缺少策略信号时，候选评分主要依赖技术指标。"]
        elif strategy_signal.signal == "buy":
            score = self.STRATEGY_BUY_SCORE
            reason = "策略信号为 buy，对候选评分形成明显加分。"
            warnings = strategy_signal.risks
        elif strategy_signal.signal == "hold":
            score = self.STRATEGY_HOLD_SCORE
            reason = "策略信号为 hold，对候选评分小幅加分。"
            warnings = strategy_signal.risks
        elif strategy_signal.signal == "observe":
            score = self.STRATEGY_OBSERVE_SCORE
            reason = "策略信号为 observe，当前更适合作为观察对象。"
            warnings = strategy_signal.risks
        elif strategy_signal.signal == "sell":
            score = self.STRATEGY_SELL_SCORE
            reason = "策略信号为 sell，候选评分需要明显扣分。"
            warnings = strategy_signal.risks or ["策略信号偏弱。"]
        else:
            score = 0
            reason = "策略信号暂未给出明确方向。"
            warnings = []

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="strategy_signal",
                score_delta=score,
                reason=reason,
                warnings=self._limit_text_list(warnings, limit=5),
            )
        )
        return score

    def _score_user_preference(
        self,
        *,
        data_item: StockCandidateDataItem,
        risk_preference: str,
        rule_results: list[StockCandidateScoreRuleResult],
    ) -> int:
        normalized_preference = self._normalize_risk_preference(risk_preference)

        if normalized_preference == "conservative":
            score, reason, warnings = self._score_conservative_preference(data_item)
        elif normalized_preference == "aggressive":
            score, reason, warnings = self._score_aggressive_preference(data_item)
        else:
            score = 0
            reason = "用户风险偏好为 balanced，候选评分按默认风险权重处理。"
            warnings = []

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="user_preference",
                score_delta=score,
                reason=reason,
                warnings=self._limit_text_list(warnings, limit=5),
            )
        )
        return score

    def _score_conservative_preference(
        self,
        data_item: StockCandidateDataItem,
    ) -> tuple[int, str, list[str]]:
        volatility_level = self._get_volatility_level(data_item)
        signal = self._get_strategy_signal_action(data_item)

        score = 0
        reasons: list[str] = []
        warnings: list[str] = []

        if volatility_level == "high":
            score -= 10
            reasons.append("保守型用户对高波动股票额外降权。")
            warnings.append("该股票波动率较高，可能不适合保守型风险偏好。")

        if signal == "sell":
            score -= 6
            reasons.append("保守型用户对 sell 策略信号额外谨慎。")
            warnings.append("策略信号偏弱，保守型用户应降低研究优先级。")

        if signal == "buy" and volatility_level != "high":
            score += 2
            reasons.append("策略信号较积极，且波动率未处于高风险状态，适合保守型用户作为观察候选。")

        if not reasons:
            reasons.append("保守型用户偏好下，本股票未触发额外风险调整。")

        return score, " ".join(reasons), warnings

    def _score_aggressive_preference(
        self,
        data_item: StockCandidateDataItem,
    ) -> tuple[int, str, list[str]]:
        volatility_level = self._get_volatility_level(data_item)
        trend = self._get_trend_direction(data_item)
        momentum = self._get_momentum_direction(data_item)
        signal = self._get_strategy_signal_action(data_item)

        score = 0
        reasons: list[str] = []
        warnings: list[str] = []

        if signal == "buy":
            score += 5
            reasons.append("激进型用户对 buy 策略信号给予额外加权。")

        if trend == "bullish" and momentum == "bullish":
            score += 4
            reasons.append("趋势和动量同时偏多，符合激进型用户更关注进攻性的偏好。")

        if volatility_level == "high":
            score -= 3
            reasons.append("虽然用户偏好激进，但高波动仍需要轻微扣分。")
            warnings.append("高波动股票可能带来更大回撤。")

        if signal == "sell":
            score -= 4
            reasons.append("即使是激进型用户，sell 策略信号也需要降低研究优先级。")
            warnings.append("策略信号偏弱时，不应只因为激进偏好而提高候选等级。")

        if not reasons:
            reasons.append("激进型用户偏好下，本股票未触发额外加分或扣分。")

        return score, " ".join(reasons), warnings

    def _normalize_risk_preference(
        self,
        risk_preference: str,
    ) -> str:
        value = str(risk_preference or "balanced").strip().lower()

        if value in {"conservative", "balanced", "aggressive"}:
            return value

        return "balanced"

    def _get_volatility_level(
        self,
        data_item: StockCandidateDataItem,
    ) -> str | None:
        if data_item.technical_indicators is None:
            return None

        return data_item.technical_indicators.summary.volatility.level

    def _get_trend_direction(
        self,
        data_item: StockCandidateDataItem,
    ) -> str | None:
        if data_item.technical_indicators is None:
            return None

        return data_item.technical_indicators.summary.moving_average.trend

    def _get_momentum_direction(
        self,
        data_item: StockCandidateDataItem,
    ) -> str | None:
        if data_item.technical_indicators is None:
            return None

        return data_item.technical_indicators.summary.momentum.direction

    def _get_strategy_signal_action(
        self,
        data_item: StockCandidateDataItem,
    ) -> str | None:
        if data_item.strategy_signal is None:
            return None

        return data_item.strategy_signal.signal

    def _build_reasons(
        self,
        data_item: StockCandidateDataItem,
        rule_results: list[StockCandidateScoreRuleResult],
    ) -> list[str]:
        values = [
            result.reason
            for result in rule_results
            if result.score_delta > 0
        ]

        if data_item.strategy_signal is not None:
            values.extend(data_item.strategy_signal.reasons)

        if not values:
            values = ["当前候选评分未出现明显加分项，建议仅作为观察对象。"]

        return self._limit_text_list(values, limit=self.MAX_REASON_COUNT)

    def _build_risks(
        self,
        data_item: StockCandidateDataItem,
        rule_results: list[StockCandidateScoreRuleResult],
    ) -> list[str]:
        values: list[str] = []

        for result in rule_results:
            values.extend(result.warnings)
            if result.score_delta < 0:
                values.append(result.reason)

        values.extend(data_item.warnings)
        values.extend(data_item.errors)

        if data_item.strategy_signal is not None:
            values.extend(data_item.strategy_signal.risks)

        values.append("候选评分基于历史行情和技术指标，不代表未来一定上涨。")

        return self._limit_text_list(values, limit=self.MAX_RISK_COUNT)

    def _build_data_quality_snapshot(
        self,
        data_item: StockCandidateDataItem,
    ) -> StockCandidateDataQualitySnapshot | None:
        data_quality = data_item.data_quality

        if data_quality is None:
            return None

        return StockCandidateDataQualitySnapshot(
            status="unavailable" if data_quality.is_empty or data_quality.errors else "available",
            candle_count=data_quality.candle_count,
            is_empty=data_quality.is_empty,
            is_enough=data_quality.is_enough,
            is_stale=data_quality.is_stale,
            warnings=self._limit_text_list(data_quality.warnings, limit=10),
            errors=self._limit_text_list(data_quality.errors, limit=10),
        )

    def _build_strategy_signal_snapshot(
        self,
        data_item: StockCandidateDataItem,
    ) -> StockCandidateStrategySignalSnapshot | None:
        strategy_signal = data_item.strategy_signal

        if strategy_signal is None:
            return None

        return StockCandidateStrategySignalSnapshot(
            status=strategy_signal.status,
            signal=strategy_signal.signal,
            strength=strategy_signal.strength,
            score=strategy_signal.score,
            summary=strategy_signal.summary,
        )

    def _grade_from_score(
        self,
        score: int,
    ) -> str:
        if score >= 80:
            return "A"

        if score >= 65:
            return "B"

        if score >= 50:
            return "C"

        return "D"

    def _clamp_score(
        self,
        score: int,
    ) -> int:
        return max(0, min(100, score))

    def _limit_text_list(
        self,
        values: list[str],
        *,
        limit: int,
    ) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for value in values:
            text = str(value).strip()
            if not text or text in seen:
                continue

            seen.add(text)
            result.append(text[:300])

            if len(result) >= limit:
                break

        return result