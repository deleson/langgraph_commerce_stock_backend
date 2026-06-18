"""Tushare 行情 Provider。

Tushare 是当前生产环境 A 股数据的主要真实来源之一。本适配器只做三件事：
校验当前请求是否属于它支持的范围、调用 Tushare SDK、把返回行转换成项目统一的
MarketProviderCandle。它不负责入库、不负责技术指标、不负责策略判断。
"""

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
    """面向 A 股日 K 线的 Tushare 适配器。"""

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

        return await anyio.to_thread.run_sync(
            self._search_symbols_sync,
            keyword,
            limit,
        )

    async def list_symbols(
        self,
        *,
        market: MarketCode | None = None,
        limit: int | None = None,
    ) -> list[MarketSymbolCreate]:
        """低频拉取 Tushare 股票基础信息池。

        Tushare stock_basic 调用额度宝贵，因此该方法应由后台同步任务调用，
        不能放到普通用户名称搜索链路里反复触发。
        """

        if market is not None and market != "CN":
            return []

        return await anyio.to_thread.run_sync(
            self._list_symbols_sync,
            limit,
        )

    async def get_symbol(
        self,
        *,
        symbol: str,
        market: MarketCode,
    ) -> MarketSymbolCreate:
        if market != "CN":
            raise NotFoundException(message=f"tushare does not support market: {market}")

        normalized_symbol = symbol.strip().upper()
        return await anyio.to_thread.run_sync(
            self._get_symbol_sync,
            normalized_symbol,
        )

    def _search_symbols_sync(
        self,
        keyword: str,
        limit: int,
    ) -> list[MarketSymbolCreate]:
        normalized_keyword = keyword.strip().upper()
        if not normalized_keyword:
            return []

        pro = self._build_client()
        fields = self._stock_basic_fields()
        df = pro.stock_basic(
            exchange="",
            list_status="L",
            fields=fields,
        )

        if df is None or df.empty:
            return []

        matched_symbols: list[MarketSymbolCreate] = []
        for row in df.to_dict("records"):
            symbol = str(row.get("symbol") or "").strip().upper()
            ts_code = str(row.get("ts_code") or "").strip().upper()
            name = str(row.get("name") or "").strip()

            if (
                normalized_keyword not in symbol
                and normalized_keyword not in ts_code
                and normalized_keyword not in name.upper()
            ):
                continue

            matched_symbols.append(self._row_to_symbol(row))
            if len(matched_symbols) >= limit:
                break

        return matched_symbols

    def _list_symbols_sync(
        self,
        limit: int | None,
    ) -> list[MarketSymbolCreate]:
        pro = self._build_client()
        fields = self._stock_basic_fields()
        df = pro.stock_basic(
            exchange="",
            list_status="L",
            fields=fields,
        )

        if df is None or df.empty:
            return []

        rows = df.to_dict("records")
        if limit is not None:
            rows = rows[:limit]

        return [self._row_to_symbol(row) for row in rows]

    def _get_symbol_sync(
        self,
        symbol: str,
    ) -> MarketSymbolCreate:
        pro = self._build_client()
        provider_symbol = self._to_tushare_code(symbol)
        fields = self._stock_basic_fields()
        df = pro.stock_basic(
            ts_code=provider_symbol,
            list_status="L",
            fields=fields,
        )

        if df is None or df.empty:
            raise NotFoundException(message=f"tushare stock basic not found for CN:{symbol}")

        row = df.to_dict("records")[0]
        return self._row_to_symbol(row)

    async def get_candles(
        self,
        query: MarketCandleQuery,
    ) -> list[MarketProviderCandle]:
        """读取 Tushare 日 K 线。

        第一版只开放 CN 市场、1d 周期和 none 复权，是为了把生产链路先跑通。
        如果后续要支持前复权、后复权或更细周期，应先扩展这里的 Provider 能力，
        再扩展同步 API 和测试，而不是在策略层临时拼接。
        """

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
        """在线程中执行同步 SDK 调用，避免阻塞 FastAPI 事件循环。"""

        provider_symbol = self._to_tushare_code(query.symbol)

        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=query.limit * 3)

        pro = self._build_client()

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
        """把 Tushare 的单行数据转换成项目内部统一 K 线结构。"""

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

    def _row_to_symbol(
        self,
        row: dict[str, Any],
    ) -> MarketSymbolCreate:
        provider_symbol = str(row.get("ts_code") or "").strip().upper()
        symbol = str(row.get("symbol") or "").strip().upper()
        name = str(row.get("name") or symbol).strip()
        exchange = (
            str(row.get("exchange") or self._infer_exchange(provider_symbol))
            .strip()
            .upper()
        )
        currency = str(row.get("curr_type") or "CNY").strip().upper()

        if not symbol and provider_symbol:
            symbol = provider_symbol.split(".", maxsplit=1)[0]

        if not symbol:
            raise NotFoundException(message="tushare stock basic row missing symbol")

        return MarketSymbolCreate(
            symbol=symbol,
            market="CN",
            name=name or symbol,
            currency=currency or "CNY",
            exchange=exchange or self._infer_exchange(provider_symbol),
            provider_symbol=provider_symbol or self._to_tushare_code(symbol),
            list_status=str(row.get("list_status") or "").strip().upper() or None,
            source="tushare",
            is_active=True,
            raw_payload={
                str(key): value
                for key, value in row.items()
            },
        )

    def _build_client(
        self,
    ):
        import tushare as ts

        settings = get_settings()
        if settings.tushare_token is None:
            raise BadRequestException(message="TUSHARE_TOKEN is required")

        token = settings.tushare_token.get_secret_value()
        if not token:
            raise BadRequestException(message="TUSHARE_TOKEN is required")

        return ts.pro_api(token)

    def _stock_basic_fields(
        self,
    ) -> str:
        return "ts_code,symbol,name,exchange,curr_type,list_status"

    def _to_tushare_code(
        self,
        symbol: str,
    ) -> str:
        """把项目内的 6 位股票代码转换成 Tushare 使用的交易所后缀格式。"""

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
