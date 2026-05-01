from datetime import UTC, datetime

from app.core.exceptions import NotFoundException
from app.schemas.stock_analysis import MarketCode, MarketSnapshot


class MockMarketDataService:
    """Mock market data provider for the stage-five stock analysis MVP."""

    _MOCK_QUOTES: dict[tuple[str, MarketCode], dict[str, object]] = {
        ("AAPL", "US"): {
            "name": "Apple Inc.",
            "currency": "USD",
            "latest_price": 172.4,
            "previous_close": 170.2,
            "open_price": 171.0,
            "high_price": 173.5,
            "low_price": 169.8,
            "volume": 83_400_000,
        },
        ("TSLA", "US"): {
            "name": "Tesla Inc.",
            "currency": "USD",
            "latest_price": 185.8,
            "previous_close": 192.3,
            "open_price": 191.0,
            "high_price": 193.2,
            "low_price": 184.6,
            "volume": 101_200_000,
        },
        ("NVDA", "US"): {
            "name": "NVIDIA Corporation",
            "currency": "USD",
            "latest_price": 910.6,
            "previous_close": 892.4,
            "open_price": 898.0,
            "high_price": 918.2,
            "low_price": 895.5,
            "volume": 54_800_000,
        },
        ("600519", "CN"): {
            "name": "贵州茅台",
            "currency": "CNY",
            "latest_price": 1688.0,
            "previous_close": 1660.5,
            "open_price": 1668.0,
            "high_price": 1695.0,
            "low_price": 1658.0,
            "volume": 2_350_000,
        },
        ("0700", "HK"): {
            "name": "Tencent Holdings",
            "currency": "HKD",
            "latest_price": 365.2,
            "previous_close": 358.4,
            "open_price": 360.0,
            "high_price": 368.0,
            "low_price": 357.8,
            "volume": 18_900_000,
        },
    }

    def get_snapshot(self, symbol: str, market: MarketCode) -> MarketSnapshot:
        normalized_symbol = symbol.strip().upper()
        key = (normalized_symbol, market)

        quote = self._MOCK_QUOTES.get(key)
        if quote is None:
            raise NotFoundException(
                message=f"mock market data not found for {market}:{normalized_symbol}"
            )

        return MarketSnapshot(
            symbol=normalized_symbol,
            market=market,
            name=quote["name"],  # type: ignore[arg-type]
            currency=quote["currency"],  # type: ignore[arg-type]
            latest_price=quote["latest_price"],  # type: ignore[arg-type]
            previous_close=quote["previous_close"],  # type: ignore[arg-type]
            open_price=quote["open_price"],  # type: ignore[arg-type]
            high_price=quote["high_price"],  # type: ignore[arg-type]
            low_price=quote["low_price"],  # type: ignore[arg-type]
            volume=quote["volume"],  # type: ignore[arg-type]
            as_of=datetime.now(UTC),
        )