from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.backtest import BacktestRequest, BacktestResponse
from app.schemas.market_data_sync import MarketDataQualityReport
from app.services.backtest_service import BacktestService
from app.services.market_data_quality_report_service import (
    MarketDataQualityReportService,
)


class BacktestQueryService:
    """Orchestrate backtest queries for API and future tools.

    This service keeps routers thin and gives later steps a stable place to add
    data-quality gates, persistence, user isolation, and AI explanation hooks.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        backtest_service: BacktestService | None = None,
        quality_report_service: MarketDataQualityReportService | None = None,
    ) -> None:
        self.db = db
        self.backtest_service = backtest_service or BacktestService(db)
        self.quality_report_service = (
            quality_report_service or MarketDataQualityReportService(db)
        )

    async def run_backtest(
        self,
        request: BacktestRequest,
    ) -> BacktestResponse:
        quality_report = await self.quality_report_service.get_quality_report(
            symbol=request.symbol,
            market=request.market,
            timeframe=request.timeframe,
            limit=request.min_required_candles,
            adjust_type=request.adjust_type,
            source=request.source,
            min_required=request.min_required_candles,
            stale_after_days=request.data_quality_stale_after_days,
        )

        if request.enforce_data_quality:
            unavailable_response = self._build_unavailable_response_if_needed(
                request=request,
                quality_report=quality_report,
            )
            if unavailable_response is not None:
                return unavailable_response

        response = await self.backtest_service.run_backtest(request)
        response.warnings = [
            *quality_report.warnings,
            *response.warnings,
        ]
        return response

    def _build_unavailable_response_if_needed(
        self,
        *,
        request: BacktestRequest,
        quality_report: MarketDataQualityReport,
    ) -> BacktestResponse | None:
        if quality_report.is_empty:
            return self._build_unavailable_response(
                request=request,
                reason="no_data",
                quality_report=quality_report,
            )

        if not quality_report.is_enough:
            return self._build_unavailable_response(
                request=request,
                reason="insufficient_data",
                quality_report=quality_report,
            )

        if quality_report.errors:
            return self._build_unavailable_response(
                request=request,
                reason="data_error",
                quality_report=quality_report,
            )

        if quality_report.is_stale:
            return self._build_unavailable_response(
                request=request,
                reason="data_error",
                quality_report=quality_report,
            )

        return None

    def _build_unavailable_response(
        self,
        *,
        request: BacktestRequest,
        reason,
        quality_report: MarketDataQualityReport,
    ) -> BacktestResponse:
        messages = [
            *quality_report.errors,
            *quality_report.warnings,
        ]

        if not messages:
            messages = ["数据质量检查未通过，当前请求不适合执行回测。"]

        return BacktestResponse(
            symbol=request.symbol,
            market=request.market,
            start_date=request.start_date,
            end_date=request.end_date,
            status="unavailable",
            unavailable_reason=reason,
            summary="当前数据质量不足，未执行历史回测。",
            metrics=None,
            trades=[],
            daily_equity=[],
            signal_snapshots=[],
            input_snapshot=None,
            warnings=messages[:20],
            calculated_at=datetime.now(UTC),
        )