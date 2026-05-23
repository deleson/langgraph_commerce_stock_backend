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

    TREND_DIRECTION_BULLISH_SCORE = 8
    TREND_DIRECTION_BEARISH_SCORE = -8
    TREND_SHORT_ALIGNMENT_BULLISH_SCORE = 4
    TREND_SHORT_ALIGNMENT_BEARISH_SCORE = -4
    TREND_LONG_CONFIRM_BULLISH_SCORE = 4
    TREND_LONG_CONFIRM_BEARISH_SCORE = -4
    TREND_EMA_CONFIRM_BULLISH_SCORE = 2
    TREND_EMA_CONFIRM_BEARISH_SCORE = -2

    MOMENTUM_DIRECTION_BULLISH_SCORE = 4
    MOMENTUM_DIRECTION_BEARISH_SCORE = -4
    MOMENTUM_SHORT_BULLISH_SCORE = 2
    MOMENTUM_SHORT_BEARISH_SCORE = -2
    MOMENTUM_MEDIUM_BULLISH_SCORE = 3
    MOMENTUM_MEDIUM_BEARISH_SCORE = -3
    MOMENTUM_LONG_BULLISH_SCORE = 5
    MOMENTUM_LONG_BEARISH_SCORE = -5
    MOMENTUM_BULLISH_CONFLUENCE_SCORE = 3
    MOMENTUM_BEARISH_CONFLUENCE_SCORE = -3
    MOMENTUM_SHORT_OVERHEAT_RISK_SCORE = -2

    RSI_EXTREME_OVERSOLD_SCORE = 4
    RSI_OVERSOLD_SCORE = 6
    RSI_NEUTRAL_HEALTHY_SCORE = 2
    RSI_OVERBOUGHT_SCORE = -8
    RSI_EXTREME_OVERBOUGHT_SCORE = -12
    RSI_SHORT_REBOUND_CONFIRM_SCORE = 2
    RSI_SHORT_OVERHEAT_RISK_SCORE = -2
    RSI_MULTI_OVERBOUGHT_RISK_SCORE = -3

    MACD_SIGNAL_BULLISH_SCORE = 8
    MACD_SIGNAL_BEARISH_SCORE = -8
    MACD_HISTOGRAM_BULLISH_SCORE = 3
    MACD_HISTOGRAM_BEARISH_SCORE = -3
    MACD_LINE_BULLISH_SCORE = 3
    MACD_LINE_BEARISH_SCORE = -3
    MACD_ZERO_AXIS_BULLISH_SCORE = 2
    MACD_ZERO_AXIS_BEARISH_SCORE = -2

    RISK_DATA_STALE_SCORE = -6
    RISK_DATA_WARNING_SCORE = -4
    RISK_HIGH_VOLATILITY_SCORE = -6
    RISK_EXTREME_VOLATILITY_SCORE = -10
    RISK_RSI_EXTREME_OVERBOUGHT_SCORE = -4
    RISK_STRATEGY_SELL_SCORE = -6
    RISK_STRONG_SELL_SCORE = -4
    RISK_MULTI_BEARISH_TECHNICAL_SCORE = -5

    EXTREME_ANNUALIZED_VOLATILITY = 0.6
    MIN_RISK_SCORE = -30
    MAX_RISK_SCORE = 0

    VOLATILITY_LOW_SCORE = 4
    VOLATILITY_HIGH_RISK_SCORE = -12

    VOLUME_MILD_EXPANDING_SCORE = 6
    VOLUME_STRONG_EXPANDING_SCORE = 3
    VOLUME_EXTREME_EXPANDING_RISK_SCORE = -3
    VOLUME_MILD_SHRINKING_SCORE = -3
    VOLUME_STRONG_SHRINKING_SCORE = -6

    LIQUIDITY_MISSING_MA20_SCORE = -4
    LIQUIDITY_ZERO_MA20_SCORE = -8
    LIQUIDITY_EXTREME_LOW_VOLUME_SCORE = -6
    LIQUIDITY_EXTREME_HIGH_VOLUME_SCORE = -4

    MILD_VOLUME_EXPANDING_RATIO = 1.2
    STRONG_VOLUME_EXPANDING_RATIO = 2.0
    EXTREME_VOLUME_EXPANDING_RATIO = 3.0
    EXTREME_LIQUIDITY_EXPANDING_RATIO = 4.0
    MILD_VOLUME_SHRINKING_RATIO = 0.8
    STRONG_VOLUME_SHRINKING_RATIO = 0.5
    EXTREME_LOW_VOLUME_RATIO = 0.2

    STRATEGY_BUY_BASE_SCORE = 10
    STRATEGY_HOLD_BASE_SCORE = 2
    STRATEGY_OBSERVE_BASE_SCORE = 0
    STRATEGY_SELL_BASE_SCORE = -12

    STRATEGY_STRONG_BUY_CONFIRM_SCORE = 4
    STRATEGY_MEDIUM_BUY_CONFIRM_SCORE = 2

    STRATEGY_HIGH_SCORE_CONFIRM_SCORE = 3
    STRATEGY_LOW_SCORE_RISK_SCORE = -3

    STRATEGY_HIGH_SCORE_THRESHOLD = 75
    STRATEGY_LOW_SCORE_THRESHOLD = 35
    STRATEGY_NEUTRAL_LOW_THRESHOLD = 45
    STRATEGY_NEUTRAL_HIGH_THRESHOLD = 55

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

    GRADE_EXPLANATIONS = {
        "A": "等级 A：综合条件较强，适合作为本次优先研究候选。",
        "B": "等级 B：综合条件较好，但仍需要结合风险项继续观察。",
        "C": "等级 C：具备一定观察价值，但候选强度偏弱。",
        "D": "等级 D：当前不适合进入候选优先列表。",
    }

    RISK_PREFERENCE_EXPLANATIONS = {
        "conservative": "当前解释已按保守型风险偏好处理，更重视波动率、风险控制和弱信号过滤。",
        "balanced": "当前解释已按均衡型风险偏好处理，综合考虑收益机会与风险暴露。",
        "aggressive": "当前解释已按激进型风险偏好处理，会更关注趋势、动量和进攻性信号，但不会忽略风险。",
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
        liquidity_score = self._score_liquidity(data_item, rule_results)
        strategy_signal_score = self._score_strategy_signal(data_item, rule_results)
        backtest_performance_score = self._score_backtest_performance(
            data_item,
            rule_results,
        )
        risk_score = self._score_risk(data_item, rule_results)
        user_preference_score = self._score_user_preference(
            data_item=data_item,
            risk_preference=risk_preference,
            rule_results=rule_results,
        )

        raw_score = (
                self.BASE_SCORE
                + data_quality_score
                + trend_score
                + momentum_score
                + rsi_score
                + macd_score
                + volatility_score
                + volume_score
                + liquidity_score
                + strategy_signal_score
                + backtest_performance_score
                + risk_score
                + user_preference_score
        )
        final_score = self._clamp_score(raw_score)

        grade = self._grade_from_score(final_score)
        normalized_risk_preference = self._normalize_risk_preference(risk_preference)

        reasons = self._build_reasons(
            data_item=data_item,
            rule_results=rule_results,
            final_score=final_score,
            grade=grade,
            risk_preference=normalized_risk_preference,
        )
        risks = self._build_risks(
            data_item=data_item,
            rule_results=rule_results,
            final_score=final_score,
            grade=grade,
            risk_preference=normalized_risk_preference,
        )

        return StockCandidateItem(
            symbol=data_item.symbol,
            market=data_item.market,
            name=data_item.name,
            decision="candidate",
            excluded_reason=None,
            rank=None,
            score=final_score,
            grade=grade,
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
                    liquidity_score=liquidity_score,
                    strategy_signal_score=strategy_signal_score,
                    backtest_performance_score=backtest_performance_score,
                    risk_score=risk_score,
                    user_preference_score=user_preference_score,
                    raw_score=raw_score,
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
        moving_average = data_item.technical_indicators.summary.moving_average

        score = 0
        reasons: list[str] = []
        warnings: list[str] = []

        if moving_average.trend == "bullish":
            score += self.TREND_DIRECTION_BULLISH_SCORE
            reasons.append("均线趋势方向偏多，价格结构对候选评分形成基础支持。")
        elif moving_average.trend == "bearish":
            score += self.TREND_DIRECTION_BEARISH_SCORE
            reasons.append("均线趋势方向偏空，价格结构对候选评分形成压制。")
            warnings.append("趋势偏弱时，不宜只因为短期反弹或低位状态提高研究优先级。")
        else:
            reasons.append("均线趋势方向中性，趋势方向本身暂不提供明显加分。")

        if self._is_bullish_short_ma_alignment(moving_average):
            score += self.TREND_SHORT_ALIGNMENT_BULLISH_SCORE
            reasons.append("短期均线呈 ma5 > ma10 > ma20 的多头排列。")
        elif self._is_bearish_short_ma_alignment(moving_average):
            score += self.TREND_SHORT_ALIGNMENT_BEARISH_SCORE
            reasons.append("短期均线呈 ma5 < ma10 < ma20 的空头排列。")
            warnings.append("短期均线空头排列说明近期价格结构仍偏弱。")

        if self._is_bullish_long_ma_confirmation(moving_average):
            score += self.TREND_LONG_CONFIRM_BULLISH_SCORE
            reasons.append("ma20 高于 ma60，中期趋势对多头方向形成确认。")
        elif self._is_bearish_long_ma_confirmation(moving_average):
            score += self.TREND_LONG_CONFIRM_BEARISH_SCORE
            reasons.append("ma20 低于 ma60，中期趋势对空头方向形成确认。")
            warnings.append("中期均线偏空时，需要谨慎看待短期技术反弹。")

        if self._is_bullish_ema_confirmation(moving_average):
            score += self.TREND_EMA_CONFIRM_BULLISH_SCORE
            reasons.append("ema12 高于 ema26，EMA 动能对趋势形成小幅确认。")
        elif self._is_bearish_ema_confirmation(moving_average):
            score += self.TREND_EMA_CONFIRM_BEARISH_SCORE
            reasons.append("ema12 低于 ema26，EMA 动能偏弱。")
            warnings.append("EMA 动能偏弱时，趋势修复可能还不充分。")

        if score == 0 and not warnings:
            reasons.append("均线结构没有出现明确多空共振，趋势评分保持中性。")

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="trend",
                score_delta=score,
                reason=" ".join(reasons),
                warnings=self._limit_text_list(warnings, limit=5),
            )
        )
        return score

    def _is_bullish_short_ma_alignment(
            self,
            moving_average,
    ) -> bool:
        return (
                moving_average.ma5 is not None
                and moving_average.ma10 is not None
                and moving_average.ma20 is not None
                and moving_average.ma5 > moving_average.ma10 > moving_average.ma20
        )

    def _is_bearish_short_ma_alignment(
            self,
            moving_average,
    ) -> bool:
        return (
                moving_average.ma5 is not None
                and moving_average.ma10 is not None
                and moving_average.ma20 is not None
                and moving_average.ma5 < moving_average.ma10 < moving_average.ma20
        )

    def _is_bullish_long_ma_confirmation(
            self,
            moving_average,
    ) -> bool:
        return (
                moving_average.ma20 is not None
                and moving_average.ma60 is not None
                and moving_average.ma20 > moving_average.ma60
        )

    def _is_bearish_long_ma_confirmation(
            self,
            moving_average,
    ) -> bool:
        return (
                moving_average.ma20 is not None
                and moving_average.ma60 is not None
                and moving_average.ma20 < moving_average.ma60
        )

    def _is_bullish_ema_confirmation(
            self,
            moving_average,
    ) -> bool:
        return (
                moving_average.ema12 is not None
                and moving_average.ema26 is not None
                and moving_average.ema12 > moving_average.ema26
        )

    def _is_bearish_ema_confirmation(
            self,
            moving_average,
    ) -> bool:
        return (
                moving_average.ema12 is not None
                and moving_average.ema26 is not None
                and moving_average.ema12 < moving_average.ema26
        )

    def _score_momentum(
            self,
            data_item: StockCandidateDataItem,
            rule_results: list[StockCandidateScoreRuleResult],
    ) -> int:
        momentum = data_item.technical_indicators.summary.momentum

        score = 0
        reasons: list[str] = []
        warnings: list[str] = []

        if momentum.direction == "bullish":
            score += self.MOMENTUM_DIRECTION_BULLISH_SCORE
            reasons.append("动量方向偏多，近期价格变化对候选评分形成基础支持。")
        elif momentum.direction == "bearish":
            score += self.MOMENTUM_DIRECTION_BEARISH_SCORE
            reasons.append("动量方向偏空，近期价格变化显示下行压力。")
            warnings.append("动量偏弱时需要谨慎确认是否仍处于下跌趋势。")
        else:
            reasons.append("动量方向中性，方向本身暂不对候选评分做明显调整。")

        score += self._score_one_momentum_value(
            value=momentum.momentum_5,
            bullish_score=self.MOMENTUM_SHORT_BULLISH_SCORE,
            bearish_score=self.MOMENTUM_SHORT_BEARISH_SCORE,
            bullish_reason="5 日动量为正，短期价格变化偏强。",
            bearish_reason="5 日动量为负，短期价格变化偏弱。",
            reasons=reasons,
            warnings=warnings,
        )
        score += self._score_one_momentum_value(
            value=momentum.momentum_10,
            bullish_score=self.MOMENTUM_MEDIUM_BULLISH_SCORE,
            bearish_score=self.MOMENTUM_MEDIUM_BEARISH_SCORE,
            bullish_reason="10 日动量为正，中短期价格变化偏强。",
            bearish_reason="10 日动量为负，中短期价格变化偏弱。",
            reasons=reasons,
            warnings=warnings,
        )
        score += self._score_one_momentum_value(
            value=momentum.momentum_20,
            bullish_score=self.MOMENTUM_LONG_BULLISH_SCORE,
            bearish_score=self.MOMENTUM_LONG_BEARISH_SCORE,
            bullish_reason="20 日动量为正，中期价格变化偏强。",
            bearish_reason="20 日动量为负，中期价格变化偏弱。",
            reasons=reasons,
            warnings=warnings,
        )

        if self._is_all_positive_momentum(momentum):
            score += self.MOMENTUM_BULLISH_CONFLUENCE_SCORE
            reasons.append("5 日、10 日、20 日动量均为正，形成多周期上行动量共振。")
        elif self._is_all_negative_momentum(momentum):
            score += self.MOMENTUM_BEARISH_CONFLUENCE_SCORE
            reasons.append("5 日、10 日、20 日动量均为负，形成多周期下行动量共振。")
            warnings.append("多周期动量同步偏弱时，候选优先级需要降低。")

        if self._has_short_momentum_overheat_risk(momentum):
            score += self.MOMENTUM_SHORT_OVERHEAT_RISK_SCORE
            reasons.append("短期动量明显强于中期动量，已进行轻微降温处理。")
            warnings.append("短期快速拉升但中期动量未确认时，需要防范追高风险。")

        if score == 0 and not warnings:
            reasons.append("动量数据没有给出明确多空优势，动量评分保持中性。")

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="momentum",
                score_delta=score,
                reason=" ".join(reasons),
                warnings=self._limit_text_list(warnings, limit=5),
            )
        )
        return score

    def _score_one_momentum_value(
            self,
            *,
            value: float | None,
            bullish_score: int,
            bearish_score: int,
            bullish_reason: str,
            bearish_reason: str,
            reasons: list[str],
            warnings: list[str],
    ) -> int:
        if value is None:
            return 0

        if value > 0:
            reasons.append(bullish_reason)
            return bullish_score

        if value < 0:
            reasons.append(bearish_reason)
            warnings.append(bearish_reason)
            return bearish_score

        return 0

    def _is_all_positive_momentum(
            self,
            momentum,
    ) -> bool:
        values = [
            momentum.momentum_5,
            momentum.momentum_10,
            momentum.momentum_20,
        ]
        return all(value is not None and value > 0 for value in values)

    def _is_all_negative_momentum(
            self,
            momentum,
    ) -> bool:
        values = [
            momentum.momentum_5,
            momentum.momentum_10,
            momentum.momentum_20,
        ]
        return all(value is not None and value < 0 for value in values)

    def _has_short_momentum_overheat_risk(
            self,
            momentum,
    ) -> bool:
        if momentum.momentum_5 is None or momentum.momentum_20 is None:
            return False

        return momentum.momentum_5 > 0 and momentum.momentum_20 <= 0

    def _score_rsi(
            self,
            data_item: StockCandidateDataItem,
            rule_results: list[StockCandidateScoreRuleResult],
    ) -> int:
        rsi = data_item.technical_indicators.summary.rsi
        primary_rsi = self._select_candidate_primary_rsi(rsi)

        score = 0
        reasons: list[str] = []
        warnings: list[str] = []

        if primary_rsi is None:
            reasons.append("缺少可用 RSI 数值，RSI 评分保持中性。")
        elif primary_rsi <= 20:
            score += self.RSI_EXTREME_OVERSOLD_SCORE
            reasons.append(f"主要 RSI 为 {primary_rsi:.2f}，处于极端超卖区域，存在修复观察价值。")
            warnings.append("极端超卖可能来自持续下跌，不应直接等同于买入机会。")
        elif primary_rsi <= 30:
            score += self.RSI_OVERSOLD_SCORE
            reasons.append(f"主要 RSI 为 {primary_rsi:.2f}，处于超卖区域，存在修复观察价值。")
            warnings.append("超卖不等于一定反弹，需要结合趋势和成交量确认。")
        elif primary_rsi >= 80:
            score += self.RSI_EXTREME_OVERBOUGHT_SCORE
            reasons.append(f"主要 RSI 为 {primary_rsi:.2f}，处于极端超买区域，追高风险较高。")
            warnings.append("极端超买状态下，短期回撤风险可能上升。")
        elif primary_rsi >= 70:
            score += self.RSI_OVERBOUGHT_SCORE
            reasons.append(f"主要 RSI 为 {primary_rsi:.2f}，处于超买区域，短期追高风险上升。")
            warnings.append("超买状态下应谨慎对待高分候选。")
        elif 45 <= primary_rsi <= 60:
            score += self.RSI_NEUTRAL_HEALTHY_SCORE
            reasons.append(f"主要 RSI 为 {primary_rsi:.2f}，处于相对健康的中性区间。")
        else:
            reasons.append(f"主要 RSI 为 {primary_rsi:.2f}，暂不触发明显加分或扣分。")

        if self._has_rsi_short_rebound_confirmation(rsi):
            score += self.RSI_SHORT_REBOUND_CONFIRM_SCORE
            reasons.append("rsi6 高于 rsi12，短期 RSI 有修复迹象。")

        if self._has_rsi_short_overheat_risk(rsi):
            score += self.RSI_SHORT_OVERHEAT_RISK_SCORE
            reasons.append("rsi6 已进入超买，但 rsi12 尚未确认，已进行轻微降温处理。")
            warnings.append("短期 RSI 过热但中期未确认时，需要防范追高风险。")

        if self._has_rsi_multi_period_overbought_risk(rsi):
            score += self.RSI_MULTI_OVERBOUGHT_RISK_SCORE
            reasons.append("rsi6 / rsi12 / rsi24 均处于超买区域，多周期超买风险上升。")
            warnings.append("多周期 RSI 同时超买时，候选评分需要更谨慎。")

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="rsi",
                score_delta=score,
                reason=" ".join(reasons),
                warnings=self._limit_text_list(warnings, limit=5),
            )
        )
        return score

    def _select_candidate_primary_rsi(
            self,
            rsi,
    ) -> float | None:
        for value in (rsi.rsi12, rsi.rsi6, rsi.rsi24):
            if value is not None:
                return value

        return None

    def _has_rsi_short_rebound_confirmation(
            self,
            rsi,
    ) -> bool:
        return (
                rsi.rsi6 is not None
                and rsi.rsi12 is not None
                and rsi.rsi6 > rsi.rsi12
                and rsi.rsi12 <= 60
        )

    def _has_rsi_short_overheat_risk(
            self,
            rsi,
    ) -> bool:
        return (
                rsi.rsi6 is not None
                and rsi.rsi12 is not None
                and rsi.rsi6 >= 70
                and rsi.rsi12 < 70
        )

    def _has_rsi_multi_period_overbought_risk(
            self,
            rsi,
    ) -> bool:
        values = [rsi.rsi6, rsi.rsi12, rsi.rsi24]
        return all(value is not None and value >= 70 for value in values)

    def _score_macd(
            self,
            data_item: StockCandidateDataItem,
            rule_results: list[StockCandidateScoreRuleResult],
    ) -> int:
        macd = data_item.technical_indicators.summary.macd

        score = 0
        reasons: list[str] = []
        warnings: list[str] = []

        if macd.signal == "bullish":
            score += self.MACD_SIGNAL_BULLISH_SCORE
            reasons.append("MACD 信号偏多，趋势动能对候选评分形成基础支持。")
        elif macd.signal == "bearish":
            score += self.MACD_SIGNAL_BEARISH_SCORE
            reasons.append("MACD 信号偏空，趋势动能偏弱。")
            warnings.append("MACD 偏弱时需要谨慎进入候选优先列表。")
        else:
            reasons.append("MACD 信号中性，方向本身暂不对候选评分做明显调整。")

        if self._has_macd_bullish_histogram(macd):
            score += self.MACD_HISTOGRAM_BULLISH_SCORE
            reasons.append("MACD histogram 大于 0，柱体对多头动能形成确认。")
        elif self._has_macd_bearish_histogram(macd):
            score += self.MACD_HISTOGRAM_BEARISH_SCORE
            reasons.append("MACD histogram 小于 0，柱体显示空头动能。")
            warnings.append("MACD 柱体偏弱时，趋势修复可能还不充分。")

        if self._has_macd_bullish_line_confirmation(macd):
            score += self.MACD_LINE_BULLISH_SCORE
            reasons.append("MACD DIF 高于 DEA，快线对慢线形成多头确认。")
        elif self._has_macd_bearish_line_confirmation(macd):
            score += self.MACD_LINE_BEARISH_SCORE
            reasons.append("MACD DIF 低于 DEA，快线对慢线形成空头确认。")
            warnings.append("DIF 低于 DEA 时，动能结构偏弱。")

        if self._has_macd_bullish_zero_axis_confirmation(macd):
            score += self.MACD_ZERO_AXIS_BULLISH_SCORE
            reasons.append("MACD DIF 和 DEA 均位于 0 轴上方，多头趋势质量更好。")
        elif self._has_macd_bearish_zero_axis_confirmation(macd):
            score += self.MACD_ZERO_AXIS_BEARISH_SCORE
            reasons.append("MACD DIF 和 DEA 均位于 0 轴下方，弱势特征更明显。")
            warnings.append("MACD 位于 0 轴下方时，即使短期反弹也需要谨慎确认。")

        if score == 0 and not warnings:
            reasons.append("MACD 数据没有给出明确多空优势，MACD 评分保持中性。")

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="macd",
                score_delta=score,
                reason=" ".join(reasons),
                warnings=self._limit_text_list(warnings, limit=5),
            )
        )
        return score

    def _has_macd_bullish_histogram(
            self,
            macd,
    ) -> bool:
        return macd.histogram is not None and macd.histogram > 0

    def _has_macd_bearish_histogram(
            self,
            macd,
    ) -> bool:
        return macd.histogram is not None and macd.histogram < 0

    def _has_macd_bullish_line_confirmation(
            self,
            macd,
    ) -> bool:
        return (
                macd.dif is not None
                and macd.dea is not None
                and macd.dif > macd.dea
        )

    def _has_macd_bearish_line_confirmation(
            self,
            macd,
    ) -> bool:
        return (
                macd.dif is not None
                and macd.dea is not None
                and macd.dif < macd.dea
        )

    def _has_macd_bullish_zero_axis_confirmation(
            self,
            macd,
    ) -> bool:
        return (
                macd.dif is not None
                and macd.dea is not None
                and macd.dif > 0
                and macd.dea > 0
        )

    def _has_macd_bearish_zero_axis_confirmation(
            self,
            macd,
    ) -> bool:
        return (
                macd.dif is not None
                and macd.dea is not None
                and macd.dif < 0
                and macd.dea < 0
        )

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
        volume_ratio = volume.volume_ratio

        score = 0
        reasons: list[str] = []
        warnings: list[str] = []

        if volume_ratio is None:
            reasons.append("缺少 volume_ratio，成交量评分保持中性。")
        elif volume_ratio >= self.EXTREME_VOLUME_EXPANDING_RATIO:
            score += self.VOLUME_EXTREME_EXPANDING_RISK_SCORE
            reasons.append(f"volume_ratio 为 {volume_ratio:.2f}，属于异常放量，已进行风险降温。")
            warnings.append("异常放量不一定代表健康上涨，可能来自短期冲高或资金异动。")
        elif volume_ratio >= self.STRONG_VOLUME_EXPANDING_RATIO:
            score += self.VOLUME_STRONG_EXPANDING_SCORE
            reasons.append(f"volume_ratio 为 {volume_ratio:.2f}，属于明显放量，市场参与度提升。")
            warnings.append("明显放量需要结合价格位置和趋势确认，避免追高。")
        elif volume_ratio >= self.MILD_VOLUME_EXPANDING_RATIO:
            score += self.VOLUME_MILD_EXPANDING_SCORE
            reasons.append(f"volume_ratio 为 {volume_ratio:.2f}，属于温和放量，对候选评分形成支持。")
        elif volume_ratio <= self.STRONG_VOLUME_SHRINKING_RATIO:
            score += self.VOLUME_STRONG_SHRINKING_SCORE
            reasons.append(f"volume_ratio 为 {volume_ratio:.2f}，属于明显缩量，信号确认度不足。")
            warnings.append("明显缩量时，价格信号的可靠性需要降低看待。")
        elif volume_ratio < self.MILD_VOLUME_SHRINKING_RATIO:
            score += self.VOLUME_MILD_SHRINKING_SCORE
            reasons.append(f"volume_ratio 为 {volume_ratio:.2f}，属于轻微缩量，市场参与度略弱。")
            warnings.append("轻微缩量不一定是风险，但会降低信号确认度。")
        else:
            reasons.append(f"volume_ratio 为 {volume_ratio:.2f}，成交量处于相对正常区间。")

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="volume",
                score_delta=score,
                reason=" ".join(reasons),
                warnings=self._limit_text_list(warnings, limit=5),
            )
        )
        return score

    def _score_liquidity(
            self,
            data_item: StockCandidateDataItem,
            rule_results: list[StockCandidateScoreRuleResult],
    ) -> int:
        volume = data_item.technical_indicators.summary.volume_factor

        score = 0
        reasons: list[str] = []
        warnings: list[str] = []

        if volume.volume_ma20 is None:
            score += self.LIQUIDITY_MISSING_MA20_SCORE
            reasons.append("缺少 20 日平均成交量，流动性判断依据不足。")
            warnings.append("缺少 volume_ma20 时，成交量和流动性评分可信度下降。")
        elif volume.volume_ma20 == 0:
            score += self.LIQUIDITY_ZERO_MA20_SCORE
            reasons.append("20 日平均成交量为 0，流动性存在明显异常。")
            warnings.append("volume_ma20 为 0 时，候选股票可能缺乏有效成交。")

        if volume.volume_ratio is not None:
            if volume.volume_ratio <= self.EXTREME_LOW_VOLUME_RATIO:
                score += self.LIQUIDITY_EXTREME_LOW_VOLUME_SCORE
                reasons.append(f"volume_ratio 为 {volume.volume_ratio:.2f}，成交活跃度极低。")
                warnings.append("极端低量环境下，价格信号可能缺乏足够成交确认。")
            elif volume.volume_ratio >= self.EXTREME_LIQUIDITY_EXPANDING_RATIO:
                score += self.LIQUIDITY_EXTREME_HIGH_VOLUME_SCORE
                reasons.append(f"volume_ratio 为 {volume.volume_ratio:.2f}，出现极端放量。")
                warnings.append("极端放量可能代表事件冲击或短期资金异动，需要谨慎确认。")

        if score == 0:
            reasons.append("未触发额外流动性风险，liquidity_score 保持中性。")

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="liquidity",
                score_delta=score,
                reason=" ".join(reasons),
                warnings=self._limit_text_list(warnings, limit=5),
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

            rule_results.append(
                StockCandidateScoreRuleResult(
                    dimension="strategy_signal",
                    score=score,
                    reason=reason,
                    warnings=warnings,
                )
            )
            return score

        score = 0
        reasons: list[str] = []
        warnings: list[str] = []

        if strategy_signal.signal == "buy":
            score += self.STRATEGY_BUY_BASE_SCORE
            reasons.append("策略信号为 buy，说明多项技术规则合成后偏向买入观察。")
        elif strategy_signal.signal == "hold":
            score += self.STRATEGY_HOLD_BASE_SCORE
            reasons.append("策略信号为 hold，说明当前更适合持有或继续观察。")
        elif strategy_signal.signal == "observe":
            score += self.STRATEGY_OBSERVE_BASE_SCORE
            reasons.append("策略信号为 observe，说明当前方向不够明确，暂不明显加分。")
            warnings.append("策略信号处于观察状态，候选结论需要结合其他指标确认。")
        elif strategy_signal.signal == "sell":
            score += self.STRATEGY_SELL_BASE_SCORE
            reasons.append("策略信号为 sell，说明规则系统对当前股票偏谨慎。")
            warnings.append("策略信号偏弱，候选评分需要扣分。")
        else:
            reasons.append("策略信号暂未给出明确方向。")

        strength_score, strength_reasons, strength_warnings = self._score_strategy_strength(
            signal=strategy_signal.signal,
            strength=strategy_signal.strength,
        )
        score += strength_score
        reasons.extend(strength_reasons)
        warnings.extend(strength_warnings)

        numeric_score, numeric_reasons, numeric_warnings = self._score_strategy_numeric_score(
            signal=strategy_signal.signal,
            strategy_score=strategy_signal.score,
        )
        score += numeric_score
        reasons.extend(numeric_reasons)
        warnings.extend(numeric_warnings)

        if strategy_signal.risks:
            warnings.extend(strategy_signal.risks[:3])

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="strategy_signal",
                score=score,
                reason="；".join(reasons),
                warnings=warnings,
            )
        )
        return score

    def _score_backtest_performance(
            self,
            data_item: StockCandidateDataItem,
            rule_results: list[StockCandidateScoreRuleResult],
    ) -> int:
        score = 0

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="backtest_performance",
                score_delta=score,
                reason=(
                    "回测表现评分维度已预留；当前候选评分接口默认不批量执行历史回测，"
                    "因此本维度暂不加分也不扣分。"
                ),
                warnings=[
                    "历史回测需要明确开始日期、结束日期和回测规则，当前候选评分暂不默认触发。",
                    "后续可在请求参数中显式开启回测表现评分，再接入 BacktestQueryService。",
                ],
            )
        )

        return score

    def _score_strategy_strength(
            self,
            *,
            signal: str | None,
            strength: str | None,
    ) -> tuple[int, list[str], list[str]]:
        if strength == "strong" and signal == "buy":
            return (
                self.STRATEGY_STRONG_BUY_CONFIRM_SCORE,
                ["策略信号强度为 strong，buy 信号确认度较高。"],
                [],
            )

        if strength == "medium" and signal == "buy":
            return (
                self.STRATEGY_MEDIUM_BUY_CONFIRM_SCORE,
                ["策略信号强度为 medium，buy 信号有一定确认度。"],
                [],
            )

        if strength == "weak" and signal == "buy":
            return (
                0,
                ["策略信号强度为 weak，buy 信号暂不额外加分。"],
                ["buy 信号强度较弱，需要结合趋势、动量和风险评分确认。"],
            )

        if signal == "sell" and strength in {"medium", "strong"}:
            return (
                0,
                ["sell 信号强度较高，额外风险交由 risk_score 统一处理。"],
                ["策略信号偏空强度较高，综合风险评分会进一步反映该风险。"],
            )

        return (0, [], [])

    def _score_strategy_numeric_score(
            self,
            *,
            signal: str | None,
            strategy_score: int | None,
    ) -> tuple[int, list[str], list[str]]:
        if strategy_score is None:
            return (
                0,
                [],
                ["策略信号缺少原始分数，无法进行分数确认。"],
            )

        if signal == "buy" and strategy_score >= self.STRATEGY_HIGH_SCORE_THRESHOLD:
            return (
                self.STRATEGY_HIGH_SCORE_CONFIRM_SCORE,
                [f"策略信号原始分为 {strategy_score}，高于强确认阈值。"],
                [],
            )

        if signal == "sell" and strategy_score <= self.STRATEGY_LOW_SCORE_THRESHOLD:
            return (
                self.STRATEGY_LOW_SCORE_RISK_SCORE,
                [f"策略信号原始分为 {strategy_score}，低于偏弱阈值。"],
                ["策略信号原始分偏低，候选评分需要谨慎。"],
            )

        if (
                self.STRATEGY_NEUTRAL_LOW_THRESHOLD
                <= strategy_score
                <= self.STRATEGY_NEUTRAL_HIGH_THRESHOLD
        ):
            return (
                0,
                [f"策略信号原始分为 {strategy_score}，接近中性区间。"],
                ["策略信号分数接近中性，方向确认度有限。"],
            )

        return (0, [], [])

    def _score_risk(
            self,
            data_item: StockCandidateDataItem,
            rule_results: list[StockCandidateScoreRuleResult],
    ) -> int:
        score = 0
        reasons: list[str] = []
        warnings: list[str] = []

        data_quality = data_item.data_quality
        technical_indicators = data_item.technical_indicators
        strategy_signal = data_item.strategy_signal

        if data_quality is not None:
            if data_quality.is_stale:
                score += self.RISK_DATA_STALE_SCORE
                reasons.append("行情数据存在过旧风险，候选评分需要额外降温。")
                warnings.append("数据过旧会降低技术指标和策略信号的参考价值。")

            if data_quality.warnings:
                score += self.RISK_DATA_WARNING_SCORE
                reasons.append("数据质量报告存在 warning，候选评分需要额外谨慎。")
                warnings.extend(data_quality.warnings)

        if technical_indicators is not None:
            volatility = technical_indicators.summary.volatility
            rsi = technical_indicators.summary.rsi

            if (
                    volatility.annualized_volatility is not None
                    and volatility.annualized_volatility >= self.EXTREME_ANNUALIZED_VOLATILITY
            ):
                score += self.RISK_EXTREME_VOLATILITY_SCORE
                reasons.append(
                    f"年化波动率为 {volatility.annualized_volatility:.2%}，处于极端高波动区域。"
                )
                warnings.append("极端高波动股票可能带来更大回撤，不适合作为低风险候选。")
            elif volatility.level == "high":
                score += self.RISK_HIGH_VOLATILITY_SCORE
                reasons.append("波动率等级为 high，候选风险需要额外扣分。")
                warnings.append("高波动股票需要结合仓位管理和风险承受能力谨慎研究。")

            primary_rsi = self._select_candidate_primary_rsi(rsi)
            if primary_rsi is not None and primary_rsi >= 80:
                score += self.RISK_RSI_EXTREME_OVERBOUGHT_SCORE
                reasons.append(f"主要 RSI 为 {primary_rsi:.2f}，极端超买带来额外追高风险。")
                warnings.append("极端超买不代表一定下跌，但短期回撤风险可能上升。")

            if self._has_multi_bearish_technical_risk(data_item):
                score += self.RISK_MULTI_BEARISH_TECHNICAL_SCORE
                reasons.append("趋势、动量或 MACD 中多个技术项偏弱，形成综合技术风险。")
                warnings.append("多个技术项同时偏弱时，不宜只看单一加分项提高候选优先级。")

        if strategy_signal is not None and strategy_signal.status == "available":
            if strategy_signal.signal == "sell":
                score += self.RISK_STRATEGY_SELL_SCORE
                reasons.append("策略信号为 sell，综合风险评分额外扣分。")
                warnings.extend(strategy_signal.risks or ["策略信号偏弱。"])

                if strategy_signal.strength == "strong":
                    score += self.RISK_STRONG_SELL_SCORE
                    reasons.append("策略信号强度为 strong，sell 风险进一步提高。")
                    warnings.append("强 sell 信号下，候选研究优先级需要明显降低。")

        score = max(self.MIN_RISK_SCORE, min(self.MAX_RISK_SCORE, score))

        if score == 0:
            reasons.append("未触发额外综合风险扣分，risk_score 保持中性。")

        rule_results.append(
            StockCandidateScoreRuleResult(
                dimension="risk",
                score_delta=score,
                reason=" ".join(reasons),
                warnings=self._limit_text_list(warnings, limit=5),
            )
        )
        return score

    def _has_multi_bearish_technical_risk(
            self,
            data_item: StockCandidateDataItem,
    ) -> bool:
        technical_indicators = data_item.technical_indicators
        if technical_indicators is None:
            return False

        summary = technical_indicators.summary
        bearish_count = 0

        if summary.moving_average.trend == "bearish":
            bearish_count += 1

        if summary.momentum.direction == "bearish":
            bearish_count += 1

        if summary.macd.signal == "bearish":
            bearish_count += 1

        return bearish_count >= 2

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
        *,
        data_item: StockCandidateDataItem,
        rule_results: list[StockCandidateScoreRuleResult],
        final_score: int,
        grade: str,
        risk_preference: str,
    ) -> list[str]:
        values = [
            self._build_grade_explanation(
                final_score=final_score,
                grade=grade,
            ),
            self.RISK_PREFERENCE_EXPLANATIONS.get(
                risk_preference,
                self.RISK_PREFERENCE_EXPLANATIONS["balanced"],
            ),
        ]

        values.extend(
            result.reason
            for result in rule_results
            if result.score_delta > 0
        )

        if data_item.strategy_signal is not None:
            values.extend(data_item.strategy_signal.reasons)

        if not values:
            values = ["当前候选评分未出现明显加分项，建议仅作为观察对象。"]

        return self._limit_text_list(values, limit=self.MAX_REASON_COUNT)

    def _build_risks(
        self,
        *,
        data_item: StockCandidateDataItem,
        rule_results: list[StockCandidateScoreRuleResult],
        final_score: int,
        grade: str,
        risk_preference: str,
    ) -> list[str]:
        values: list[str] = [
            self._build_score_risk_boundary(
                final_score=final_score,
                grade=grade,
            )
        ]

        for result in rule_results:
            values.extend(result.warnings)
            if result.score_delta < 0:
                values.append(result.reason)

        values.extend(data_item.warnings)
        values.extend(data_item.errors)

        if data_item.strategy_signal is not None:
            values.extend(data_item.strategy_signal.risks)

        if risk_preference == "aggressive":
            values.append("激进型偏好可能提高进攻性候选的优先级，但不代表风险降低。")
        elif risk_preference == "conservative":
            values.append("保守型偏好会降低高波动或弱信号股票优先级，但仍不能完全避免亏损。")

        values.append("候选评分基于历史行情和技术指标，不代表未来一定上涨。")
        values.append("本结果只作为研究线索，不构成投资建议，也不承诺未来收益。")

        return self._limit_text_list(values, limit=self.MAX_RISK_COUNT)

    def _build_grade_explanation(
        self,
        *,
        final_score: int,
        grade: str,
    ) -> str:
        grade_text = self.GRADE_EXPLANATIONS.get(
            grade,
            "当前等级无法识别，建议谨慎参考。",
        )
        return f"综合评分 {final_score} 分，{grade_text}"

    def _build_score_risk_boundary(
        self,
        *,
        final_score: int,
        grade: str,
    ) -> str:
        if grade == "A":
            return "即使候选等级为 A，也只是历史数据和规则评分较强，不代表未来一定上涨。"

        if grade == "B":
            return "等级 B 仍需要结合行情环境、仓位管理和风险承受能力继续确认。"

        if grade == "C":
            return "等级 C 的候选强度有限，更适合观察，不适合直接当作买入依据。"

        return f"当前综合评分为 {final_score} 分，候选强度偏弱，需要谨慎看待。"

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