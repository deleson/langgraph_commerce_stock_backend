from datetime import UTC, datetime, timedelta

from app.core.exceptions import NotFoundException
from app.schemas.market import (
    CandleTimeframe,
    MarketCandle,
    MarketStockSearchItem,
)
from app.schemas.stock_analysis import MarketCode, MarketSnapshot


# list_stocks()	列出所有模拟股票
# search_stocks()	按关键词搜索股票
# get_snapshot()	获取某只股票的当前行情快照
# get_candles()	生成某只股票的 K 线数据
# _get_quote()	内部方法：从模拟数据里取行情
# _normalize_symbol()	内部方法：标准化股票代码
# _get_time_step()	内部方法：根据 K 线周期返回时间间隔
# _mock_close_price()	内部方法：生成模拟收盘价
# _mock_open_price()	内部方法：生成模拟开盘价
# _mock_volume()	内部方法：生成模拟成交量

class MockMarketDataService:
    """Mock market data provider for stock analysis and market APIs."""

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

    _EXCHANGES: dict[tuple[str, MarketCode], str] = {
        ("AAPL", "US"): "NASDAQ",
        ("TSLA", "US"): "NASDAQ",
        ("NVDA", "US"): "NASDAQ",
        ("600519", "CN"): "SSE",
        ("0700", "HK"): "HKEX",
    }

    def list_stocks(self, market: MarketCode | None = None) -> list[MarketStockSearchItem]:
        stocks: list[MarketStockSearchItem] = []

        for key in sorted(self._MOCK_QUOTES):
            symbol, stock_market = key
            if market is not None and stock_market != market:
                continue

            stocks.append(self._build_search_item(symbol=symbol, market=stock_market))

        return stocks

    def search_stocks(
        self,
        keyword: str | None = None,
        market: MarketCode | None = None,
    ) -> list[MarketStockSearchItem]:
        normalized_keyword = (keyword or "").strip().upper()

        stocks = self.list_stocks(market=market)
        if not normalized_keyword:
            return stocks

        return [
            stock
            for stock in stocks
            if normalized_keyword in stock.symbol.upper()
            or normalized_keyword in stock.name.upper()
        ]

    def get_snapshot(self, symbol: str, market: MarketCode) -> MarketSnapshot:
        normalized_symbol = self._normalize_symbol(symbol)
        quote = self._get_quote(symbol=normalized_symbol, market=market)

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

    def get_candles(
        self,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 30,
    ) -> list[MarketCandle]:
        snapshot = self.get_snapshot(symbol=symbol, market=market)
        normalized_limit = max(1, min(limit, 200))
        step = self._get_time_step(timeframe)

        candles: list[MarketCandle] = []
        now = datetime.now(UTC)

        for index in range(normalized_limit):
            reverse_index = normalized_limit - index - 1
            time = now - step * reverse_index

            close_price = self._mock_close_price(
                latest_price=snapshot.latest_price,
                previous_close=snapshot.previous_close,
                index=index,
                total=normalized_limit,
            )
            open_price = self._mock_open_price(
                close_price=close_price,
                previous_close=snapshot.previous_close,
                index=index,
            )
            high_price = round(max(open_price, close_price) * 1.006, 4)
            low_price = round(min(open_price, close_price) * 0.994, 4)
            volume = self._mock_volume(
                base_volume=snapshot.volume,
                index=index,
                total=normalized_limit,
            )

            candles.append(
                MarketCandle(
                    time=time,
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    close_price=close_price,
                    volume=volume,
                )
            )

        return candles

    def _build_search_item(
        self,
        symbol: str,
        market: MarketCode,
    ) -> MarketStockSearchItem:
        quote = self._get_quote(symbol=symbol, market=market)

        return MarketStockSearchItem(
            symbol=symbol,
            market=market,
            name=quote["name"],  # type: ignore[arg-type]
            currency=quote["currency"],  # type: ignore[arg-type]
            exchange=self._EXCHANGES.get((symbol, market)),
        )

    def _get_quote(self, symbol: str, market: MarketCode) -> dict[str, object]:
        normalized_symbol = self._normalize_symbol(symbol)
        key = (normalized_symbol, market)

        quote = self._MOCK_QUOTES.get(key)
        if quote is None:
            raise NotFoundException(
                message=f"mock market data not found for {market}:{normalized_symbol}"
            )

        return quote

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.strip().upper()

    def _get_time_step(self, timeframe: CandleTimeframe) -> timedelta:
        if timeframe == "5m":
            return timedelta(minutes=5)
        if timeframe == "1h":
            return timedelta(hours=1)
        return timedelta(days=1)

    def _mock_close_price(
        self,
        latest_price: float,
        previous_close: float,
        index: int,
        total: int,
    ) -> float:
        if total <= 1:
            return round(latest_price, 4)

        progress = index / (total - 1)
        base_price = previous_close + (latest_price - previous_close) * progress
        wave = ((index % 5) - 2) * latest_price * 0.001

        return round(base_price + wave, 4)

    def _mock_open_price(
        self,
        close_price: float,
        previous_close: float,
        index: int,
    ) -> float:
        direction = 1 if index % 2 == 0 else -1
        drift = previous_close * 0.001 * direction

        return round(close_price - drift, 4)

    def _mock_volume(
        self,
        base_volume: int,
        index: int,
        total: int,
    ) -> int:
        if total <= 1:
            return base_volume

        ratio = 0.75 + (index / total) * 0.35
        return int(base_volume * ratio)