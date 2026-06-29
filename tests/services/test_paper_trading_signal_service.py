"""纸面交易自选股与未平持仓股票池规则测试。"""

from datetime import UTC, datetime
from types import SimpleNamespace

from app.schemas.market import MarketIndicatorResponse, MarketOverviewResponse, MarketQuoteResponse
from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.paper_trading import PaperTradingTickRequest
from app.schemas.strategy_signal import StrategySignalResponse
from app.services.paper_trading_signal_service import (
    PaperTradingSignalService,
    PaperTradingUniverseItem,
)


class FakeWatchlistService:
    def __init__(self, items):
        self.items = items

    async def list_my_watchlist(self, user):
        return self.items


class FakePaperTradingRepository:
    def __init__(self, positions):
        self.positions = positions

    async def list_open_positions_for_account(self, *, account_id: int, limit: int):
        return self.positions[:limit]


def overview(signal: str) -> MarketOverviewResponse:
    return MarketOverviewResponse(
        quote=MarketQuoteResponse(
            symbol="000001",
            market="CN",
            name="测试股票",
            currency="CNY",
            latest_price=10,
            previous_close=9.8,
            open_price=9.9,
            high_price=10.2,
            low_price=9.7,
            volume=100000,
            price_change=0.2,
            price_change_percent=2,
            as_of=datetime.now(UTC),
            source="mock",
        ),
        indicators=MarketIndicatorResponse(
            symbol="000001",
            market="CN",
            price_change=0.2,
            price_change_percent=2,
            moving_average_5=10,
            moving_average_20=9.5,
            volatility_level="medium",
            trend="bullish",
            source="mock",
        ),
        data_quality=MarketDataQualityReport(
            symbol="000001",
            market="CN",
            timeframe="1d",
            source="mock",
            adjust_type="none",
            candle_count=120,
            is_empty=False,
            is_enough=True,
            is_stale=False,
            errors=[],
            warnings=[],
        ),
        strategy_signal=StrategySignalResponse(
            symbol="000001",
            market="CN",
            timeframe="1d",
            adjust_type="none",
            source="mock",
            status="available",
            signal=signal,
            strength="strong",
            score=80 if signal == "buy" else 20,
            summary=f"{signal} signal",
            reasons=[],
            risks=[],
        ),
    )


def service_for_rules() -> PaperTradingSignalService:
    return PaperTradingSignalService.__new__(PaperTradingSignalService)


def test_removed_watchlist_position_can_sell_but_cannot_buy() -> None:
    service = service_for_rules()
    removed_position = PaperTradingUniverseItem(
        symbol="000001",
        market="CN",
        is_watchlisted=False,
        has_open_position=True,
    )

    can_sell, sell_action, _ = service._evaluate_actionable_signal(
        item=removed_position,
        overview=overview("sell"),
    )
    can_buy, buy_action, buy_reason = service._evaluate_actionable_signal(
        item=removed_position,
        overview=overview("buy"),
    )

    assert can_sell is True
    assert sell_action == "sell"
    assert can_buy is False
    assert buy_action == "buy"
    assert "禁止新买入" in buy_reason


def test_watchlist_without_position_does_not_create_sell_order() -> None:
    service = service_for_rules()
    watchlist_only = PaperTradingUniverseItem(
        symbol="000001",
        market="CN",
        is_watchlisted=True,
        has_open_position=False,
    )

    can_sell, action, reason = service._evaluate_actionable_signal(
        item=watchlist_only,
        overview=overview("sell"),
    )

    assert can_sell is False
    assert action == "sell"
    assert "没有该股票持仓" in reason


async def test_universe_merges_watchlist_and_open_positions_with_exit_priority() -> None:
    watchlist_items = [
        SimpleNamespace(symbol="000001", market="CN", name="平安银行", notes=None),
        SimpleNamespace(symbol="000002", market="CN", name="万科A", notes="观察"),
    ]
    positions = [
        SimpleNamespace(symbol="000003", market="CN"),
        SimpleNamespace(symbol="000001", market="CN"),
    ]
    service = PaperTradingSignalService(
        db=None,
        watchlist_service=FakeWatchlistService(watchlist_items),
        market_service=SimpleNamespace(),
        repository=FakePaperTradingRepository(positions),
    )
    warnings: list[str] = []

    items = await service._build_universe_items(
        user=SimpleNamespace(id=1),
        request=PaperTradingTickRequest(account_id=7, max_symbols=10),
        warnings=warnings,
    )

    by_symbol = {item.symbol: item for item in items}
    assert set(by_symbol) == {"000001", "000002", "000003"}
    assert by_symbol["000001"].is_watchlisted is True
    assert by_symbol["000001"].has_open_position is True
    assert by_symbol["000002"].is_watchlisted is True
    assert by_symbol["000002"].has_open_position is False
    assert by_symbol["000003"].is_watchlisted is False
    assert by_symbol["000003"].has_open_position is True
    assert any("禁止新买入" in warning for warning in warnings)