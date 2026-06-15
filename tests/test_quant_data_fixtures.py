"""量化测试数据工厂验证。

这些测试确认固定 K 线工厂可以生成上涨、下跌、横盘、缺失日期、放量和多资产数据，
并能写入测试库供 Repository、指标、回测和纸面交易测试复用。
"""

from app.repositories.market_repo import AsyncMarketRepository
from app.schemas.market_data import MarketCandleQuery
from tests.fixtures.quant_data import (
    build_downtrend_candles,
    build_flat_candles,
    build_market_symbol_payload,
    build_missing_date_candles,
    build_multi_asset_candles,
    build_uptrend_candles,
    build_volume_spike_candles,
    persist_quant_symbol_and_candles,
)


def test_quant_uptrend_candle_factory_builds_ordered_payloads() -> None:
    candles = build_uptrend_candles(symbol="QTUP", count=40)

    assert len(candles) == 40
    assert candles[0].symbol == "QTUP"
    assert candles[0].market == "US"
    assert candles[0].source == "mock"
    assert candles[0].adjust_type == "none"
    assert candles[0].candle_time < candles[-1].candle_time
    assert candles[-1].close_price > candles[0].close_price
    assert all(candle.high_price >= candle.low_price for candle in candles)
    assert all(candle.volume >= 0 for candle in candles)


def test_quant_downtrend_and_flat_factories_have_expected_direction() -> None:
    downtrend = build_downtrend_candles(symbol="QTDOWN", count=40)
    flat = build_flat_candles(symbol="QTFLAT", count=40)

    assert downtrend[-1].close_price < downtrend[0].close_price
    assert abs(flat[-1].close_price - flat[0].close_price) <= 1


def test_quant_special_factories_build_expected_shapes() -> None:
    missing = build_missing_date_candles(symbol="QTMISS", count=40, missing_index=10)
    volume_spike = build_volume_spike_candles(symbol="QTVOL", count=40)
    multi_asset = build_multi_asset_candles(count=20)

    assert len(missing) == 39
    assert volume_spike[-1].volume > volume_spike[-2].volume
    assert set(multi_asset.keys()) == {"QTAAA", "QTBBB"}
    assert len(multi_asset["QTAAA"]) == 20
    assert len(multi_asset["QTBBB"]) == 20


async def test_quant_data_factory_can_persist_and_query_candles(db_session) -> None:
    symbol_payload = build_market_symbol_payload(symbol="QTUP")
    candle_payloads = build_uptrend_candles(symbol="QTUP", count=40)

    symbol, candles = await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=symbol_payload,
        candle_payloads=candle_payloads,
    )

    assert symbol.id is not None
    assert len(candles) == 40
    assert all(candle.symbol_id == symbol.id for candle in candles)

    queried = await AsyncMarketRepository(db_session).list_candles(
        MarketCandleQuery(
            symbol="QTUP",
            market="US",
            timeframe="1d",
            limit=40,
            source="mock",
            adjust_type="none",
        )
    )

    assert len(queried) == 40
    assert queried[0].candle_time < queried[-1].candle_time
    assert queried[-1].close_price > queried[0].close_price
