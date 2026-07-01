"""单股回测查询编排服务。

Router 不直接执行回测，本服务负责在 API 请求进入核心回测前先做数据质量门控，
再调用 BacktestService。这样数据质量检查、不可用响应和回测计算可以保持清晰分层。
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import BadRequestException, NotFoundException
from app.schemas.backtest import BacktestRequest, BacktestResponse
from app.schemas.market_data_sync import MarketDataQualityReport
from app.services.backtest_service import BacktestService
from app.services.market_data_sync_service import MarketDataSyncService
from app.services.market_data_quality_report_service import (
    MarketDataQualityReportService,
)


class BacktestQueryService:
    """单股回测 API 与核心回测引擎之间的编排层。

    它不写交易撮合公式，也不直接访问 market_candles；这些分别由 BacktestService
    和数据/质量服务负责。
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
        """执行一次单股回测请求。

        如果 enforce_data_quality=True，则数据为空、数量不足、过旧或有错误时，
        直接返回 unavailable，避免用不可靠 K 线生成看似完整的回测结果。
        """

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

        quality_report = await self._refresh_candles_if_needed(
            request=request,
            quality_report=quality_report,
        )

        if request.enforce_data_quality:
            unavailable_response = self._build_unavailable_response_if_needed(
                request=request,
                quality_report=quality_report,
            )
            if unavailable_response is not None:
                return unavailable_response

        try:
            response = await self.backtest_service.run_backtest(request)
        except NotFoundException as exc:
            return self._build_unavailable_response(
                request=request,
                reason="no_data",
                quality_report=self._append_quality_error(
                    quality_report,
                    exc,
                ),
            )
        except BadRequestException as exc:
            return self._build_unavailable_response(
                request=request,
                reason="insufficient_data",
                quality_report=self._append_quality_error(
                    quality_report,
                    exc,
                ),
            )

        response.warnings = [
            *quality_report.warnings,
            *response.warnings,
        ]
        return response

    async def _refresh_candles_if_needed(
        self,
        *,
        request: BacktestRequest,
        quality_report: MarketDataQualityReport,
    ) -> MarketDataQualityReport:
        """仅在数据库 K 线缺失、不足或过期时执行一次受控补齐。

        回测仍然以数据库为唯一计算输入。外部 Provider 只负责把缺失数据写入数据库，
        随后重新执行质量检查；这样既避免每次回测都消耗外部额度，也避免用户第一次
        回测尚未同步过的股票时永远得到 unavailable。
        """

        if not self._should_refresh_candles(quality_report):
            return quality_report

        provider_names = self._sync_provider_names(request)
        sync_limit = self._calculate_sync_limit(request)
        sync_warnings: list[str] = []

        for provider_name in provider_names:
            try:
                await MarketDataSyncService(
                    self.db,
                    provider_name=provider_name,
                ).sync_candles(
                    symbol=request.symbol,
                    market=request.market,
                    timeframe=request.timeframe,
                    limit=sync_limit,
                    adjust_type=request.adjust_type,
                )
            except Exception as exc:
                sync_warnings.append(
                    f"回测数据自动同步失败（{provider_name}）：{self._safe_error_message(exc)}"
                )
                continue

            refreshed_report = await self.quality_report_service.get_quality_report(
                symbol=request.symbol,
                market=request.market,
                timeframe=request.timeframe,
                limit=request.min_required_candles,
                adjust_type=request.adjust_type,
                source=request.source,
                min_required=request.min_required_candles,
                stale_after_days=request.data_quality_stale_after_days,
            )
            if not self._should_refresh_candles(refreshed_report):
                if sync_warnings:
                    refreshed_report = refreshed_report.model_copy(
                        update={
                            "warnings": [
                                *refreshed_report.warnings,
                                *sync_warnings,
                            ][:20]
                        }
                    )
                return refreshed_report

            quality_report = refreshed_report

        if sync_warnings:
            quality_report = quality_report.model_copy(
                update={
                    "warnings": [
                        *quality_report.warnings,
                        *sync_warnings,
                    ][:20]
                }
            )

        return quality_report

    def _append_quality_error(
        self,
        quality_report: MarketDataQualityReport,
        exc: Exception,
    ) -> MarketDataQualityReport:
        return quality_report.model_copy(
            update={
                "errors": [
                    *quality_report.errors,
                    self._safe_error_message(exc),
                ][:20]
            }
        )

    def _should_refresh_candles(
        self,
        quality_report: MarketDataQualityReport,
    ) -> bool:
        return (
            quality_report.is_empty
            or not quality_report.is_enough
            or quality_report.is_stale
        )

    def _sync_provider_names(
        self,
        request: BacktestRequest,
    ) -> list[str]:
        """显式 source 必须保持口径；未指定时才使用主 Provider 和兜底链。"""

        if request.source is not None:
            return [request.source]

        settings = get_settings()
        provider_names: list[str] = []
        for provider_name in [
            settings.market_data_primary_provider,
            *settings.market_data_fallback_providers.split(","),
        ]:
            normalized = provider_name.strip().lower()
            if normalized and normalized not in provider_names:
                provider_names.append(normalized)

        return provider_names

    def _calculate_sync_limit(
        self,
        request: BacktestRequest,
    ) -> int:
        """按回测日期跨度估算交易日数量，并限制单次外部请求规模。"""

        settings = get_settings()
        calendar_days = (request.end_date - request.start_date).days + 1
        estimated_trading_days = int(calendar_days * 5 / 7) + 20
        return min(
            max(
                request.min_required_candles,
                settings.market_data_candle_sync_limit,
                estimated_trading_days,
            ),
            1000,
        )

    def _safe_error_message(
        self,
        exc: Exception,
    ) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        return message[:200]

    def _build_unavailable_response_if_needed(
        self,
        *,
        request: BacktestRequest,
        quality_report: MarketDataQualityReport,
    ) -> BacktestResponse | None:
        """根据数据质量报告决定是否跳过回测。"""

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
