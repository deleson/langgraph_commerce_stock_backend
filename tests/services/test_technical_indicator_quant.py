"""技术指标公式专项测试。

使用固定 K 线验证 MA、RSI、MACD、波动率、动量和成交量因子计算稳定性。
测试目的不是证明指标能预测未来，而是保证公式实现可复现。
"""

import pandas as pd
import pytest

from app.core.exceptions import BadRequestException, NotFoundException
from app.services.technical_indicator_query_service import TechnicalIndicatorQueryService
from app.services.technical_indicator_service import TechnicalIndicatorService
from tests.fixtures.quant_data import (
    build_downtrend_candles,
    build_flat_candles,
    build_market_symbol_payload,
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


def test_moving_average_calculates_expected_values_for_uptrend() -> None:
    service = TechnicalIndicatorService()
    df = _indicator_dataframe(build_uptrend_candles(symbol="QTMA", count=20))

    result = service.calculate_moving_average(df)

    assert result.ma5 == 117.0
    assert result.ma10 == 114.5
    assert result.ma20 == 109.5
    assert result.ma60 is None
    assert result.ema12 == 113.7301
    assert result.ema26 is None
    assert result.trend == "bullish"


def test_moving_average_calculates_bearish_trend_for_downtrend() -> None:
    service = TechnicalIndicatorService()
    df = _indicator_dataframe(build_downtrend_candles(symbol="QTMD", count=40))

    result = service.calculate_moving_average(df)

    assert result.ma5 == 103.0
    assert result.ma10 == 105.5
    assert result.ma20 == 110.5
    assert result.ma60 is None
    assert result.ema12 == 106.4919
    assert result.ema26 == 112.8786
    assert result.trend == "bearish"


def test_rsi_handles_uptrend_downtrend_and_flat_data() -> None:
    service = TechnicalIndicatorService()

    uptrend = service.calculate_rsi(
        _indicator_dataframe(build_uptrend_candles(symbol="QTRU", count=40))
    )
    downtrend = service.calculate_rsi(
        _indicator_dataframe(build_downtrend_candles(symbol="QTRD", count=40))
    )
    flat = service.calculate_rsi(
        _indicator_dataframe(build_flat_candles(symbol="QTRF", count=40))
    )

    assert uptrend.rsi6 == 100.0
    assert uptrend.rsi12 == 100.0
    assert uptrend.rsi24 == 100.0
    assert uptrend.status == "overbought"

    assert downtrend.rsi6 == 0.0
    assert downtrend.rsi12 == 0.0
    assert downtrend.rsi24 == 0.0
    assert downtrend.status == "oversold"

    assert flat.rsi6 == 50.0
    assert flat.rsi12 == 50.0
    assert flat.rsi24 == 50.0
    assert flat.status == "neutral"


def test_macd_calculates_bullish_and_bearish_signals() -> None:
    service = TechnicalIndicatorService()

    bullish = service.calculate_macd(
        _indicator_dataframe(build_uptrend_candles(symbol="QTMCU", count=40))
    )
    bearish = service.calculate_macd(
        _indicator_dataframe(build_downtrend_candles(symbol="QTMCD", count=40))
    )

    assert bullish.dif == 6.3867
    assert bullish.dea == 6.1146
    assert bullish.histogram == 0.5443
    assert bullish.signal == "bullish"

    assert bearish.dif == -6.3867
    assert bearish.dea == -6.1146
    assert bearish.histogram == -0.5443
    assert bearish.signal == "bearish"


def test_macd_returns_neutral_when_candles_are_not_enough() -> None:
    service = TechnicalIndicatorService()

    result = service.calculate_macd(
        _indicator_dataframe(build_uptrend_candles(symbol="QTMCS", count=20))
    )

    assert result.dif is None
    assert result.dea is None
    assert result.histogram is None
    assert result.signal == "neutral"


def test_volatility_calculates_expected_low_risk_values() -> None:
    service = TechnicalIndicatorService()

    result = service.calculate_volatility(
        _indicator_dataframe(build_uptrend_candles(symbol="QTVOL", count=20))
    )

    assert result.daily_return_std == 0.000476
    assert result.annualized_volatility == 0.007556
    assert result.level == "low"


def test_momentum_calculates_expected_values_and_direction() -> None:
    service = TechnicalIndicatorService()

    bullish = service.calculate_momentum(
        _indicator_dataframe(build_uptrend_candles(symbol="QTMOU", count=40))
    )
    bearish = service.calculate_momentum(
        _indicator_dataframe(build_downtrend_candles(symbol="QTMOD", count=40))
    )

    assert bullish.momentum_5 == 5.0
    assert bullish.momentum_10 == 10.0
    assert bullish.momentum_20 == 20.0
    assert bullish.direction == "bullish"

    assert bearish.momentum_5 == -5.0
    assert bearish.momentum_10 == -10.0
    assert bearish.momentum_20 == -20.0
    assert bearish.direction == "bearish"


def test_volume_factor_detects_volume_expansion() -> None:
    service = TechnicalIndicatorService()

    result = service.calculate_volume_factor(
        _indicator_dataframe(build_volume_spike_candles(symbol="QTVF", count=40))
    )

    assert result.volume_ma5 == 2482000.0
    assert result.volume_ma20 == 1573000.0
    assert result.volume_ratio == 4.4183
    assert result.status == "expanding"


def test_volume_factor_returns_normal_when_volume_ratio_is_normal() -> None:
    service = TechnicalIndicatorService()

    result = service.calculate_volume_factor(
        _indicator_dataframe(build_uptrend_candles(symbol="QTVN", count=40))
    )

    assert result.volume_ma5 == 1370000.0
    assert result.volume_ma20 == 1295000.0
    assert result.volume_ratio == 1.0734
    assert result.status == "normal"


def test_price_indicator_rejects_empty_dataframe() -> None:
    service = TechnicalIndicatorService()

    with pytest.raises(BadRequestException) as exc_info:
        service.calculate_moving_average(pd.DataFrame())

    assert exc_info.value.message == "indicator dataframe cannot be empty"


def test_price_indicator_rejects_missing_close_price_column() -> None:
    service = TechnicalIndicatorService()

    with pytest.raises(BadRequestException) as exc_info:
        service.calculate_moving_average(pd.DataFrame({"volume": [1000]}))

    assert exc_info.value.message == "indicator dataframe missing close_price column"


def test_price_indicator_rejects_non_positive_close_price() -> None:
    service = TechnicalIndicatorService()

    df = pd.DataFrame(
        {
            "close_price": [100.0, 0.0, 102.0],
            "volume": [1000.0, 1000.0, 1000.0],
        }
    )

    with pytest.raises(BadRequestException) as exc_info:
        service.calculate_moving_average(df)

    assert exc_info.value.message == "indicator dataframe contains non-positive close_price"


def test_volume_indicator_rejects_negative_volume() -> None:
    service = TechnicalIndicatorService()

    df = pd.DataFrame(
        {
            "close_price": [100.0, 101.0, 102.0],
            "volume": [1000.0, -1.0, 1000.0],
        }
    )

    with pytest.raises(BadRequestException) as exc_info:
        service.calculate_volume_factor(df)

    assert exc_info.value.message == "indicator dataframe contains negative volume"


async def test_query_service_summary_uses_database_candles(db_session) -> None:
    await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=build_market_symbol_payload(symbol="QTQS"),
        candle_payloads=build_uptrend_candles(symbol="QTQS", count=40),
    )

    service = TechnicalIndicatorQueryService(db_session)

    result = await service.get_summary(
        symbol="qtqs",
        market="US",
        timeframe="1d",
        limit=40,
        adjust_type="none",
        source="mock",
    )

    assert result.symbol == "QTQS"
    assert result.market == "US"
    assert result.timeframe == "1d"
    assert result.source == "mock"
    assert result.adjust_type == "none"
    assert result.candle_count == 40

    assert result.summary.moving_average.ma5 == 137.0
    assert result.summary.moving_average.ma20 == 129.5
    assert result.summary.moving_average.trend == "bullish"

    assert result.summary.rsi.rsi12 == 100.0
    assert result.summary.rsi.status == "overbought"

    assert result.summary.macd.signal == "bullish"
    assert result.summary.momentum.direction == "bullish"
    assert result.summary.volume_factor.status == "normal"

    assert result.summary.interpretation == [
        "均线趋势为 bullish。",
        "RSI 状态为 overbought。",
        "MACD 信号为 bullish。",
        "波动率等级为 low。",
        "动量方向为 bullish。",
        "成交量状态为 normal。",
    ]
    assert len(result.summary.warnings) == 3


async def test_query_service_respects_source_filter(db_session) -> None:
    await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=build_market_symbol_payload(symbol="QTQF"),
        candle_payloads=build_uptrend_candles(symbol="QTQF", count=40),
    )

    service = TechnicalIndicatorQueryService(db_session)

    with pytest.raises(NotFoundException) as exc_info:
        await service.get_summary(
            symbol="QTQF",
            market="US",
            timeframe="1d",
            limit=40,
            adjust_type="none",
            source="tushare",
        )

    assert exc_info.value.message == "market candles not found for US:QTQF"
