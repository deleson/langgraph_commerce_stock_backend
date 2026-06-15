"""策略信号专项测试。

验证确定性规则如何结合趋势、RSI、MACD、动量、波动率、成交量和数据质量。
signal=buy / sell 只是研究信号，不构成真实交易建议。
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from app.core.exceptions import NotFoundException
from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.technical_indicator import TechnicalIndicatorResponse, TechnicalIndicatorSummary
from app.services.strategy_signal_query_service import StrategySignalQueryService
from app.services.strategy_signal_service import StrategySignalService
from app.services.technical_indicator_service import TechnicalIndicatorService
from tests.fixtures.quant_data import (
    build_downtrend_candles,
    build_market_symbol_payload,
    build_stale_candles,
    build_uptrend_candles,
    build_volume_spike_candles,
    persist_quant_symbol_and_candles,
)


def _indicator_dataframe(candles) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "candle_time": candle.candle_time,
                "close_price": float(candle.close_price),
                "volume": float(candle.volume),
            }
            for candle in candles
        ]
    )


def _technical_response(symbol: str, candles) -> TechnicalIndicatorResponse:
    service = TechnicalIndicatorService()
    df = _indicator_dataframe(candles)

    return TechnicalIndicatorResponse(
        symbol=symbol,
        market="US",
        timeframe="1d",
        adjust_type="none",
        source="mock",
        candle_count=len(candles),
        calculated_at=datetime(2024, 1, 1, tzinfo=UTC),
        summary=TechnicalIndicatorSummary(
            moving_average=service.calculate_moving_average(df),
            rsi=service.calculate_rsi(df),
            macd=service.calculate_macd(df),
            volatility=service.calculate_volatility(df),
            momentum=service.calculate_momentum(df),
            volume_factor=service.calculate_volume_factor(df),
            interpretation=[],
            warnings=[],
        ),
    )


def _quality_report(
    *,
    symbol: str,
    candle_count: int = 40,
    is_empty: bool = False,
    is_enough: bool = True,
    is_stale: bool = False,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> MarketDataQualityReport:
    return MarketDataQualityReport(
        symbol=symbol,
        market="US",
        timeframe="1d",
        source="mock",
        adjust_type="none",
        candle_count=candle_count,
        duplicate_count=0,
        is_empty=is_empty,
        is_enough=is_enough,
        is_stale=is_stale,
        errors=errors or [],
        warnings=warnings or [],
        checked_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


def _rule_map(response):
    return {rule.rule_name: rule for rule in response.rule_results}


def test_generate_signal_returns_buy_for_uptrend_indicators() -> None:
    service = StrategySignalService()
    technical = _technical_response(
        "QTUP",
        build_uptrend_candles(symbol="QTUP", count=40),
    )

    result = service.generate_signal(
        technical_indicators=technical,
        data_quality=_quality_report(symbol="QTUP"),
        include_detail=True,
    )

    assert result.status == "available"
    assert result.signal == "buy"
    assert result.strength == "strong"
    assert result.score == 97
    assert result.summary.startswith("US:QTUP 当前已根据数据质量")
    assert result.disclaimer
    assert result.input_snapshot is not None

    rules = _rule_map(result)
    assert rules["data_quality"].direction == "neutral"
    assert rules["trend"].score_delta == 23
    assert rules["rsi"].score_delta == -17
    assert rules["macd"].score_delta == 22
    assert rules["momentum"].score_delta == 16
    assert rules["volatility"].score_delta == 3
    assert rules["volume"].score_delta == 0


def test_generate_signal_returns_sell_for_downtrend_indicators() -> None:
    service = StrategySignalService()
    technical = _technical_response(
        "QTDN",
        build_downtrend_candles(symbol="QTDN", count=40),
    )

    result = service.generate_signal(
        technical_indicators=technical,
        data_quality=_quality_report(symbol="QTDN"),
        include_detail=True,
    )

    assert result.status == "available"
    assert result.signal == "sell"
    assert result.strength == "strong"
    assert result.score == 7

    rules = _rule_map(result)
    assert rules["trend"].direction == "bearish"
    assert rules["trend"].score_delta == -23
    assert rules["rsi"].direction == "bullish"
    assert rules["rsi"].score_delta == 15
    assert rules["macd"].direction == "bearish"
    assert rules["macd"].score_delta == -22
    assert rules["momentum"].direction == "bearish"
    assert rules["momentum"].score_delta == -16


def test_generate_signal_adds_volume_score_for_volume_spike() -> None:
    service = StrategySignalService()
    technical = _technical_response(
        "QTVF",
        build_volume_spike_candles(symbol="QTVF", count=40),
    )

    result = service.generate_signal(
        technical_indicators=technical,
        data_quality=_quality_report(symbol="QTVF"),
        include_detail=True,
    )

    assert result.status == "available"
    assert result.signal == "buy"
    assert result.strength == "strong"
    assert result.score == 100

    rules = _rule_map(result)
    assert rules["volume"].direction == "bullish"
    assert rules["volume"].score_delta == 9


def test_generate_signal_returns_observe_when_data_not_enough() -> None:
    service = StrategySignalService()
    technical = _technical_response(
        "QTNE",
        build_uptrend_candles(symbol="QTNE", count=40),
    )

    result = service.generate_signal(
        technical_indicators=technical,
        data_quality=_quality_report(
            symbol="QTNE",
            candle_count=10,
            is_enough=False,
            warnings=["not enough candles: required=35, actual=10"],
        ),
        include_detail=True,
    )

    assert result.status == "available"
    assert result.signal == "observe"
    assert result.strength == "weak"
    assert result.score == 40
    assert "数据不足" in result.summary

    rules = _rule_map(result)
    assert list(rules) == ["data_quality"]
    assert rules["data_quality"].direction == "risk"
    assert rules["data_quality"].score_delta == -10


def test_generate_signal_returns_observe_when_data_stale() -> None:
    service = StrategySignalService()
    technical = _technical_response(
        "QTST",
        build_uptrend_candles(symbol="QTST", count=40),
    )

    result = service.generate_signal(
        technical_indicators=technical,
        data_quality=_quality_report(
            symbol="QTST",
            is_stale=True,
            warnings=["latest candle is stale"],
        ),
        include_detail=True,
    )

    assert result.status == "available"
    assert result.signal == "observe"
    assert result.strength == "weak"
    assert result.score == 40
    assert "过旧" in result.summary

    rules = _rule_map(result)
    assert list(rules) == ["data_quality"]
    assert rules["data_quality"].direction == "risk"


def test_generate_signal_returns_unavailable_when_data_empty() -> None:
    service = StrategySignalService()
    technical = _technical_response(
        "QTEM",
        build_uptrend_candles(symbol="QTEM", count=40),
    )

    result = service.generate_signal(
        technical_indicators=technical,
        data_quality=_quality_report(
            symbol="QTEM",
            candle_count=0,
            is_empty=True,
            is_enough=False,
            errors=["market candles not found for US:QTEM"],
        ),
        include_detail=True,
    )

    assert result.status == "unavailable"
    assert result.signal is None
    assert result.strength is None
    assert result.score == 0
    assert "暂无法生成策略信号" in result.summary

    rules = _rule_map(result)
    assert list(rules) == ["data_quality"]
    assert rules["data_quality"].direction == "invalid"
    assert rules["data_quality"].score_delta == -100


def test_generate_signal_without_data_quality_keeps_detail_warning() -> None:
    service = StrategySignalService()
    technical = _technical_response(
        "QTNOQ",
        build_uptrend_candles(symbol="QTNOQ", count=40),
    )

    result = service.generate_signal(
        technical_indicators=technical,
        data_quality=None,
        include_detail=True,
    )

    assert result.status == "available"
    assert result.signal == "buy"
    assert result.score == 97

    rules = _rule_map(result)
    assert rules["data_quality"].direction == "neutral"
    assert rules["data_quality"].score_delta == 0
    assert any("缺少数据质量报告" in risk for risk in result.risks)


def test_generate_signal_hides_detail_when_include_detail_false() -> None:
    service = StrategySignalService()
    technical = _technical_response(
        "QTNOD",
        build_uptrend_candles(symbol="QTNOD", count=40),
    )

    result = service.generate_signal(
        technical_indicators=technical,
        data_quality=_quality_report(symbol="QTNOD"),
        include_detail=False,
    )

    assert result.status == "available"
    assert result.signal == "buy"
    assert result.score == 97
    assert result.rule_results == []
    assert result.input_snapshot is not None
    assert result.input_snapshot.technical_indicators is None
    assert result.input_snapshot.data_quality is None


async def test_query_service_generates_signal_from_database_candles(db_session) -> None:
    await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=build_market_symbol_payload(symbol="QTQS"),
        candle_payloads=build_uptrend_candles(symbol="QTQS", count=40),
    )

    service = StrategySignalQueryService(db_session)

    result = await service.get_signal(
        symbol="qtqs",
        market="US",
        timeframe="1d",
        limit=40,
        adjust_type="none",
        source="mock",
        include_detail=True,
        min_required=35,
        stale_after_days=3650,
    )

    assert result.symbol == "QTQS"
    assert result.market == "US"
    assert result.status == "available"
    assert result.signal == "buy"
    assert result.strength == "strong"
    assert result.score == 97
    assert result.input_snapshot is not None
    assert result.input_snapshot.technical_indicators is not None
    assert result.input_snapshot.data_quality is not None


async def test_query_service_returns_observe_for_stale_database_candles(db_session) -> None:
    await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=build_market_symbol_payload(symbol="QTST"),
        candle_payloads=build_stale_candles(symbol="QTST", count=40),
    )

    service = StrategySignalQueryService(db_session)

    result = await service.get_signal(
        symbol="QTST",
        market="US",
        timeframe="1d",
        limit=40,
        adjust_type="none",
        source="mock",
        include_detail=True,
        min_required=35,
        stale_after_days=30,
    )

    assert result.status == "available"
    assert result.signal == "observe"
    assert result.strength == "weak"
    assert result.score == 40
    assert result.rule_results[0].rule_name == "data_quality"
    assert result.rule_results[0].direction == "risk"


async def test_query_service_respects_source_filter(db_session) -> None:
    await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=build_market_symbol_payload(symbol="QTQF"),
        candle_payloads=build_uptrend_candles(symbol="QTQF", count=40),
    )

    service = StrategySignalQueryService(db_session)

    with pytest.raises(NotFoundException) as exc_info:
        await service.get_signal(
            symbol="QTQF",
            market="US",
            timeframe="1d",
            limit=40,
            adjust_type="none",
            source="tushare",
            include_detail=True,
            min_required=35,
        )

    assert exc_info.value.message == "market candles not found for US:QTQF"
