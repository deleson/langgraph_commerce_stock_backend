from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.market_candle import MarketCandle
from app.repositories.market_repo import AsyncMarketRepository
from app.schemas.market_data import MarketCandleQuery
from tests.fixtures.quant_data import (
    build_candle_payload,
    build_downtrend_candles,
    build_market_symbol_payload,
    build_trend_candles,
    build_uptrend_candles,
    quant_decimal,
)


async def test_upsert_symbol_creates_and_updates_existing_symbol(db_session) -> None:
    repo = AsyncMarketRepository(db_session)

    created = await repo.upsert_symbol(
        build_market_symbol_payload(
            symbol="QTUP",
            name="QTUP Original",
            source="mock",
        )
    )

    updated = await repo.upsert_symbol(
        build_market_symbol_payload(
            symbol="QTUP",
            name="QTUP Updated",
            source="tushare",
        )
    )

    assert created.id == updated.id
    assert updated.symbol == "QTUP"
    assert updated.market == "US"
    assert updated.name == "QTUP Updated"
    assert updated.source == "tushare"


async def test_upsert_candle_creates_and_updates_existing_candle(db_session) -> None:
    repo = AsyncMarketRepository(db_session)
    symbol = await repo.upsert_symbol(build_market_symbol_payload(symbol="QTUP"))

    original = build_uptrend_candles(symbol="QTUP", count=1, symbol_id=symbol.id)[0]
    created = await repo.upsert_candle(original)

    updated_payload = original.model_copy(
        update={
            "symbol_id": symbol.id,
            "open_price": quant_decimal("101"),
            "high_price": quant_decimal("103"),
            "low_price": quant_decimal("100"),
            "close_price": quant_decimal("102"),
            "volume": 2_000_000,
            "amount": quant_decimal("204000000"),
        }
    )

    updated = await repo.upsert_candle(updated_payload)

    assert created.id == updated.id
    assert updated.close_price == Decimal("102.0000")
    assert updated.volume == 2_000_000
    assert updated.amount == Decimal("204000000.0000")


async def test_upsert_candles_and_list_candles_returns_latest_limit_in_ascending_order(
    db_session,
) -> None:
    repo = AsyncMarketRepository(db_session)
    symbol = await repo.upsert_symbol(build_market_symbol_payload(symbol="QTUP"))

    payloads = [
        candle.model_copy(update={"symbol_id": symbol.id})
        for candle in build_uptrend_candles(symbol="QTUP", count=40)
    ]

    await repo.upsert_candles(payloads)

    candles = await repo.list_candles(
        MarketCandleQuery(
            symbol="QTUP",
            market="US",
            timeframe="1d",
            limit=5,
            source="mock",
            adjust_type="none",
        )
    )

    assert len(candles) == 5
    assert [candle.candle_time for candle in candles] == sorted(
        candle.candle_time for candle in candles
    )

    expected_latest_five = payloads[-5:]
    assert [candle.candle_time for candle in candles] == [
        candle.candle_time for candle in expected_latest_five
    ]
    assert candles[0].close_price == expected_latest_five[0].close_price
    assert candles[-1].close_price == expected_latest_five[-1].close_price


async def test_list_candles_by_date_range_returns_inclusive_ascending_range(
    db_session,
) -> None:
    repo = AsyncMarketRepository(db_session)
    symbol = await repo.upsert_symbol(build_market_symbol_payload(symbol="QTUP"))

    payloads = [
        candle.model_copy(update={"symbol_id": symbol.id})
        for candle in build_uptrend_candles(symbol="QTUP", count=20)
    ]

    await repo.upsert_candles(payloads)

    start = payloads[5].candle_time
    end = payloads[10].candle_time

    candles = await repo.list_candles_by_date_range(
        symbol="QTUP",
        market="US",
        timeframe="1d",
        start_at=start,
        end_at=end,
        source="mock",
        adjust_type="none",
    )

    assert len(candles) == 6
    assert candles[0].candle_time == start
    assert candles[-1].candle_time == end
    assert [candle.candle_time for candle in candles] == [
        candle.candle_time for candle in payloads[5:11]
    ]


async def test_list_candles_filters_by_source(db_session) -> None:
    repo = AsyncMarketRepository(db_session)
    symbol = await repo.upsert_symbol(build_market_symbol_payload(symbol="QTSRC"))

    mock_payloads = [
        candle.model_copy(update={"symbol_id": symbol.id, "source": "mock"})
        for candle in build_trend_candles(symbol="QTSRC", count=5)
    ]
    tushare_payloads = [
        candle.model_copy(update={"symbol_id": symbol.id, "source": "tushare"})
        for candle in build_downtrend_candles(symbol="QTSRC", count=5)
    ]

    await repo.upsert_candles(mock_payloads)
    await repo.upsert_candles(tushare_payloads)

    mock_candles = await repo.list_candles(
        MarketCandleQuery(
            symbol="QTSRC",
            market="US",
            timeframe="1d",
            limit=10,
            source="mock",
            adjust_type="none",
        )
    )

    tushare_candles = await repo.list_candles(
        MarketCandleQuery(
            symbol="QTSRC",
            market="US",
            timeframe="1d",
            limit=10,
            source="tushare",
            adjust_type="none",
        )
    )

    assert len(mock_candles) == 5
    assert len(tushare_candles) == 5
    assert all(candle.source == "mock" for candle in mock_candles)
    assert all(candle.source == "tushare" for candle in tushare_candles)
    assert mock_candles[-1].close_price != tushare_candles[-1].close_price


async def test_list_candles_filters_by_adjust_type(db_session) -> None:
    repo = AsyncMarketRepository(db_session)
    symbol = await repo.upsert_symbol(build_market_symbol_payload(symbol="QTADJ"))

    none_payloads = [
        candle.model_copy(update={"symbol_id": symbol.id, "adjust_type": "none"})
        for candle in build_uptrend_candles(symbol="QTADJ", count=5)
    ]
    qfq_payloads = [
        candle.model_copy(update={"symbol_id": symbol.id, "adjust_type": "qfq"})
        for candle in build_downtrend_candles(symbol="QTADJ", count=5)
    ]

    await repo.upsert_candles(none_payloads)
    await repo.upsert_candles(qfq_payloads)

    none_candles = await repo.list_candles(
        MarketCandleQuery(
            symbol="QTADJ",
            market="US",
            timeframe="1d",
            limit=10,
            source="mock",
            adjust_type="none",
        )
    )

    qfq_candles = await repo.list_candles(
        MarketCandleQuery(
            symbol="QTADJ",
            market="US",
            timeframe="1d",
            limit=10,
            source="mock",
            adjust_type="qfq",
        )
    )

    assert len(none_candles) == 5
    assert len(qfq_candles) == 5
    assert all(candle.adjust_type == "none" for candle in none_candles)
    assert all(candle.adjust_type == "qfq" for candle in qfq_candles)
    assert none_candles[-1].close_price != qfq_candles[-1].close_price


async def test_create_candle_duplicate_key_raises_integrity_error(db_session) -> None:
    repo = AsyncMarketRepository(db_session)
    symbol = await repo.upsert_symbol(build_market_symbol_payload(symbol="QTDUP"))

    payload = build_uptrend_candles(symbol="QTDUP", count=1, symbol_id=symbol.id)[0]

    await repo.create_candle(payload)

    with pytest.raises(IntegrityError):
        await repo.create_candle(payload)

    await db_session.rollback()


async def test_create_candle_rejects_high_price_lower_than_low_price(db_session) -> None:
    symbol = await AsyncMarketRepository(db_session).upsert_symbol(
        build_market_symbol_payload(symbol="QTBAD")
    )

    valid_payload = build_uptrend_candles(symbol="QTBAD", count=1, symbol_id=symbol.id)[0]

    invalid = MarketCandle(
        symbol_id=symbol.id,
        symbol=valid_payload.symbol,
        market=valid_payload.market,
        timeframe=valid_payload.timeframe,
        candle_time=valid_payload.candle_time,
        open_price=quant_decimal("100"),
        high_price=quant_decimal("90"),
        low_price=quant_decimal("95"),
        close_price=quant_decimal("96"),
        volume=1_000_000,
        amount=quant_decimal("96000000"),
        source="mock",
        is_adjusted=False,
        adjust_type="none",
    )

    db_session.add(invalid)

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


async def test_get_candle_returns_none_for_wrong_source_or_adjust_type(db_session) -> None:
    repo = AsyncMarketRepository(db_session)
    symbol = await repo.upsert_symbol(build_market_symbol_payload(symbol="QTGET"))

    payload = build_uptrend_candles(symbol="QTGET", count=1, symbol_id=symbol.id)[0]
    candle = await repo.upsert_candle(payload)

    wrong_source = await repo.get_candle(
        symbol="QTGET",
        market="US",
        timeframe="1d",
        candle_time=candle.candle_time,
        source="tushare",
        adjust_type="none",
    )

    wrong_adjust_type = await repo.get_candle(
        symbol="QTGET",
        market="US",
        timeframe="1d",
        candle_time=candle.candle_time,
        source="mock",
        adjust_type="qfq",
    )

    assert wrong_source is None
    assert wrong_adjust_type is None