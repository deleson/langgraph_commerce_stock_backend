from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import anyio

from app.core.config import get_settings
from app.core.exceptions import BadRequestException, NotFoundException
from app.schemas.market_data import (
    CandleTimeframe,
    MarketCandleQuery,
    MarketCode,
    MarketProviderCandle,
    MarketSymbolCreate,
)
from app.services.market_providers.base import MarketDataProvider


class TushareProvider(MarketDataProvider):
    provider_name = "tushare"

    @property
    def supported_markets(self) -> set[MarketCode]:
        return {"CN"}

    @property
    def supported_timeframes(self) -> set[CandleTimeframe]:
        return {"1d"}

    async def search_symbols(
        self,
        *,
        keyword: str | None = None,
        market: MarketCode | None = None,
        limit: int = 50,
    ) -> list[MarketSymbolCreate]:
        if market is not None and market != "CN":
            return []

        if not keyword:
            return []

        normalized_keyword = keyword.strip().upper()
        if not normalized_keyword.isdigit():
            return []

        try:
            symbol = await self.get_symbol(
                symbol=normalized_keyword,
                market="CN",
            )
        except NotFoundException:
            return []

        return [symbol][:limit]

    async def get_symbol(
        self,
        *,
        symbol: str,
        market: MarketCode,
    ) -> MarketSymbolCreate:
        if market != "CN":
            raise NotFoundException(message=f"tushare does not support market: {market}")

        normalized_symbol = symbol.strip().upper()
        provider_symbol = self._to_tushare_code(normalized_symbol)

        return MarketSymbolCreate(
            symbol=normalized_symbol,
            market="CN",
            name=normalized_symbol,
            currency="CNY",
            exchange=self._infer_exchange(provider_symbol),
            provider_symbol=provider_symbol,
            source="tushare",
            is_active=True,
        )

    async def get_candles(
        self,
        query: MarketCandleQuery,
    ) -> list[MarketProviderCandle]:
        if query.market != "CN":
            raise BadRequestException(message="tushare only supports CN market")

        if query.timeframe != "1d":
            raise BadRequestException(message="tushare provider currently only supports 1d candles")

        if query.adjust_type != "none":
            raise BadRequestException(
                message="tushare minimal provider currently only supports non-adjusted candles"
            )

        return await anyio.to_thread.run_sync(
            self._get_candles_sync,
            query,
        )

    def _get_candles_sync(
        self,
        query: MarketCandleQuery,
    ) -> list[MarketProviderCandle]:
        import tushare as ts

        settings = get_settings()
        if settings.tushare_token is None:
            raise BadRequestException(message="TUSHARE_TOKEN is required")

        token = settings.tushare_token.get_secret_value()
        if not token:
            raise BadRequestException(message="TUSHARE_TOKEN is required")

        provider_symbol = self._to_tushare_code(query.symbol)

        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=query.limit * 3)

        pro = ts.pro_api(token)

        df = pro.daily(
            ts_code=provider_symbol,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )

        if df is None or df.empty:
            raise NotFoundException(
                message=f"tushare daily data not found for CN:{query.symbol}"
            )

        candles: list[MarketProviderCandle] = []

        for row in df.to_dict("records"):
            candles.append(self._row_to_candle(row=row, query=query))

        candles.sort(key=lambda candle: candle.candle_time)

        return candles[-query.limit :]

    def _row_to_candle(
        self,
        *,
        row: dict[str, Any],
        query: MarketCandleQuery,
    ) -> MarketProviderCandle:
        return MarketProviderCandle(
            symbol=query.symbol,
            market=query.market,
            timeframe=query.timeframe,
            candle_time=self._parse_trade_date(str(row["trade_date"])),
            open_price=self._to_decimal(row.get("open")),
            high_price=self._to_decimal(row.get("high")),
            low_price=self._to_decimal(row.get("low")),
            close_price=self._to_decimal(row.get("close")),
            volume=self._to_int(row.get("vol")),
            amount=self._to_optional_decimal(row.get("amount")),
            source="tushare",
            is_adjusted=False,
            adjust_type="none",
        )

    def _to_tushare_code(
        self,
        symbol: str,
    ) -> str:
        normalized_symbol = symbol.strip().upper()

        if normalized_symbol.endswith((".SH", ".SZ")):
            return normalized_symbol

        if normalized_symbol.startswith(("6", "9")):
            return f"{normalized_symbol}.SH"

        return f"{normalized_symbol}.SZ"

    def _infer_exchange(
        self,
        provider_symbol: str,
    ) -> str:
        if provider_symbol.endswith(".SH"):
            return "SSE"
        return "SZSE"

    def _parse_trade_date(
        self,
        value: str,
    ) -> datetime:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=UTC)

    def _to_decimal(
        self,
        value: Any,
    ) -> Decimal:
        if value is None or value == "":
            return Decimal("0")
        return Decimal(str(value))

    def _to_optional_decimal(
        self,
        value: Any,
    ) -> Decimal | None:
        if value is None or value == "":
            return None
        return Decimal(str(value))

    def _to_int(
        self,
        value: Any,
    ) -> int:
        if value is None or value == "":
            return 0
        return int(Decimal(str(value)))