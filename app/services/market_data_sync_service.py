"""行情同步服务。

本服务负责把外部 Provider 的股票信息和 K 线同步到数据库。它处在“外部行情源”
和“内部量化计算”之间，所以必须先完成数据质量检查，再写入 market_symbols /
market_candles / sync_status / sync_logs。后续技术指标、策略信号、回测和纸面交易
都依赖这里落库后的稳定数据。
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import BadRequestException
from app.models.market_candle import MarketCandle
from app.models.market_data_sync_log import MarketDataSyncLog
from app.models.market_symbol import MarketSymbol
from app.repositories.market_data_sync_repo import AsyncMarketDataSyncRepository
from app.repositories.market_repo import AsyncMarketRepository
from app.schemas.market_data import (
    AdjustType,
    CandleTimeframe,
    MarketCandleQuery,
    MarketCode,
)
from app.schemas.market_data_sync import (
    MarketDataSyncLogCreate,
    MarketDataSyncLogUpdate,
    MarketDataSyncStatusCreate,
)
from app.services.market_data_quality_service import (
    MarketDataQualityCheckResult,
    MarketDataQualityService,
)
from app.services.market_symbol_sync_service import MarketSymbolSyncService
from app.services.market_providers import (
    BaoStockProvider,
    MarketDataProvider,
    MockMarketDataProvider,
    TushareProvider,
)


class MarketDataSyncService:
    """协调 Provider、数据质量服务和 Repository 的行情同步编排器。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        provider: MarketDataProvider | None = None,
        provider_name: str | None = None,
        repository: AsyncMarketRepository | None = None,
        sync_repository: AsyncMarketDataSyncRepository | None = None,
        quality_service: MarketDataQualityService | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncMarketRepository(db)
        self.sync_repository = sync_repository or AsyncMarketDataSyncRepository(db)
        self.quality_service = quality_service or MarketDataQualityService()
        self.provider = provider or self._build_provider(provider_name)

    async def sync_symbol(
        self,
        *,
        symbol: str,
        market: MarketCode,
    ) -> MarketSymbol:
        """同步单只股票基础信息。

        股票基础信息先落库，K 线同步时才能把 candle 关联到 symbol_id。
        """

        return await MarketSymbolSyncService(
            self.db,
            provider=self.provider,
            repository=self.repository,
        ).sync_symbol(
            symbol=symbol,
            market=market,
        )

    async def search_symbols(
        self,
        *,
        keyword: str | None = None,
        market: MarketCode | None = None,
        limit: int = 50,
        persist: bool = True,
    ) -> list[MarketSymbol]:
        """通过已配置的 Provider 搜索股票标的，并可选择缓存结果。

        这样前端搜索只需要发起一次后端请求：API 调用方不需要先搜索、
        同步股票标的，然后再搜索一次。
        """

        return await MarketSymbolSyncService(
            self.db,
            provider=self.provider,
            repository=self.repository,
        ).search_symbols(
            keyword=keyword,
            market=market,
            limit=limit,
            persist=persist,
        )

    async def sync_candles(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int | None = None,
        adjust_type: AdjustType = "none",
    ) -> list[MarketCandle]:
        """同步单只股票 K 线。

        业务流程：
        1. 读取当前 Provider；
        2. 拉取 Provider 原始 K 线；
        3. 用 MarketDataQualityService 标准化、去重、校验；
        4. upsert 到 market_candles；
        5. 写同步状态和同步日志。

        这一步只负责“数据入库”，不计算策略信号，也不判断买卖。
        """

        settings = get_settings()
        sync_limit = limit or settings.market_data_candle_sync_limit
        normalized_symbol = symbol.strip().upper()
        source = self.provider.provider_name
        started_at = datetime.now(UTC)

        if sync_limit <= 0:
            raise BadRequestException(message="market candle sync limit must be greater than 0")

        sync_log = await self._create_running_log(
            symbol=normalized_symbol,
            market=market,
            timeframe=timeframe,
            source=source,
            adjust_type=adjust_type,
            started_at=started_at,
        )

        market_symbol: MarketSymbol | None = None

        try:
            market_symbol = await self.sync_symbol(
                symbol=normalized_symbol,
                market=market,
            )

            query = MarketCandleQuery(
                symbol=market_symbol.symbol,
                market=market,
                timeframe=timeframe,
                limit=sync_limit,
                adjust_type=adjust_type,
                source=source,
            )

            provider_candles = await self.provider.get_candles(query)

            # Provider 返回的数据不能直接入库：先统一 UTC 时间、价格精度、去重，
            # 再检查空数据、数量不足等问题，避免下游指标被脏数据污染。
            candle_payloads, quality_result = self.quality_service.inspect_provider_candles(
                provider_candles,
                symbol_id=market_symbol.id,
                min_required=sync_limit,
            )

            saved_candles = await self.repository.upsert_candles(candle_payloads)

            await self._finish_success_log_and_status(
                sync_log=sync_log,
                symbol_id=market_symbol.id,
                symbol=market_symbol.symbol,
                market=market,
                timeframe=timeframe,
                source=source,
                adjust_type=adjust_type,
                fetched_count=len(provider_candles),
                normalized_count=len(candle_payloads),
                saved_count=len(saved_candles),
                quality_result=quality_result,
                started_at=started_at,
            )

            return saved_candles

        except Exception as exc:
            await self._finish_failed_log_and_status(
                sync_log=sync_log,
                symbol_id=market_symbol.id if market_symbol is not None else None,
                symbol=market_symbol.symbol if market_symbol is not None else normalized_symbol,
                market=market,
                timeframe=timeframe,
                source=source,
                adjust_type=adjust_type,
                error_message=str(exc),
                started_at=started_at,
            )
            raise

    async def sync_symbols(
        self,
        *,
        symbols: Sequence[str],
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int | None = None,
        adjust_type: AdjustType = "none",
    ) -> dict[str, int]:
        """批量同步多只股票 K 线，返回每只股票最终保存的 K 线数量。"""

        result: dict[str, int] = {}

        for symbol in symbols:
            candles = await self.sync_candles(
                symbol=symbol,
                market=market,
                timeframe=timeframe,
                limit=limit,
                adjust_type=adjust_type,
            )
            result[symbol.strip().upper()] = len(candles)

        return result

    async def _create_running_log(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe,
        source: str,
        adjust_type: AdjustType,
        started_at: datetime,
    ) -> MarketDataSyncLog:
        return await self.sync_repository.create_log(
            MarketDataSyncLogCreate(
                symbol=symbol,
                market=market,
                timeframe=timeframe,
                source=source,
                adjust_type=adjust_type,
                status="running",
                started_at=started_at,
            )
        )

    async def _finish_success_log_and_status(
        self,
        *,
        sync_log: MarketDataSyncLog,
        symbol_id: int | None,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe,
        source: str,
        adjust_type: AdjustType,
        fetched_count: int,
        normalized_count: int,
        saved_count: int,
        quality_result: MarketDataQualityCheckResult,
        started_at: datetime,
    ) -> None:
        finished_at = datetime.now(UTC)
        sync_status = self._resolve_sync_status(quality_result)
        error_message = self._build_quality_message(quality_result)

        await self.sync_repository.update_log(
            sync_log,
            MarketDataSyncLogUpdate(
                status=sync_status,
                fetched_count=fetched_count,
                normalized_count=normalized_count,
                saved_count=saved_count,
                error_message=error_message,
                finished_at=finished_at,
                duration_ms=self._calculate_duration_ms(
                    started_at=started_at,
                    finished_at=finished_at,
                ),
            ),
        )

        await self.sync_repository.upsert_status(
            MarketDataSyncStatusCreate(
                symbol_id=symbol_id,
                symbol=symbol,
                market=market,
                timeframe=timeframe,
                source=source,
                adjust_type=adjust_type,
                status=sync_status,
                last_success_at=finished_at if sync_status in {"success", "partial"} else None,
                earliest_candle_time=quality_result.earliest_candle_time,
                latest_candle_time=quality_result.latest_candle_time,
                candle_count=saved_count,
                last_error_message=error_message,
            )
        )

    async def _finish_failed_log_and_status(
        self,
        *,
        sync_log: MarketDataSyncLog,
        symbol_id: int | None,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe,
        source: str,
        adjust_type: AdjustType,
        error_message: str,
        started_at: datetime,
    ) -> None:
        finished_at = datetime.now(UTC)

        await self.sync_repository.update_log(
            sync_log,
            MarketDataSyncLogUpdate(
                status="failed",
                error_message=self._truncate_error_message(error_message),
                finished_at=finished_at,
                duration_ms=self._calculate_duration_ms(
                    started_at=started_at,
                    finished_at=finished_at,
                ),
            ),
        )

        await self.sync_repository.upsert_status(
            MarketDataSyncStatusCreate(
                symbol_id=symbol_id,
                symbol=symbol,
                market=market,
                timeframe=timeframe,
                source=source,
                adjust_type=adjust_type,
                status="failed",
                last_failed_at=finished_at,
                candle_count=0,
                last_error_message=self._truncate_error_message(error_message),
            )
        )

    def _resolve_sync_status(
        self,
        quality_result: MarketDataQualityCheckResult,
    ) -> str:
        """把数据质量结果折算成同步状态，供 API 和运维日志查看。"""

        if quality_result.errors:
            return "failed"

        if quality_result.warnings or not quality_result.is_enough or quality_result.is_stale:
            return "partial"

        return "success"

    def _build_quality_message(
        self,
        quality_result: MarketDataQualityCheckResult,
    ) -> str | None:
        messages = [*quality_result.errors, *quality_result.warnings]

        if not messages:
            return None

        return self._truncate_error_message("; ".join(messages))

    def _truncate_error_message(
        self,
        message: str,
    ) -> str:
        return message[:500]

    def _calculate_duration_ms(
        self,
        *,
        started_at: datetime,
        finished_at: datetime,
    ) -> int:
        return max(int((finished_at - started_at).total_seconds() * 1000), 0)

    @classmethod
    def build_provider(
        cls,
        provider_name: str | None = None,
    ) -> MarketDataProvider:
        """按名称构造行情 Provider。

        单股任务、批量任务和查询兜底都通过这里创建 Provider，避免各处自己解析
        .env。这里继续使用白名单，防止配置里写了尚未实现的数据源后静默跑错。
        """

        settings = get_settings()
        resolved_provider_name = (
            provider_name or settings.market_data_primary_provider
        ).strip().lower()

        if resolved_provider_name == "mock":
            return MockMarketDataProvider()

        if resolved_provider_name == "baostock":
            if not settings.baostock_enabled:
                raise BadRequestException(message="baostock provider is disabled")
            return BaoStockProvider()

        if resolved_provider_name == "tushare":
            if not settings.tushare_enabled:
                raise BadRequestException(message="tushare provider is disabled")
            return TushareProvider()

        raise BadRequestException(
            message=f"unsupported market data provider: {resolved_provider_name}"
        )

    def _build_provider(
        self,
        provider_name: str | None = None,
    ) -> MarketDataProvider:
        return self.build_provider(provider_name)
