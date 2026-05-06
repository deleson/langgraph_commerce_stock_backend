from datetime import UTC, datetime, timedelta
from decimal import Decimal

import anyio

from app.core.exceptions import BadRequestException, NotFoundException
from app.schemas.market_data import (
    CandleTimeframe,
    MarketCandleQuery,
    MarketCode,
    MarketProviderCandle,
    MarketSymbolCreate,
)
from app.services.market_providers.base import MarketDataProvider


class BaoStockProvider(MarketDataProvider):
    provider_name = "baostock"

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
            raise NotFoundException(message=f"baostock does not support market: {market}")

        return await anyio.to_thread.run_sync(
            self._get_symbol_sync,
            symbol,
        )

    async def get_candles(
        self,
        query: MarketCandleQuery,
    ) -> list[MarketProviderCandle]:
        if query.market != "CN":
            raise BadRequestException(message="baostock only supports CN market")

        if query.timeframe != "1d":
            raise BadRequestException(message="baostock provider currently only supports 1d candles")

        return await anyio.to_thread.run_sync(
            self._get_candles_sync,
            query,
        )

    def _get_symbol_sync(
        self,
        symbol: str,
    ) -> MarketSymbolCreate:
        import baostock as bs

        normalized_symbol = symbol.strip().upper()
        provider_symbol = self._to_baostock_code(normalized_symbol)

        login_result = bs.login()
        if login_result.error_code != "0":
            raise BadRequestException(message=f"baostock login failed: {login_result.error_msg}")

        try:
            name = normalized_symbol

            if hasattr(bs, "query_stock_basic"):
                result = bs.query_stock_basic(code=provider_symbol)
                if result.error_code == "0" and result.next():
                    row = dict(zip(result.fields, result.get_row_data(), strict=False))
                    name = row.get("code_name") or normalized_symbol

            return MarketSymbolCreate(
                symbol=normalized_symbol,
                market="CN",
                name=name,
                currency="CNY",
                exchange=self._infer_exchange(provider_symbol),
                provider_symbol=provider_symbol,
                source="baostock",
                is_active=True,
            )
        finally:
            bs.logout()

    def _get_candles_sync(
        self,
        query: MarketCandleQuery,
    ) -> list[MarketProviderCandle]:
        import baostock as bs

        provider_symbol = self._to_baostock_code(query.symbol)
        adjustflag = self._to_baostock_adjustflag(query.adjust_type)

        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=query.limit * 3)

        login_result = bs.login()
        if login_result.error_code != "0":
            raise BadRequestException(message=f"baostock login failed: {login_result.error_msg}")

        try:
            fields = ",".join(
                [
                    "date",
                    "code",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "amount",
                    "adjustflag",
                    "tradestatus",
                ]
            )

            result = bs.query_history_k_data_plus(
                provider_symbol,
                fields,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                frequency="d",
                adjustflag=adjustflag,
            )

            if result.error_code != "0":
                raise BadRequestException(message=f"baostock query failed: {result.error_msg}")

            candles: list[MarketProviderCandle] = []

            while result.next():
                row = dict(zip(result.fields, result.get_row_data(), strict=False))

                if row.get("tradestatus") not in (None, "", "1"):
                    continue

                if not row.get("date"):
                    continue

                candles.append(
                    MarketProviderCandle(
                        symbol=query.symbol,
                        market=query.market,
                        timeframe=query.timeframe,
                        candle_time=self._parse_candle_time(row["date"]),
                        open_price=self._to_decimal(row.get("open")),
                        high_price=self._to_decimal(row.get("high")),
                        low_price=self._to_decimal(row.get("low")),
                        close_price=self._to_decimal(row.get("close")),
                        volume=self._to_int(row.get("volume")),
                        amount=self._to_optional_decimal(row.get("amount")),
                        source="baostock",
                        is_adjusted=query.adjust_type != "none",
                        adjust_type=query.adjust_type,
                    )
                )

            return candles[-query.limit :]
        finally:
            bs.logout()

    def _to_baostock_code(
        self,
        symbol: str,
    ) -> str:
        normalized_symbol = symbol.strip().upper()

        if normalized_symbol.startswith(("SH.", "SZ.")):
            return normalized_symbol.lower()

        if normalized_symbol.startswith(("6", "9")):
            return f"sh.{normalized_symbol}"

        return f"sz.{normalized_symbol}"

    def _infer_exchange(
        self,
        provider_symbol: str,
    ) -> str:
        if provider_symbol.startswith("sh."):
            return "SSE"
        return "SZSE"

    def _to_baostock_adjustflag(
        self,
        adjust_type: str,
    ) -> str:
        mapping = {
            "none": "3",
            "qfq": "2",
            "hfq": "1",
        }
        return mapping.get(adjust_type, "3")

    def _parse_candle_time(
        self,
        value: str,
    ) -> datetime:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)

    def _to_decimal(
        self,
        value: str | None,
    ) -> Decimal:
        if value is None or value == "":
            return Decimal("0")
        return Decimal(str(value))

    def _to_optional_decimal(
        self,
        value: str | None,
    ) -> Decimal | None:
        if value is None or value == "":
            return None
        return Decimal(str(value))

    def _to_int(
        self,
        value: str | None,
    ) -> int:
        if value is None or value == "":
            return 0
        return int(Decimal(str(value)))