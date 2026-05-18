from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.strategy_signal import (
    StrategySignalInputSnapshot,
    StrategySignalResponse,
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

    def generate_signal(
        self,
        *,
        technical_indicators: TechnicalIndicatorResponse,
        data_quality: MarketDataQualityReport | None = None,
        include_detail: bool = True,
    ) -> StrategySignalResponse:
        """Build a baseline strategy signal response.

        Stage 5.8 step 4 only wires the service shape.
        Later steps will add data quality gate and indicator rules.
        """

        reasons = self._build_initial_reasons(technical_indicators)
        risks = self._build_initial_risks(
            technical_indicators=technical_indicators,
            data_quality=data_quality,
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
            reasons=reasons,
            risks=risks,
            rule_results=[] if include_detail else [],
            input_snapshot=StrategySignalInputSnapshot(
                technical_indicators=technical_indicators if include_detail else None,
                data_quality=data_quality if include_detail else None,
            ),
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