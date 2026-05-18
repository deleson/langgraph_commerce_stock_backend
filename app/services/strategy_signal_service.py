from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.strategy_signal import (
    StrategySignalInputSnapshot,
    StrategySignalResponse,
    StrategyRuleResult,
)
from app.schemas.technical_indicator import (
    MacdSnapshot,
    MovingAverageSnapshot,
    RsiSnapshot,
    TechnicalIndicatorResponse,
)

class StrategySignalService:
    """Generate strategy signals from technical indicators.

    This service starts with a neutral baseline signal.
    Specific rules will be added step by step in later stage 5.8 tasks.
    """

    BASE_SCORE = 50
    MAX_REASON_COUNT = 10
    MAX_RISK_COUNT = 10
    QUALITY_LIMITED_SCORE = 40
    UNAVAILABLE_SCORE = 0
    TREND_BULLISH_SCORE = 18
    TREND_BEARISH_SCORE = -18
    TREND_CONFIRM_SCORE = 5
    RSI_OVERSOLD_SCORE = 10
    RSI_OVERBOUGHT_SCORE = -12
    RSI_LOW_CONFIRM_SCORE = 5
    RSI_HIGH_RISK_SCORE = -5
    MACD_BULLISH_SCORE = 18
    MACD_BEARISH_SCORE = -18
    MACD_HISTOGRAM_CONFIRM_SCORE = 4

    def generate_signal(
        self,
        *,
        technical_indicators: TechnicalIndicatorResponse,
        data_quality: MarketDataQualityReport | None = None,
        include_detail: bool = True,
    ) -> StrategySignalResponse:
        """Build a strategy signal response.

        Stage 5.8 step 5 adds the data quality gate.
        Indicator-specific rules will be added in later steps.
        """

        quality_rule = self._build_data_quality_rule(data_quality)
        reasons = self._build_initial_reasons(technical_indicators)
        risks = self._build_initial_risks(
            technical_indicators=technical_indicators,
            data_quality=data_quality,
        )

        if quality_rule is not None:
            reasons.append(quality_rule.reason)
            risks.extend(quality_rule.warnings)

        if self._is_data_unavailable(data_quality):
            return StrategySignalResponse(
                symbol=technical_indicators.symbol,
                market=technical_indicators.market,
                timeframe=technical_indicators.timeframe,
                adjust_type=technical_indicators.adjust_type,
                source=technical_indicators.source,
                status="unavailable",
                signal=None,
                strength=None,
                score=self.UNAVAILABLE_SCORE,
                summary=self._build_unavailable_summary(
                    technical_indicators=technical_indicators,
                    data_quality=data_quality,
                ),
                reasons=self._limit_text_list(reasons, limit=self.MAX_REASON_COUNT),
                risks=self._limit_text_list(risks, limit=self.MAX_RISK_COUNT),
                rule_results=self._build_rule_results(
                    quality_rule=quality_rule,
                    include_detail=include_detail,
                ),
                input_snapshot=self._build_input_snapshot(
                    technical_indicators=technical_indicators,
                    data_quality=data_quality,
                    include_detail=include_detail,
                ),
            )

        if self._is_data_quality_limited(data_quality):
            return StrategySignalResponse(
                symbol=technical_indicators.symbol,
                market=technical_indicators.market,
                timeframe=technical_indicators.timeframe,
                adjust_type=technical_indicators.adjust_type,
                source=technical_indicators.source,
                status="available",
                signal="observe",
                strength="weak",
                score=self.QUALITY_LIMITED_SCORE,
                summary=self._build_quality_limited_summary(
                    technical_indicators=technical_indicators,
                    data_quality=data_quality,
                ),
                reasons=self._limit_text_list(reasons, limit=self.MAX_REASON_COUNT),
                risks=self._limit_text_list(risks, limit=self.MAX_RISK_COUNT),
                rule_results=self._build_rule_results(
                    quality_rule=quality_rule,
                    include_detail=include_detail,
                ),
                input_snapshot=self._build_input_snapshot(
                    technical_indicators=technical_indicators,
                    data_quality=data_quality,
                    include_detail=include_detail,
                ),
            )

        trend_rule = self._build_trend_rule(
            technical_indicators.summary.moving_average
        )
        rsi_rule = self._build_rsi_rule(technical_indicators.summary.rsi)
        macd_rule = self._build_macd_rule(technical_indicators.summary.macd)

        score = self._clamp_score(
            self.BASE_SCORE
            + trend_rule.score_delta
            + rsi_rule.score_delta
            + macd_rule.score_delta
        )
        signal = self._signal_from_score(score)
        strength = self._strength_from_score(score)

        reasons.append(trend_rule.reason)
        reasons.append(rsi_rule.reason)
        reasons.append(macd_rule.reason)
        risks.extend(trend_rule.warnings)
        risks.extend(rsi_rule.warnings)
        risks.extend(macd_rule.warnings)

        return StrategySignalResponse(
            symbol=technical_indicators.symbol,
            market=technical_indicators.market,
            timeframe=technical_indicators.timeframe,
            adjust_type=technical_indicators.adjust_type,
            source=technical_indicators.source,
            status="available",
            signal=signal,
            strength=strength,
            score=score,
            summary=self._build_baseline_summary(technical_indicators),
            reasons=self._limit_text_list(reasons, limit=self.MAX_REASON_COUNT),
            risks=self._limit_text_list(risks, limit=self.MAX_RISK_COUNT),
            rule_results=self._build_rule_results(
                quality_rule=quality_rule,
                trend_rule=trend_rule,
                rsi_rule=rsi_rule,
                macd_rule=macd_rule,
                include_detail=include_detail,
            ),
            input_snapshot=self._build_input_snapshot(
                technical_indicators=technical_indicators,
                data_quality=data_quality,
                include_detail=include_detail,
            ),
        )

    def _is_data_unavailable(
        self,
        data_quality: MarketDataQualityReport | None,
    ) -> bool:
        if data_quality is None:
            return False

        return data_quality.is_empty or bool(data_quality.errors)

    def _is_data_quality_limited(
        self,
        data_quality: MarketDataQualityReport | None,
    ) -> bool:
        if data_quality is None:
            return False

        return (not data_quality.is_enough) or data_quality.is_stale

    def _build_data_quality_rule(
        self,
        data_quality: MarketDataQualityReport | None,
    ) -> StrategyRuleResult | None:
        if data_quality is None:
            return StrategyRuleResult(
                rule_name="data_quality",
                direction="neutral",
                score_delta=0,
                reason="当前未传入数据质量报告，暂不根据数据质量调整策略信号。",
                warnings=["缺少数据质量报告，策略信号可信度需要谨慎看待。"],
            )

        if data_quality.is_empty:
            return StrategyRuleResult(
                rule_name="data_quality",
                direction="invalid",
                score_delta=-100,
                reason="当前没有可用 K 线数据，无法生成策略信号。",
                warnings=data_quality.errors or ["K 线数据为空。"],
            )

        if data_quality.errors:
            return StrategyRuleResult(
                rule_name="data_quality",
                direction="invalid",
                score_delta=-100,
                reason="当前 K 线数据存在硬错误，无法生成策略信号。",
                warnings=data_quality.errors,
            )

        if not data_quality.is_enough:
            return StrategyRuleResult(
                rule_name="data_quality",
                direction="risk",
                score_delta=-10,
                reason="当前 K 线数量不足，策略信号只能作为观察参考。",
                warnings=data_quality.warnings or ["K 线数量不足。"],
            )

        if data_quality.is_stale:
            return StrategyRuleResult(
                rule_name="data_quality",
                direction="risk",
                score_delta=-10,
                reason="当前 K 线数据可能过旧，策略信号只能作为观察参考。",
                warnings=data_quality.warnings or ["K 线数据可能过旧。"],
            )

        return StrategyRuleResult(
            rule_name="data_quality",
            direction="neutral",
            score_delta=0,
            reason=f"当前 K 线数据质量可用，共 {data_quality.candle_count} 根。",
            warnings=data_quality.warnings,
        )

    def _build_unavailable_summary(
        self,
        *,
        technical_indicators: TechnicalIndicatorResponse,
        data_quality: MarketDataQualityReport | None,
    ) -> str:
        if data_quality is None:
            return (
                f"{technical_indicators.market}:{technical_indicators.symbol} "
                "当前缺少数据质量报告，无法确认策略信号可靠性。"
            )

        if data_quality.is_empty:
            return (
                f"{technical_indicators.market}:{technical_indicators.symbol} "
                "当前没有可用 K 线数据，暂无法生成策略信号。"
            )

        return (
            f"{technical_indicators.market}:{technical_indicators.symbol} "
            "当前 K 线数据存在错误，暂无法生成策略信号。"
        )

    def _build_quality_limited_summary(
        self,
        *,
        technical_indicators: TechnicalIndicatorResponse,
        data_quality: MarketDataQualityReport | None,
    ) -> str:
        if data_quality is None:
            return self._build_baseline_summary(technical_indicators)

        if not data_quality.is_enough:
            return (
                f"{technical_indicators.market}:{technical_indicators.symbol} "
                f"当前 K 线数量为 {data_quality.candle_count}，数据不足，策略信号仅建议观察。"
            )

        if data_quality.is_stale:
            return (
                f"{technical_indicators.market}:{technical_indicators.symbol} "
                "当前 K 线数据可能过旧，策略信号仅建议观察。"
            )

        return self._build_baseline_summary(technical_indicators)

    def _build_rule_results(
        self,
        *,
        quality_rule: StrategyRuleResult | None,
        trend_rule: StrategyRuleResult | None = None,
        rsi_rule: StrategyRuleResult | None = None,
        macd_rule: StrategyRuleResult | None = None,
        include_detail: bool,
    ) -> list[StrategyRuleResult]:
        if not include_detail:
            return []

        results: list[StrategyRuleResult] = []

        if quality_rule is not None:
            results.append(quality_rule)

        if trend_rule is not None:
            results.append(trend_rule)

        if rsi_rule is not None:
            results.append(rsi_rule)

        if macd_rule is not None:
            results.append(macd_rule)

        return results

    def _build_trend_rule(
        self,
        moving_average: MovingAverageSnapshot,
    ) -> StrategyRuleResult:
        score_delta = 0
        warnings: list[str] = []

        if moving_average.trend == "bullish":
            score_delta += self.TREND_BULLISH_SCORE
            direction = "bullish"
            reason = "均线趋势偏多，当前价格结构表现出一定上行动能。"
        elif moving_average.trend == "bearish":
            score_delta += self.TREND_BEARISH_SCORE
            direction = "bearish"
            reason = "均线趋势偏空，当前价格结构表现出一定下行压力。"
        else:
            direction = "neutral"
            reason = "均线趋势暂时中性，尚未形成明确方向。"

        confirm_delta = self._calculate_trend_confirmation_score(moving_average)
        score_delta += confirm_delta

        if confirm_delta > 0:
            reason += " MA5 高于 MA20 且 EMA12 高于 EMA26，短期趋势得到一定确认。"
        elif confirm_delta < 0:
            reason += " MA5 低于 MA20 且 EMA12 低于 EMA26，短期弱势得到一定确认。"
        elif self._has_missing_trend_confirmation_values(moving_average):
            warnings.append("部分均线数据缺失，趋势确认分未完全计算。")

        return StrategyRuleResult(
            rule_name="trend",
            direction=direction,
            score_delta=score_delta,
            reason=reason,
            warnings=warnings,
        )

    def _build_rsi_rule(
        self,
        rsi: RsiSnapshot,
    ) -> StrategyRuleResult:
        score_delta = 0
        warnings: list[str] = []

        if rsi.status == "oversold":
            score_delta += self.RSI_OVERSOLD_SCORE
            direction = "bullish"
            reason = "RSI 处于超卖区域，价格短期可能存在修复机会，但不代表一定反弹。"
        elif rsi.status == "overbought":
            score_delta += self.RSI_OVERBOUGHT_SCORE
            direction = "risk"
            reason = "RSI 处于超买区域，短期追高风险上升。"
        else:
            direction = "neutral"
            reason = "RSI 当前处于中性区域，暂未给出明显超买或超卖信号。"

        if rsi.rsi12 is None:
            warnings.append("RSI12 数据缺失，无法进行中周期 RSI 强弱确认。")
        elif rsi.rsi12 <= 30:
            score_delta += self.RSI_LOW_CONFIRM_SCORE
            direction = "bullish"
            reason += f" RSI12={rsi.rsi12:.2f}，处于明显低位。"
        elif rsi.rsi12 >= 70:
            score_delta += self.RSI_HIGH_RISK_SCORE
            direction = "risk"
            reason += f" RSI12={rsi.rsi12:.2f}，处于明显过热区域。"

        if self._has_missing_rsi_values(rsi):
            warnings.append("部分 RSI 数据缺失，RSI 规则可信度需要谨慎看待。")

        return StrategyRuleResult(
            rule_name="rsi",
            direction=direction,
            score_delta=score_delta,
            reason=reason,
            warnings=self._limit_text_list(warnings, limit=5),
        )

    def _build_macd_rule(
        self,
        macd: MacdSnapshot,
    ) -> StrategyRuleResult:
        score_delta = 0
        warnings: list[str] = []

        if macd.signal == "bullish":
            score_delta += self.MACD_BULLISH_SCORE
            direction = "bullish"
            reason = "MACD 当前为多头信号，趋势动能偏强。"
        elif macd.signal == "bearish":
            score_delta += self.MACD_BEARISH_SCORE
            direction = "bearish"
            reason = "MACD 当前为空头信号，趋势动能偏弱。"
        else:
            direction = "neutral"
            reason = "MACD 当前为中性信号，趋势动能暂不明显。"

        if macd.histogram is None:
            warnings.append("MACD histogram 数据缺失，无法进行柱状图动能确认。")
        elif macd.histogram > 0:
            score_delta += self.MACD_HISTOGRAM_CONFIRM_SCORE
            if direction == "neutral":
                direction = "bullish"
            reason += f" histogram={macd.histogram:.4f}，柱状图为正，动能有一定支持。"
        elif macd.histogram < 0:
            score_delta -= self.MACD_HISTOGRAM_CONFIRM_SCORE
            if direction == "neutral":
                direction = "bearish"
            reason += f" histogram={macd.histogram:.4f}，柱状图为负，动能偏弱。"

        if self._has_missing_macd_values(macd):
            warnings.append("部分 MACD 数据缺失，MACD 规则可信度需要谨慎看待。")

        return StrategyRuleResult(
            rule_name="macd",
            direction=direction,
            score_delta=score_delta,
            reason=reason,
            warnings=self._limit_text_list(warnings, limit=5),
        )

    def _has_missing_macd_values(
        self,
        macd: MacdSnapshot,
    ) -> bool:
        return any(
            value is None
            for value in (
                macd.dif,
                macd.dea,
                macd.histogram,
            )
        )

    def _has_missing_rsi_values(
        self,
        rsi: RsiSnapshot,
    ) -> bool:
        return any(
            value is None
            for value in (
                rsi.rsi6,
                rsi.rsi12,
                rsi.rsi24,
            )
        )

    def _calculate_trend_confirmation_score(
        self,
        moving_average: MovingAverageSnapshot,
    ) -> int:
        if self._has_missing_trend_confirmation_values(moving_average):
            return 0

        if (
                moving_average.ma5 > moving_average.ma20
                and moving_average.ema12 > moving_average.ema26
        ):
            return self.TREND_CONFIRM_SCORE

        if (
                moving_average.ma5 < moving_average.ma20
                and moving_average.ema12 < moving_average.ema26
        ):
            return -self.TREND_CONFIRM_SCORE

        return 0

    def _has_missing_trend_confirmation_values(
        self,
        moving_average: MovingAverageSnapshot,
    ) -> bool:
        return any(
            value is None
            for value in (
                moving_average.ma5,
                moving_average.ma20,
                moving_average.ema12,
                moving_average.ema26,
            )
        )


    def _build_input_snapshot(
        self,
        *,
        technical_indicators: TechnicalIndicatorResponse,
        data_quality: MarketDataQualityReport | None,
        include_detail: bool,
    ) -> StrategySignalInputSnapshot:
        return StrategySignalInputSnapshot(
            technical_indicators=technical_indicators if include_detail else None,
            data_quality=data_quality if include_detail else None,
        )

    def _build_baseline_summary(
        self,
        technical_indicators: TechnicalIndicatorResponse,
    ) -> str:
        trend = technical_indicators.summary.moving_average.trend
        rsi_status = technical_indicators.summary.rsi.status
        macd_signal = technical_indicators.summary.macd.signal
        return (
            f"{technical_indicators.market}:{technical_indicators.symbol} "
            f"当前已根据数据质量、均线趋势、RSI 和 MACD 生成基础策略信号，"
            f"均线趋势为 {trend}，RSI 状态为 {rsi_status}，MACD 信号为 {macd_signal}。"
        )

    def _build_initial_reasons(
        self,
        technical_indicators: TechnicalIndicatorResponse,
    ) -> list[str]:
        reasons = [
            *technical_indicators.summary.interpretation,
            f"当前技术指标基于 {technical_indicators.candle_count} 根 K 线计算。",
        ]

        return self._limit_text_list(reasons, limit=self.MAX_REASON_COUNT)

    def _build_initial_risks(
        self,
        *,
        technical_indicators: TechnicalIndicatorResponse,
        data_quality: MarketDataQualityReport | None,
    ) -> list[str]:
        risks = [
            *technical_indicators.summary.warnings,
            "当前策略信号仍在逐步接入动量、波动率和成交量等规则。",
        ]

        if data_quality is None:
            risks.append("当前未传入数据质量报告，后续步骤会加入数据质量门控。")
        else:
            risks.extend(data_quality.warnings)
            risks.extend(data_quality.errors)

        return self._limit_text_list(risks, limit=self.MAX_RISK_COUNT)

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

    def _clamp_score(
        self,
        score: int,
    ) -> int:
        return max(0, min(100, score))

    def _signal_from_score(
        self,
        score: int,
    ) -> str:
        if score >= 65:
            return "buy"

        if score >= 55:
            return "observe"

        if score >= 45:
            return "hold"

        if score >= 35:
            return "observe"

        return "sell"

    def _strength_from_score(
        self,
        score: int,
    ) -> str:
        if score >= 75 or score < 25:
            return "strong"

        if score >= 55 or score < 45:
            return "medium"

        return "weak"


