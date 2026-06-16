"""行情聚合服务。

MarketService 面向 API 层提供搜索、报价、K 线、基础指标和 Overview 聚合能力。
它优先读取数据库中的真实同步数据；在没有数据库连接或数据库没有数据时，才使用
MockMarketDataService 作为开发/测试降级来源。
"""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_candle import MarketCandle as MarketCandleModel
from app.models.market_symbol import MarketSymbol
from app.repositories.market_repo import AsyncMarketRepository
from app.schemas.market import (
    CandleTimeframe,
    MarketCandle,
    MarketCandleListResponse,
    MarketCode,
    MarketIndicatorResponse,
    MarketOverviewResponse,
    MarketQuoteResponse,
    MarketStockSearchItem,
)
from app.schemas.strategy_signal import StrategySignalResponse
from app.services.strategy_signal_query_service import StrategySignalQueryService
from app.schemas.market_data import AdjustType, MarketCandleQuery, MarketDataSource
from app.schemas.stock_analysis import MarketSnapshot
from app.schemas.technical_indicator import TechnicalIndicatorResponse
from app.services.indicator_service import IndicatorService
from app.services.market_data_service import MockMarketDataService
from app.services.market_data_sync_service import MarketDataSyncService
from app.services.technical_indicator_query_service import TechnicalIndicatorQueryService
from app.repositories.market_data_sync_repo import AsyncMarketDataSyncRepository
from app.schemas.market_data_sync import (
    MarketDataQualityReport,
    MarketDataSyncStatusResponse,
)
from app.services.market_data_quality_report_service import MarketDataQualityReportService

class MarketService:
    """行情 API 的业务聚合入口。

    这一层不直接调用 Tushare / BaoStock；真实行情先由 MarketDataSyncService 入库，
    再由这里读取。这样查询 API、技术指标、策略信号和 AI 图看到的是同一套数据。
    """

    def __init__(
            self,
            db: AsyncSession | None = None,
            market_data_service: MockMarketDataService | None = None,
            indicator_service: IndicatorService | None = None,
            repository: AsyncMarketRepository | None = None,
            sync_repository: AsyncMarketDataSyncRepository | None = None,
            sync_service: MarketDataSyncService | None = None,
    ) -> None:
        self.db = db
        self.market_data_service = market_data_service or MockMarketDataService()
        self.indicator_service = indicator_service or IndicatorService()
        self.repository = repository or (AsyncMarketRepository(db) if db is not None else None)
        self.sync_repository = sync_repository or (
            AsyncMarketDataSyncRepository(db) if db is not None else None
        )
        self.sync_service = sync_service
    async def search_stocks(
        self,
        keyword: str | None = None,
        market: MarketCode | None = None,
    ) -> list[MarketStockSearchItem]:
        """搜索股票。

        如果数据库已有同步过的股票基础信息，优先返回数据库结果；否则返回 Mock
        股票池，保证开发阶段 API 不会因为缺少真实数据而不可用。
        """

        if self.repository is not None:
            db_symbols = await self.repository.list_symbols(
                market=market,
                keyword=keyword,
                active_only=True,
                limit=50,
            )

            if db_symbols:
                db_symbols = await self._refresh_search_symbols_if_needed(
                    symbols=db_symbols,
                    keyword=keyword,
                    market=market,
                )
                return [
                    self._build_search_item_from_model(symbol)
                    for symbol in db_symbols
                ]

        provider_symbols = await self._search_symbols_from_provider(
            keyword=keyword,
            market=market,
        )
        if provider_symbols:
            return [
                self._build_search_item_from_model(symbol)
                for symbol in provider_symbols
            ]

        return self.market_data_service.search_stocks(
            keyword=keyword,
            market=market,
        )

    async def _search_symbols_from_provider(
        self,
        *,
        keyword: str | None,
        market: MarketCode | None,
    ) -> list[MarketSymbol]:
        if self.sync_service is not None:
            sync_service = self.sync_service
        elif self.db is not None:
            sync_service = MarketDataSyncService(self.db)
        else:
            return []

        return await sync_service.search_symbols(
            keyword=keyword,
            market=market,
            limit=50,
            persist=True,
        )

    async def _refresh_search_symbols_if_needed(
        self,
        *,
        symbols: list[MarketSymbol],
        keyword: str | None,
        market: MarketCode | None,
    ) -> list[MarketSymbol]:
        """数据库命中但基础信息像占位数据时，用 Provider 尝试刷新。

        早期同步或 mock 降级可能只保存了代码，导致前端搜索结果没有真实名称。
        搜索接口本来就是用户主动查询入口，因此这里允许做一次轻量 Provider 搜索；
        如果 Provider 不可用，继续返回数据库结果，避免影响基础可用性。
        """

        if not keyword or not self._symbols_need_provider_refresh(symbols):
            return symbols

        provider_symbols = await self._search_symbols_from_provider(
            keyword=keyword,
            market=market,
        )
        if not provider_symbols:
            return symbols

        merged_symbols = {
            (symbol.market, symbol.symbol): symbol
            for symbol in symbols
        }
        for symbol in provider_symbols:
            merged_symbols[(symbol.market, symbol.symbol)] = symbol

        return sorted(
            merged_symbols.values(),
            key=lambda item: (item.market, item.symbol),
        )[:50]

    def _symbols_need_provider_refresh(
        self,
        symbols: list[MarketSymbol],
    ) -> bool:
        for symbol in symbols:
            name = (symbol.name or "").strip()
            if not name:
                return True
            if name.upper() == symbol.symbol.upper():
                return True
            if symbol.source == "mock":
                return True
        return False

    async def get_quote(
        self,
        symbol: str,
        market: MarketCode,
    ) -> MarketQuoteResponse:
        """读取单只股票报价快照。

        数据库报价来自最近一根 K 线；Mock 报价只用于开发、测试或数据缺失降级。
        """

        if self.repository is not None:
            db_quote = await self._get_quote_from_db(
                symbol=symbol,
                market=market,
            )
            if db_quote is not None:
                return db_quote

        snapshot = self.market_data_service.get_snapshot(
            symbol=symbol,
            market=market,
        )

        return self._build_quote_response(snapshot)

    async def get_candles(
        self,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 30,
    ) -> MarketCandleListResponse:
        if self.repository is not None:
            db_candles = await self._get_candles_from_db(
                symbol=symbol,
                market=market,
                timeframe=timeframe,
                limit=limit,
            )
            if db_candles is not None:
                return db_candles

        candles = self.market_data_service.get_candles(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
        )

        normalized_symbol = symbol.strip().upper()

        return MarketCandleListResponse(
            symbol=normalized_symbol,
            market=market,
            timeframe=timeframe,
            limit=len(candles),
            candles=candles,
            source="mock",
        )

    async def get_indicators(
            self,
            symbol: str,
            market: MarketCode,
    ) -> MarketIndicatorResponse:
        quote = await self.get_quote(
            symbol=symbol,
            market=market,
        )

        snapshot = MarketSnapshot(
            symbol=quote.symbol,
            market=quote.market,
            name=quote.name,
            currency=quote.currency,
            latest_price=quote.latest_price,
            previous_close=quote.previous_close,
            open_price=quote.open_price,
            high_price=quote.high_price,
            low_price=quote.low_price,
            volume=quote.volume,
            as_of=quote.as_of,
        )

        indicators = self.indicator_service.calculate(snapshot)

        return MarketIndicatorResponse(
            symbol=snapshot.symbol,
            market=snapshot.market,
            price_change=indicators.price_change,
            price_change_percent=indicators.price_change_percent,
            moving_average_5=indicators.moving_average_5,
            moving_average_20=indicators.moving_average_20,
            volatility_level=indicators.volatility_level,
            trend=indicators.trend,
            source=quote.source,
        )

    async def get_overview(
        self,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 30,
        *,
        include_technical_indicators: bool = False,
        technical_indicator_limit: int = 120,
        adjust_type: AdjustType = "none",
        technical_indicator_source: MarketDataSource | None = None,
        include_data_quality: bool = False,
        include_sync_status: bool = False,
        data_quality_source: MarketDataSource | None = None,
        data_quality_min_required: int = 1,
        data_quality_stale_after_days: int | None = None,
        include_strategy_signal: bool = False,
        strategy_signal_limit: int = 120,
        strategy_signal_source: MarketDataSource | None = None,
        strategy_signal_include_detail: bool = True,
        strategy_signal_min_required: int = 35,
        strategy_signal_stale_after_days: int | None = None,
    ) -> MarketOverviewResponse:
        """聚合单只股票的行情总览。

        Overview 可以按开关附加技术指标、数据质量、同步状态和策略信号。
        这些附加项都通过独立 Service 获取，避免把量化公式和数据质量逻辑写在
        MarketService 本身里。
        """

        await self._ensure_candles_for_overview(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            include_technical_indicators=include_technical_indicators,
            technical_indicator_limit=technical_indicator_limit,
            include_strategy_signal=include_strategy_signal,
            strategy_signal_limit=strategy_signal_limit,
            adjust_type=adjust_type,
        )

        quote = await self.get_quote(symbol=symbol, market=market)
        indicators = await self.get_indicators(symbol=symbol, market=market)
        candles_response = await self.get_candles(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
        )

        technical_indicators = await self._get_technical_indicators_for_overview(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            include_technical_indicators=include_technical_indicators,
            technical_indicator_limit=technical_indicator_limit,
            adjust_type=adjust_type,
            technical_indicator_source=technical_indicator_source,
        )

        data_quality = await self._get_data_quality_for_overview(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            include_data_quality=include_data_quality,
            adjust_type=adjust_type,
            data_quality_source=data_quality_source,
            data_quality_min_required=data_quality_min_required,
            data_quality_stale_after_days=data_quality_stale_after_days,
        )

        sync_status = await self._get_sync_status_for_overview(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            include_sync_status=include_sync_status,
            adjust_type=adjust_type,
            preferred_source=data_quality_source,
            quote_source=quote.source,
            candles_source=candles_response.source,
        )

        strategy_signal = await self._get_strategy_signal_for_overview(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            include_strategy_signal=include_strategy_signal,
            strategy_signal_limit=strategy_signal_limit,
            adjust_type=adjust_type,
            strategy_signal_source=strategy_signal_source,
            strategy_signal_include_detail=strategy_signal_include_detail,
            strategy_signal_min_required=strategy_signal_min_required,
            strategy_signal_stale_after_days=strategy_signal_stale_after_days,
        )

        return MarketOverviewResponse(
            quote=quote,
            indicators=indicators,
            candles=candles_response.candles,
            technical_indicators=technical_indicators,
            data_quality=data_quality,
            sync_status=sync_status,
            strategy_signal=strategy_signal,
        )

    async def _ensure_candles_for_overview(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe,
        limit: int,
        include_technical_indicators: bool,
        technical_indicator_limit: int,
        include_strategy_signal: bool,
        strategy_signal_limit: int,
        adjust_type: AdjustType,
    ) -> None:
        """详情页查询前，尝试把已搜索到的股票 K 线补齐。

        股票搜索只负责基础信息缓存；如果用户马上进入详情页，而数据库还没有 K 线，
        这里会按当前 Provider 做一次同步，再让 overview 读取统一的入库数据。
        同步失败时不抛给用户，保留原有 mock 降级能力。
        """

        if self.repository is None:
            return

        normalized_symbol = symbol.strip().upper()
        market_symbol = await self.repository.get_symbol(
            symbol=normalized_symbol,
            market=market,
        )
        if market_symbol is None:
            return

        existing_candles = await self.repository.list_candles(
            MarketCandleQuery(
                symbol=normalized_symbol,
                market=market,
                timeframe=timeframe,
                limit=1,
                adjust_type=adjust_type,
                source=None,
            )
        )
        if existing_candles:
            return

        sync_limit = limit
        if include_technical_indicators:
            sync_limit = max(sync_limit, technical_indicator_limit)
        if include_strategy_signal:
            sync_limit = max(sync_limit, strategy_signal_limit)

        try:
            sync_service = self.sync_service or (
                MarketDataSyncService(self.db) if self.db is not None else None
            )
            if sync_service is None:
                return

            await sync_service.sync_candles(
                symbol=normalized_symbol,
                market=market,
                timeframe=timeframe,
                limit=sync_limit,
                adjust_type=adjust_type,
            )
        except Exception:
            # 查询接口不能因为 Provider 临时失败完全不可用；后续仍走原有 mock 降级。
            return

    async def _get_quote_from_db(
        self,
        symbol: str,
        market: MarketCode,
    ) -> MarketQuoteResponse | None:
        if self.repository is None:
            return None

        normalized_symbol = symbol.strip().upper()

        market_symbol = await self.repository.get_symbol(
            symbol=normalized_symbol,
            market=market,
        )
        candles = await self.repository.list_candles(
            MarketCandleQuery(
                symbol=normalized_symbol,
                market=market,
                timeframe="1d",
                limit=2,
                adjust_type="none",
                source=None,
            )
        )

        if market_symbol is None or not candles:
            return None

        latest = candles[-1]
        previous = candles[-2] if len(candles) >= 2 else latest

        latest_price = self._decimal_to_float(latest.close_price)
        previous_close = self._decimal_to_float(previous.close_price)
        price_change = round(latest_price - previous_close, 4)
        price_change_percent = self._safe_percent(
            numerator=price_change,
            denominator=previous_close,
        )

        return MarketQuoteResponse(
            symbol=market_symbol.symbol,
            market=market_symbol.market,
            name=market_symbol.name,
            currency=market_symbol.currency,
            latest_price=latest_price,
            previous_close=previous_close,
            open_price=self._decimal_to_float(latest.open_price),
            high_price=self._decimal_to_float(latest.high_price),
            low_price=self._decimal_to_float(latest.low_price),
            volume=latest.volume,
            price_change=price_change,
            price_change_percent=price_change_percent,
            as_of=latest.candle_time,
            source=latest.source,
        )

    async def _get_candles_from_db(
        self,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe,
        limit: int,
    ) -> MarketCandleListResponse | None:
        if self.repository is None:
            return None

        normalized_symbol = symbol.strip().upper()

        candles = await self.repository.list_candles(
            MarketCandleQuery(
                symbol=normalized_symbol,
                market=market,
                timeframe=timeframe,
                limit=limit,
                adjust_type="none",
                source=None,
            )
        )

        if not candles:
            return None

        return MarketCandleListResponse(
            symbol=normalized_symbol,
            market=market,
            timeframe=timeframe,
            limit=len(candles),
            candles=[
                self._build_candle_response(candle)
                for candle in candles
            ],
            source=candles[-1].source,
        )

    async def _get_market_snapshot(
        self,
        symbol: str,
        market: MarketCode,
    ) -> MarketSnapshot:
        db_quote = await self._get_quote_from_db(
            symbol=symbol,
            market=market,
        )

        if db_quote is not None:
            return MarketSnapshot(
                symbol=db_quote.symbol,
                market=db_quote.market,
                name=db_quote.name,
                currency=db_quote.currency,
                latest_price=db_quote.latest_price,
                previous_close=db_quote.previous_close,
                open_price=db_quote.open_price,
                high_price=db_quote.high_price,
                low_price=db_quote.low_price,
                volume=db_quote.volume,
                as_of=db_quote.as_of,
            )

        return self.market_data_service.get_snapshot(
            symbol=symbol,
            market=market,
        )

    def _build_search_item_from_model(
        self,
        symbol: MarketSymbol,
    ) -> MarketStockSearchItem:
        return MarketStockSearchItem(
            symbol=symbol.symbol,
            market=symbol.market,
            name=symbol.name,
            currency=symbol.currency,
            exchange=symbol.exchange,
            source=symbol.source,
        )

    def _build_candle_response(
        self,
        candle: MarketCandleModel,
    ) -> MarketCandle:
        return MarketCandle(
            time=candle.candle_time,
            open_price=self._decimal_to_float(candle.open_price),
            high_price=self._decimal_to_float(candle.high_price),
            low_price=self._decimal_to_float(candle.low_price),
            close_price=self._decimal_to_float(candle.close_price),
            volume=candle.volume,
        )

    def _build_quote_response(
        self,
        snapshot: MarketSnapshot,
    ) -> MarketQuoteResponse:
        price_change = round(
            snapshot.latest_price - snapshot.previous_close,
            4,
        )
        price_change_percent = self._safe_percent(
            numerator=price_change,
            denominator=snapshot.previous_close,
        )

        return MarketQuoteResponse(
            symbol=snapshot.symbol,
            market=snapshot.market,
            name=snapshot.name,
            currency=snapshot.currency,
            latest_price=snapshot.latest_price,
            previous_close=snapshot.previous_close,
            open_price=snapshot.open_price,
            high_price=snapshot.high_price,
            low_price=snapshot.low_price,
            volume=snapshot.volume,
            price_change=price_change,
            price_change_percent=price_change_percent,
            as_of=snapshot.as_of,
            source="mock",
        )

    def _decimal_to_float(
        self,
        value: Decimal,
    ) -> float:
        return float(value)

    def _safe_percent(
        self,
        numerator: float,
        denominator: float,
    ) -> float:
        if denominator == 0:
            return 0.0

        return round(numerator / denominator * 100, 4)

    async def _get_technical_indicators_for_overview(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe,
        include_technical_indicators: bool,
        technical_indicator_limit: int,
        adjust_type: AdjustType,
        technical_indicator_source: MarketDataSource | None,
    ) -> TechnicalIndicatorResponse | None:
        """按开关为 Overview 附加技术指标。

        没有数据库连接时直接返回 None，因为完整技术指标必须基于已入库 K 线。
        """

        if not include_technical_indicators:
            return None

        if self.db is None:
            return None

        return await TechnicalIndicatorQueryService(self.db).get_summary(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=technical_indicator_limit,
            adjust_type=adjust_type,
            source=technical_indicator_source,
        )

    async def _get_data_quality_for_overview(
            self,
            *,
            symbol: str,
            market: MarketCode,
            timeframe: CandleTimeframe,
            limit: int,
            include_data_quality: bool,
            adjust_type: AdjustType,
            data_quality_source: MarketDataSource | None,
            data_quality_min_required: int,
            data_quality_stale_after_days: int | None,
    ) -> MarketDataQualityReport | None:
        """按开关为 Overview 附加数据质量报告。"""

        if not include_data_quality:
            return None

        if self.db is None:
            return None

        return await MarketDataQualityReportService(self.db).get_quality_report(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            adjust_type=adjust_type,
            source=data_quality_source,
            min_required=data_quality_min_required,
            stale_after_days=data_quality_stale_after_days,
        )

    async def _get_sync_status_for_overview(
            self,
            *,
            symbol: str,
            market: MarketCode,
            timeframe: CandleTimeframe,
            include_sync_status: bool,
            adjust_type: AdjustType,
            preferred_source: MarketDataSource | None,
            quote_source: str,
            candles_source: str,
    ) -> MarketDataSyncStatusResponse | None:
        """按开关为 Overview 附加最近同步状态。"""

        if not include_sync_status:
            return None

        if self.sync_repository is None:
            return None

        source = (
                preferred_source
                or self._normalize_market_data_source(candles_source)
                or self._normalize_market_data_source(quote_source)
        )

        if source is None:
            return None

        status = await self.sync_repository.get_status(
            symbol=symbol.strip().upper(),
            market=market,
            timeframe=timeframe,
            source=source,
            adjust_type=adjust_type,
        )

        if status is None:
            return None

        return MarketDataSyncStatusResponse.model_validate(status)

    def _normalize_market_data_source(
            self,
            source: str | None,
    ) -> MarketDataSource | None:
        """把响应里的 source 文本收敛成 Schema 允许的数据源枚举。"""

        allowed_sources = {
            "mock",
            "baostock",
            "akshare",
            "tushare",
            "alpha_vantage",
            "polygon",
        }

        if source in allowed_sources:
            return source

        return None

    async def _get_strategy_signal_for_overview(
            self,
            *,
            symbol: str,
            market: MarketCode,
            timeframe: CandleTimeframe,
            include_strategy_signal: bool,
            strategy_signal_limit: int,
            adjust_type: AdjustType,
            strategy_signal_source: MarketDataSource | None,
            strategy_signal_include_detail: bool,
            strategy_signal_min_required: int,
            strategy_signal_stale_after_days: int | None,
    ) -> StrategySignalResponse | None:
        """按开关为 Overview 附加策略信号。

        策略信号会再次读取技术指标和数据质量报告，保证返回的信号包含完整的
        rule_results 和 input_snapshot，便于前端展示和后续审计。
        """

        if not include_strategy_signal:
            return None

        if self.db is None:
            return None

        return await StrategySignalQueryService(self.db).get_signal(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=strategy_signal_limit,
            adjust_type=adjust_type,
            source=strategy_signal_source,
            include_detail=strategy_signal_include_detail,
            min_required=strategy_signal_min_required,
            stale_after_days=strategy_signal_stale_after_days,
        )
