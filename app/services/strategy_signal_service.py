from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.strategy_signal import (
    StrategySignalInputSnapshot,
    StrategySignalResponse,
    StrategyRuleResult,
)
from app.schemas.technical_indicator import TechnicalIndicatorResponse


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

        return StrategySignalResponse(
            symbol=technical_indicators.symbol,
            market=technical_indicators.market,
            timeframe=technical_indicators.timeframe,
            adjust_type=technical_indicators.adjust_type,
            source=technical_indicators.source,
            status="available",
            signal="hold",
            strength="weak",
            score=self.BASE_SCORE,
            summary=self._build_baseline_summary(technical_indicators),
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
            include_detail: bool,
    ) -> list[StrategyRuleResult]:
        if not include_detail:
            return []

        if quality_rule is None:
            return []

        return [quality_rule]

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
        return (
            f"{technical_indicators.market}:{technical_indicators.symbol} "
            "当前已生成基础策略信号。具体趋势、RSI、MACD、动量、波动率和成交量规则将在后续步骤逐步接入。"
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
            "当前策略信号为基础中性版本，尚未接入完整规则评分。",
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