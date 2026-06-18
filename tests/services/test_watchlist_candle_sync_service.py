from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.watchlist_item import WatchlistItem
from app.repositories.market_repo import AsyncMarketRepository
from app.schemas.market_data import MarketCandleCreate
from app.services.watchlist_candle_sync_service import WatchlistCandleSyncService


class FakeSyncService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        provider_name: str,
        calls: list[str],
        failing_providers: set[str] | None = None,
    ) -> None:
        self.db = db
        self.provider_name = provider_name
        self.calls = calls
        self.failing_providers = failing_providers or set()

    async def sync_candles(
        self,
        *,
        symbol: str,
        market: str,
        timeframe: str = "1d",
        limit: int | None = None,
        adjust_type: str = "none",
    ):
        self.calls.append(f"{self.provider_name}:{market}:{symbol}")
        if self.provider_name in self.failing_providers:
            raise RuntimeError(f"{self.provider_name} quota exceeded")

        candle_limit = limit or 3
        now = datetime.now(UTC)
        payloads = []
        for index in range(candle_limit):
            payloads.append(
                MarketCandleCreate(
                    symbol_id=None,
                    symbol=symbol,
                    market=market,
                    timeframe=timeframe,
                    candle_time=now - timedelta(days=candle_limit - index - 1),
                    open_price=Decimal("10"),
                    high_price=Decimal("11"),
                    low_price=Decimal("9"),
                    close_price=Decimal("10.5"),
                    volume=1000 + index,
                    amount=Decimal("10000"),
                    source=self.provider_name,
                    is_adjusted=adjust_type != "none",
                    adjust_type=adjust_type,
                )
            )

        return await AsyncMarketRepository(self.db).upsert_candles(payloads)


def _add_watchlist_item(
    db_session: AsyncSession,
    *,
    user: User,
    symbol: str,
    market: str = "CN",
) -> None:
    db_session.add(
        WatchlistItem(
            user_id=user.id,
            symbol=symbol,
            market=market,
            name=symbol,
        )
    )


async def test_watchlist_candle_sync_empty_watchlist_returns_success(
    db_session: AsyncSession,
) -> None:
    calls: list[str] = []
    service = WatchlistCandleSyncService(
        db_session,
        sync_service_factory=lambda provider: FakeSyncService(
            db_session,
            provider_name=provider,
            calls=calls,
        ),
    )

    summary = await service.sync_watchlist_candles(source="mock", fallback_sources=[])

    assert summary.status == "success"
    assert summary.requested_symbol_count == 0
    assert calls == []


async def test_watchlist_candle_sync_deduplicates_symbols_and_writes_candles(
    db_session: AsyncSession,
    test_user: User,
    another_test_user: User,
) -> None:
    _add_watchlist_item(db_session, user=test_user, symbol="600519")
    _add_watchlist_item(db_session, user=another_test_user, symbol="600519")
    _add_watchlist_item(db_session, user=test_user, symbol="002594")
    await db_session.commit()

    calls: list[str] = []
    service = WatchlistCandleSyncService(
        db_session,
        sync_service_factory=lambda provider: FakeSyncService(
            db_session,
            provider_name=provider,
            calls=calls,
        ),
    )

    summary = await service.sync_watchlist_candles(
        source="mock",
        fallback_sources=[],
        limit=3,
    )

    assert summary.status == "success"
    assert summary.requested_symbol_count == 2
    assert summary.synced_symbol_count == 2
    assert summary.total_saved_candles == 6
    assert sorted(calls) == ["mock:CN:002594", "mock:CN:600519"]


async def test_watchlist_candle_sync_skips_fresh_existing_candles(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    _add_watchlist_item(db_session, user=test_user, symbol="600519")
    await db_session.commit()

    await AsyncMarketRepository(db_session).upsert_candles(
        [
            MarketCandleCreate(
                symbol="600519",
                market="CN",
                timeframe="1d",
                candle_time=datetime.now(UTC),
                open_price=Decimal("10"),
                high_price=Decimal("11"),
                low_price=Decimal("9"),
                close_price=Decimal("10.5"),
                volume=1000,
                source="mock",
                adjust_type="none",
            )
        ]
    )

    calls: list[str] = []
    service = WatchlistCandleSyncService(
        db_session,
        sync_service_factory=lambda provider: FakeSyncService(
            db_session,
            provider_name=provider,
            calls=calls,
        ),
    )

    summary = await service.sync_watchlist_candles(source="mock", stale_after_days=3)

    assert summary.status == "success"
    assert summary.skipped_symbol_count == 1
    assert summary.synced_symbol_count == 0
    assert calls == []


async def test_watchlist_candle_sync_uses_fallback_when_primary_fails(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    _add_watchlist_item(db_session, user=test_user, symbol="600519")
    await db_session.commit()

    calls: list[str] = []
    service = WatchlistCandleSyncService(
        db_session,
        sync_service_factory=lambda provider: FakeSyncService(
            db_session,
            provider_name=provider,
            calls=calls,
            failing_providers={"baostock"},
        ),
    )

    summary = await service.sync_watchlist_candles(
        source="baostock",
        fallback_sources=["mock"],
        limit=2,
    )

    assert summary.status == "success"
    assert summary.synced_symbol_count == 1
    assert summary.provider_success_counts == {"mock": 1}
    assert calls == ["baostock:CN:600519", "mock:CN:600519"]


async def test_watchlist_candle_sync_is_idempotent_for_existing_provider_candles(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    _add_watchlist_item(db_session, user=test_user, symbol="600519")
    await db_session.commit()

    calls: list[str] = []
    service = WatchlistCandleSyncService(
        db_session,
        sync_service_factory=lambda provider: FakeSyncService(
            db_session,
            provider_name=provider,
            calls=calls,
        ),
    )

    first = await service.sync_watchlist_candles(
        source="mock",
        fallback_sources=[],
        limit=2,
        stale_after_days=0,
    )
    second = await service.sync_watchlist_candles(
        source="mock",
        fallback_sources=[],
        limit=2,
        stale_after_days=0,
    )

    candles = await AsyncMarketRepository(db_session).list_candles_by_date_range(
        symbol="600519",
        market="CN",
        timeframe="1d",
        start_at=datetime.now(UTC) - timedelta(days=10),
        end_at=datetime.now(UTC) + timedelta(days=1),
        source="mock",
    )

    assert first.synced_symbol_count == 1
    assert second.skipped_symbol_count == 1
    assert len(candles) == 2
