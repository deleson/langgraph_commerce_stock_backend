from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.schemas.backtest import BacktestRequest
from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.paper_trading import PaperTradingTickRequest
from app.services.backtest_query_service import BacktestQueryService
from app.services.paper_trading_query_service import PaperTradingQueryService
from app.services.paper_trading_run_service import PaperTradingRunService
from app.services.paper_trading_signal_service import (
    PaperTradingSignalContext,
    PaperTradingSignalItem,
)


pytestmark = pytest.mark.asyncio


def _backtest_request(*, source: str | None = None) -> BacktestRequest:
    today = date.today()
    return BacktestRequest(
        symbol="000001",
        market="CN",
        start_date=today - timedelta(days=365),
        end_date=today,
        source=source,
        min_required_candles=60,
        data_quality_stale_after_days=7,
    )


def _quality_report(
    *,
    is_empty: bool,
    is_enough: bool,
    is_stale: bool = False,
) -> MarketDataQualityReport:
    return MarketDataQualityReport(
        symbol="000001",
        market="CN",
        timeframe="1d",
        source="mock",
        candle_count=0 if is_empty else 60,
        is_empty=is_empty,
        is_enough=is_enough,
        is_stale=is_stale,
        errors=["market candles not found"] if is_empty else [],
        checked_at=datetime.now(UTC),
    )


class _QualityReportSequence:
    def __init__(self, reports: list[MarketDataQualityReport]) -> None:
        self.reports = reports
        self.calls = 0

    async def get_quality_report(self, **_kwargs) -> MarketDataQualityReport:
        index = min(self.calls, len(self.reports) - 1)
        self.calls += 1
        return self.reports[index]


async def test_backtest_refresh_skips_provider_when_database_data_is_ready(
    db_session,
    monkeypatch,
) -> None:
    ready_report = _quality_report(is_empty=False, is_enough=True)
    service = BacktestQueryService(
        db_session,
        quality_report_service=_QualityReportSequence([ready_report]),
    )

    class _UnexpectedSyncService:
        def __init__(self, *_args, **_kwargs) -> None:
            raise AssertionError("数据库数据可用时不应调用 Provider")

    monkeypatch.setattr(
        "app.services.backtest_query_service.MarketDataSyncService",
        _UnexpectedSyncService,
    )

    result = await service._refresh_candles_if_needed(
        request=_backtest_request(),
        quality_report=ready_report,
    )

    assert result is ready_report


async def test_backtest_refresh_syncs_missing_candles_and_rechecks_quality(
    db_session,
    monkeypatch,
) -> None:
    missing_report = _quality_report(is_empty=True, is_enough=False)
    ready_report = _quality_report(is_empty=False, is_enough=True)
    quality_service = _QualityReportSequence([ready_report])
    calls: list[dict] = []

    class _SuccessfulSyncService:
        def __init__(self, _db, *, provider_name: str) -> None:
            self.provider_name = provider_name

        async def sync_candles(self, **kwargs):
            calls.append({"provider": self.provider_name, **kwargs})
            return []

    monkeypatch.setattr(
        "app.services.backtest_query_service.MarketDataSyncService",
        _SuccessfulSyncService,
    )

    service = BacktestQueryService(
        db_session,
        quality_report_service=quality_service,
    )
    result = await service._refresh_candles_if_needed(
        request=_backtest_request(source="mock"),
        quality_report=missing_report,
    )

    assert result.is_enough is True
    assert quality_service.calls == 1
    assert calls[0]["provider"] == "mock"
    assert calls[0]["limit"] >= 60


async def test_backtest_refresh_keeps_unavailable_and_reports_provider_failure(
    db_session,
    monkeypatch,
) -> None:
    missing_report = _quality_report(is_empty=True, is_enough=False)

    class _FailedSyncService:
        def __init__(self, _db, *, provider_name: str) -> None:
            self.provider_name = provider_name

        async def sync_candles(self, **_kwargs):
            raise RuntimeError("provider rate limited")

    monkeypatch.setattr(
        "app.services.backtest_query_service.MarketDataSyncService",
        _FailedSyncService,
    )

    service = BacktestQueryService(
        db_session,
        quality_report_service=_QualityReportSequence([missing_report]),
    )
    result = await service._refresh_candles_if_needed(
        request=_backtest_request(source="mock"),
        quality_report=missing_report,
    )

    assert result.is_empty is True
    assert any("provider rate limited" in warning for warning in result.warnings)


async def test_paper_trading_tick_items_explain_non_executable_signal(
    db_session,
) -> None:
    signal_item = PaperTradingSignalItem(
        symbol="000001",
        market="CN",
        action="sell",
        can_generate_order=False,
        reason="当前模拟账户没有该股票持仓，不生成卖出订单",
    )
    context = PaperTradingSignalContext(
        user_id=1,
        request=PaperTradingTickRequest(account_id=1),
        universe_items=[],
        items=[signal_item],
        actionable_items=[],
    )

    items = PaperTradingQueryService(db_session)._build_tick_items(
        signal_context=context,
        execution_result=None,
    )

    assert len(items) == 1
    assert items[0].action == "sell"
    assert items[0].order_id is None
    assert items[0].trade_id is None
    assert "没有该股票持仓" in items[0].message


async def test_paper_trading_run_snapshot_keeps_strategy_and_quality_fields(
    db_session,
) -> None:
    overview = SimpleNamespace(
        quote=SimpleNamespace(latest_price=10.5),
        data_quality=SimpleNamespace(
            errors=[],
            is_empty=False,
            is_enough=True,
            is_stale=False,
        ),
        strategy_signal=SimpleNamespace(
            signal="buy",
            strength="strong",
            score=72,
        ),
    )
    signal_item = PaperTradingSignalItem(
        symbol="000001",
        market="CN",
        action="buy",
        can_generate_order=True,
        reason="测试买入信号",
        overview=overview,
    )

    snapshot = PaperTradingRunService(db_session)._build_signal_item_snapshot(
        signal_item
    )

    assert snapshot["data_quality_status"] == "available"
    assert snapshot["strategy_action"] == "buy"
    assert snapshot["strategy_strength"] == "strong"
    assert snapshot["strategy_score"] == 72
