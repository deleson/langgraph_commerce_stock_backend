from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import BadRequestException
from app.models.market_candle import MarketCandle
from app.models.market_symbol import MarketSymbol
from app.repositories.market_repo import AsyncMarketRepository
from app.schemas.market_data import (
    AdjustType,
    CandleTimeframe,
    MarketCandleQuery,
    MarketCode,
)
from app.services.market_data_quality_service import MarketDataQualityService
from app.services.market_providers import (
    BaoStockProvider,
    MarketDataProvider,
    MockMarketDataProvider,
    TushareProvider,
)


class MarketDataSyncService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        provider: MarketDataProvider | None = None,
        repository: AsyncMarketRepository | None = None,
        quality_service: MarketDataQualityService | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncMarketRepository(db)
        self.quality_service = quality_service or MarketDataQualityService()
        self.provider = provider or self._build_provider()

    async def sync_symbol(
        self,
        *,
        symbol: str,
        market: MarketCode,
    ) -> MarketSymbol:
        symbol_payload = await self.provider.get_symbol(
            symbol=symbol,
            market=market,
        )
        return await self.repository.upsert_symbol(symbol_payload)

    async def sync_candles(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int | None = None,
        adjust_type: AdjustType = "none",
    ) -> list[MarketCandle]:
        settings = get_settings()
        sync_limit = limit or settings.market_data_candle_sync_limit

        if sync_limit <= 0:
            raise BadRequestException(message="market candle sync limit must be greater than 0")

        market_symbol = await self.sync_symbol(
            symbol=symbol,
            market=market,
        )

        query = MarketCandleQuery(
            symbol=market_symbol.symbol,
            market=market,
            timeframe=timeframe,
            limit=sync_limit,
            adjust_type=adjust_type,
            source=self.provider.provider_name,
        )

        provider_candles = await self.provider.get_candles(query)

        candle_payloads = self.quality_service.normalize_candles(
            provider_candles,
            symbol_id=market_symbol.id,
        )

        return await self.repository.upsert_candles(candle_payloads)

    async def sync_symbols(
        self,
        *,
        symbols: Sequence[str],
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int | None = None,
        adjust_type: AdjustType = "none",
    ) -> dict[str, int]:
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

    def _build_provider(
        self,
    ) -> MarketDataProvider:
        settings = get_settings()
        provider_name = settings.market_data_primary_provider.strip().lower()

        if provider_name == "mock":
            return MockMarketDataProvider()

        if provider_name == "baostock":
            if not settings.baostock_enabled:
                raise BadRequestException(message="baostock provider is disabled")
            return BaoStockProvider()

        if provider_name == "tushare":
            if not settings.tushare_enabled:
                raise BadRequestException(message="tushare provider is disabled")
            return TushareProvider()

        raise BadRequestException(message=f"unsupported market data provider: {provider_name}")
