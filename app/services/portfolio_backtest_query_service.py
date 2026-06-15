"""组合回测查询编排服务。

本服务负责在组合回测核心计算前，对组合内每个资产分别生成数据质量报告。
当 enforce_data_quality=True 时，只要组合内任一资产不可用，就返回 unavailable，
避免用部分缺失数据生成不可靠的组合回测结果。
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.portfolio_backtest import (
    PortfolioBacktestRequest,
    PortfolioBacktestResponse,
    PortfolioBacktestUnavailableReason,
)
from app.services.market_data_quality_report_service import (
    MarketDataQualityReportService,
)
from app.services.portfolio_backtest_service import PortfolioBacktestService


class PortfolioBacktestQueryService:
    """组合回测 API 与组合回测引擎之间的编排层。

    它不直接计算调仓和组合权益，只负责质量门控、调用核心服务和合并 warnings。
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        portfolio_backtest_service: PortfolioBacktestService | None = None,
        quality_report_service: MarketDataQualityReportService | None = None,
    ) -> None:
        self.db = db
        self.portfolio_backtest_service = (
            portfolio_backtest_service or PortfolioBacktestService(db)
        )
        self.quality_report_service = (
            quality_report_service or MarketDataQualityReportService(db)
        )

    async def run_portfolio_backtest(
        self,
        request: PortfolioBacktestRequest,
    ) -> PortfolioBacktestResponse:
        """执行一次组合回测请求。"""

        quality_reports = await self._build_quality_reports(request)

        if request.enforce_data_quality:
            unavailable_response = self._build_unavailable_response_if_needed(
                request=request,
                quality_reports=quality_reports,
            )
            if unavailable_response is not None:
                return unavailable_response

        response = await self.portfolio_backtest_service.run_portfolio_backtest(
            request
        )
        response.warnings = [
            *self._build_quality_warning_messages(quality_reports),
            *response.warnings,
        ][:30]
        return response

    async def _build_quality_reports(
        self,
        request: PortfolioBacktestRequest,
    ) -> list[MarketDataQualityReport]:
        """为组合内每个资产生成数据质量报告。"""

        reports: list[MarketDataQualityReport] = []

        for asset in request.assets:
            report = await self.quality_report_service.get_quality_report(
                symbol=asset.symbol,
                market=asset.market,
                timeframe=request.timeframe,
                limit=request.min_required_candles,
                adjust_type=request.adjust_type,
                source=request.source,
                min_required=request.min_required_candles,
                stale_after_days=request.data_quality_stale_after_days,
            )
            reports.append(report)

        return reports

    def _build_unavailable_response_if_needed(
        self,
        *,
        request: PortfolioBacktestRequest,
        quality_reports: list[MarketDataQualityReport],
    ) -> PortfolioBacktestResponse | None:
        """只要任一资产数据质量不满足要求，就阻止组合回测继续执行。"""

        if any(report.is_empty for report in quality_reports):
            return self._build_unavailable_response(
                request=request,
                reason="no_data",
                quality_reports=quality_reports,
            )

        if any(not report.is_enough for report in quality_reports):
            return self._build_unavailable_response(
                request=request,
                reason="insufficient_data",
                quality_reports=quality_reports,
            )

        if any(report.errors for report in quality_reports):
            return self._build_unavailable_response(
                request=request,
                reason="data_error",
                quality_reports=quality_reports,
            )

        if any(report.is_stale for report in quality_reports):
            return self._build_unavailable_response(
                request=request,
                reason="data_error",
                quality_reports=quality_reports,
            )

        return None

    def _build_unavailable_response(
        self,
        *,
        request: PortfolioBacktestRequest,
        reason: PortfolioBacktestUnavailableReason,
        quality_reports: list[MarketDataQualityReport],
    ) -> PortfolioBacktestResponse:
        messages = self._build_quality_problem_messages(quality_reports)

        if not messages:
            messages = ["组合回测数据质量检查未通过，当前请求不适合执行组合回测。"]

        return PortfolioBacktestResponse(
            assets=request.assets,
            start_date=request.start_date,
            end_date=request.end_date,
            status="unavailable",
            unavailable_reason=reason,
            summary="当前组合内至少一只股票的数据质量不足，未执行组合回测。",
            metrics=None,
            trades=[],
            daily_equity=[],
            input_snapshot=None,
            warnings=messages[:30],
            calculated_at=datetime.now(UTC),
        )

    def _build_quality_problem_messages(
        self,
        quality_reports: list[MarketDataQualityReport],
    ) -> list[str]:
        messages: list[str] = []

        for report in quality_reports:
            asset_label = f"{report.market}:{report.symbol}"

            if report.is_empty:
                messages.append(f"{asset_label} 没有可用 K 线数据。")

            if not report.is_enough:
                messages.append(
                    f"{asset_label} K 线数量不足，当前 candle_count={report.candle_count}。"
                )

            if report.is_stale:
                messages.append(f"{asset_label} K 线数据过旧。")

            for error in report.errors:
                messages.append(f"{asset_label} 数据错误：{error}")

            for warning in report.warnings:
                messages.append(f"{asset_label} 数据提示：{warning}")

        return messages

    def _build_quality_warning_messages(
        self,
        quality_reports: list[MarketDataQualityReport],
    ) -> list[str]:
        messages: list[str] = []

        for report in quality_reports:
            asset_label = f"{report.market}:{report.symbol}"

            for warning in report.warnings:
                messages.append(f"{asset_label} 数据提示：{warning}")

        return messages
