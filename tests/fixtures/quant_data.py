"""量化专项测试数据工厂。

阶段九-A 的量化测试不依赖真实行情波动，而是用固定、可复现、可手算的小样本 K 线。
本文件负责生成上涨、下跌、横盘、放量、缺失日期、过旧数据和多资产数据，
让技术指标、策略信号、回测、候选评分和纸面交易测试都有稳定输入。

这些数据只用于测试，不代表真实股票走势，也不用于证明策略未来收益。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.market_repo import AsyncMarketRepository
from app.schemas.market_data import MarketCandleCreate, MarketSymbolCreate


QuantTrend = Literal["up", "down", "flat"]


DEFAULT_START_AT = datetime(2024, 1, 2, tzinfo=UTC)
MONEY_QUANT = Decimal("0.0001")


def quant_decimal(value: str | int | float | Decimal) -> Decimal:
    """统一测试金额精度，避免 Decimal 断言受浮点误差影响。"""

    return Decimal(str(value)).quantize(MONEY_QUANT)


def build_market_symbol_payload(
    *,
    symbol: str = "QTUP",
    market: str = "US",
    name: str | None = None,
    currency: str = "USD",
    exchange: str = "NASDAQ",
    source: str = "mock",
) -> MarketSymbolCreate:
    """构造测试股票基础信息。"""

    normalized_symbol = symbol.upper()

    return MarketSymbolCreate(
        symbol=normalized_symbol,
        market=market,
        name=name or f"{normalized_symbol} Quant Test",
        currency=currency,
        exchange=exchange,
        provider_symbol=normalized_symbol,
        source=source,
        is_active=True,
    )


def build_candle_payload(
    *,
    symbol: str,
    market: str = "US",
    timeframe: str = "1d",
    candle_time: datetime,
    open_price: Decimal,
    high_price: Decimal,
    low_price: Decimal,
    close_price: Decimal,
    volume: int = 1_000_000,
    amount: Decimal | None = None,
    source: str = "mock",
    adjust_type: str = "none",
    symbol_id: int | None = None,
) -> MarketCandleCreate:
    """构造单根测试 K 线。"""

    return MarketCandleCreate(
        symbol_id=symbol_id,
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        candle_time=candle_time,
        open_price=quant_decimal(open_price),
        high_price=quant_decimal(high_price),
        low_price=quant_decimal(low_price),
        close_price=quant_decimal(close_price),
        volume=volume,
        amount=quant_decimal(amount) if amount is not None else None,
        source=source,
        is_adjusted=False,
        adjust_type=adjust_type,
    )


def build_trend_candles(
    *,
    symbol: str = "QTUP",
    market: str = "US",
    timeframe: str = "1d",
    count: int = 40,
    start_at: datetime = DEFAULT_START_AT,
    start_price: Decimal = Decimal("100"),
    step: Decimal = Decimal("1"),
    trend: QuantTrend = "up",
    volume_start: int = 1_000_000,
    volume_step: int = 10_000,
    source: str = "mock",
    adjust_type: str = "none",
    symbol_id: int | None = None,
) -> list[MarketCandleCreate]:
    """构造趋势型 K 线序列。

    trend=up / down / flat 分别用于测试上涨、下跌和横盘场景。
    K 线按时间升序返回，这是指标计算和回测避免未来函数的基础。
    """

    if count <= 0:
        raise ValueError("count must be positive")

    candles: list[MarketCandleCreate] = []

    for index in range(count):
        if trend == "up":
            close_price = start_price + step * index
            open_price = close_price - Decimal("0.2000")
        elif trend == "down":
            close_price = start_price - step * index
            open_price = close_price + Decimal("0.2000")
        else:
            offset = Decimal("0.2000") if index % 2 == 0 else Decimal("-0.2000")
            close_price = start_price + offset
            open_price = start_price

        high_price = max(open_price, close_price) + Decimal("0.5000")
        low_price = max(Decimal("0"), min(open_price, close_price) - Decimal("0.5000"))
        volume = volume_start + volume_step * index
        amount = close_price * Decimal(volume)

        candles.append(
            build_candle_payload(
                symbol=symbol,
                market=market,
                timeframe=timeframe,
                candle_time=start_at + timedelta(days=index),
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
                amount=amount,
                source=source,
                adjust_type=adjust_type,
                symbol_id=symbol_id,
            )
        )

    return candles


def build_uptrend_candles(
    *,
    symbol: str = "QTUP",
    count: int = 40,
    symbol_id: int | None = None,
) -> list[MarketCandleCreate]:
    """构造稳定上涨趋势 K 线。"""

    return build_trend_candles(
        symbol=symbol,
        count=count,
        start_price=Decimal("100"),
        step=Decimal("1"),
        trend="up",
        symbol_id=symbol_id,
    )


def build_downtrend_candles(
    *,
    symbol: str = "QTDOWN",
    count: int = 40,
    symbol_id: int | None = None,
) -> list[MarketCandleCreate]:
    """构造稳定下跌趋势 K 线。"""

    return build_trend_candles(
        symbol=symbol,
        count=count,
        start_price=Decimal("140"),
        step=Decimal("1"),
        trend="down",
        symbol_id=symbol_id,
    )


def build_flat_candles(
    *,
    symbol: str = "QTFLAT",
    count: int = 40,
    symbol_id: int | None = None,
) -> list[MarketCandleCreate]:
    """构造横盘震荡 K 线。"""

    return build_trend_candles(
        symbol=symbol,
        count=count,
        start_price=Decimal("100"),
        step=Decimal("0"),
        trend="flat",
        symbol_id=symbol_id,
    )


def build_volume_spike_candles(
    *,
    symbol: str = "QTVOL",
    count: int = 40,
    symbol_id: int | None = None,
) -> list[MarketCandleCreate]:
    """构造最后一根成交量放大的 K 线序列。"""

    candles = build_trend_candles(
        symbol=symbol,
        count=count,
        start_price=Decimal("100"),
        step=Decimal("0.5"),
        trend="up",
        symbol_id=symbol_id,
    )

    last = candles[-1]
    candles[-1] = last.model_copy(
        update={
            "volume": last.volume * 5,
            "amount": quant_decimal(last.close_price * Decimal(last.volume * 5)),
        }
    )
    return candles


def build_missing_date_candles(
    *,
    symbol: str = "QTMISS",
    count: int = 40,
    missing_index: int = 10,
    symbol_id: int | None = None,
) -> list[MarketCandleCreate]:
    candles = build_trend_candles(
        symbol=symbol,
        count=count,
        start_price=Decimal("100"),
        step=Decimal("1"),
        trend="up",
        symbol_id=symbol_id,
    )

    if 0 <= missing_index < len(candles):
        return [
            candle
            for index, candle in enumerate(candles)
            if index != missing_index
        ]

    return candles


def build_stale_candles(
    *,
    symbol: str = "QTSTALE",
    count: int = 40,
    symbol_id: int | None = None,
) -> list[MarketCandleCreate]:
    return build_trend_candles(
        symbol=symbol,
        count=count,
        start_at=datetime(2020, 1, 2, tzinfo=UTC),
        start_price=Decimal("100"),
        step=Decimal("0.5"),
        trend="up",
        symbol_id=symbol_id,
    )


def build_duplicate_candle_payloads(
    *,
    symbol: str = "QTDUP",
    symbol_id: int | None = None,
) -> list[MarketCandleCreate]:
    candles = build_trend_candles(
        symbol=symbol,
        count=5,
        start_price=Decimal("100"),
        step=Decimal("1"),
        trend="up",
        symbol_id=symbol_id,
    )

    duplicated = candles[2].model_copy(
        update={
            "close_price": quant_decimal("120"),
            "high_price": quant_decimal("121"),
            "low_price": quant_decimal("99"),
        }
    )

    return [*candles, duplicated]


def build_multi_asset_candles(
    *,
    count: int = 40,
) -> dict[str, list[MarketCandleCreate]]:
    return {
        "QTAAA": build_trend_candles(
            symbol="QTAAA",
            count=count,
            start_price=Decimal("100"),
            step=Decimal("1"),
            trend="up",
        ),
        "QTBBB": build_trend_candles(
            symbol="QTBBB",
            count=count,
            start_price=Decimal("120"),
            step=Decimal("0.5"),
            trend="down",
        ),
    }


async def persist_quant_symbol_and_candles(
    db: AsyncSession,
    *,
    symbol_payload: MarketSymbolCreate,
    candle_payloads: list[MarketCandleCreate],
):
    repo = AsyncMarketRepository(db)

    symbol = await repo.upsert_symbol(symbol_payload)

    candles_with_symbol_id = [
        candle.model_copy(update={"symbol_id": symbol.id})
        for candle in candle_payloads
    ]

    candles = await repo.upsert_candles(candles_with_symbol_id)

    return symbol, candles
