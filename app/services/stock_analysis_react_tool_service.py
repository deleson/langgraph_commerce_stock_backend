from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.user_preference import UserPreference
from app.models.watchlist_item import WatchlistItem
from app.models.analysis_record import AnalysisRecord
from app.repositories.analysis_record_repo import AsyncAnalysisRecordRepository
from app.repositories.user_preference_repo import AsyncUserPreferenceRepository
from app.repositories.watchlist_repo import AsyncWatchlistRepository
from app.schemas.market import CandleTimeframe, MarketCode, MarketOverviewResponse
from app.schemas.market_data import AdjustType, MarketDataSource
from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.stock_analysis_react import ReactObservation
from app.schemas.technical_indicator import TechnicalIndicatorResponse
from app.services.market_data_quality_report_service import MarketDataQualityReportService
from app.services.market_service import MarketService
from app.services.technical_indicator_query_service import TechnicalIndicatorQueryService
from app.schemas.backtest import BacktestRequest, BacktestResponse
from app.services.backtest_query_service import BacktestQueryService

class StockAnalysisReactToolService:
    """Business tool executor used by the stock analysis ReAct graph.

    This service wraps project business capabilities as safe ReAct tools.
    It does not let the LLM access database objects directly.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.analysis_record_repo = AsyncAnalysisRecordRepository(db)
        self.user_preference_repo = AsyncUserPreferenceRepository(db)
        self.watchlist_repo = AsyncWatchlistRepository(db)
        self.market_service = MarketService(db)
        self.technical_indicator_query_service = TechnicalIndicatorQueryService(db)
        self.market_data_quality_report_service = MarketDataQualityReportService(db)
        self.backtest_query_service = BacktestQueryService(db)
    async def get_analysis_record(
        self,
        *,
        analysis_thread_id: str,
        user_id: int,
    ) -> ReactObservation:
        record = await self.analysis_record_repo.get_latest_by_thread_id_for_user(
            thread_id=analysis_thread_id,
            user_id=user_id,
        )

        if record is None:
            raise NotFoundException(
                message="analysis thread does not exist or does not belong to current user",
                details=[
                    {
                        "field": "analysis_thread_id",
                        "reason": "analysis record not found for current user",
                    }
                ],
            )

        return ReactObservation(
            tool_name="get_analysis_record",
            tool_input={
                "analysis_thread_id": analysis_thread_id,
            },
            tool_output=self._serialize_analysis_record(record),
            success=True,
            created_at=datetime.now(UTC),
        )

    async def get_market_overview(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 30,
        include_technical_indicators: bool = False,
        include_data_quality: bool = True,
        include_sync_status: bool = True,
        technical_indicator_limit: int = 120,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
    ) -> ReactObservation:
        normalized_symbol = symbol.strip().upper()

        overview = await self.market_service.get_overview(
            symbol=normalized_symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            include_technical_indicators=include_technical_indicators,
            technical_indicator_limit=technical_indicator_limit,
            adjust_type=adjust_type,
            technical_indicator_source=source,
            include_data_quality=include_data_quality,
            include_sync_status=include_sync_status,
            data_quality_source=source,
            data_quality_min_required=1,
            data_quality_stale_after_days=None,
        )

        return ReactObservation(
            tool_name="get_market_overview",
            tool_input={
                "symbol": normalized_symbol,
                "market": market,
                "timeframe": timeframe,
                "limit": limit,
                "include_technical_indicators": include_technical_indicators,
                "include_data_quality": include_data_quality,
                "include_sync_status": include_sync_status,
                "technical_indicator_limit": technical_indicator_limit,
                "adjust_type": adjust_type,
                "source": source,
            },
            tool_output=self._serialize_market_overview(overview),
            success=True,
            created_at=datetime.now(UTC),
        )

    async def get_technical_indicators(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 120,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
    ) -> ReactObservation:
        normalized_symbol = symbol.strip().upper()

        indicators = await self.technical_indicator_query_service.get_summary(
            symbol=normalized_symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            adjust_type=adjust_type,
            source=source,
        )

        return ReactObservation(
            tool_name="get_technical_indicators",
            tool_input={
                "symbol": normalized_symbol,
                "market": market,
                "timeframe": timeframe,
                "limit": limit,
                "adjust_type": adjust_type,
                "source": source,
            },
            tool_output=self._serialize_technical_indicators(indicators),
            success=True,
            created_at=datetime.now(UTC),
        )

    async def get_data_quality(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 120,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
        min_required: int = 35,
        stale_after_days: int | None = None,
    ) -> ReactObservation:
        normalized_symbol = symbol.strip().upper()

        report = await self.market_data_quality_report_service.get_quality_report(
            symbol=normalized_symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            adjust_type=adjust_type,
            source=source,
            min_required=min_required,
            stale_after_days=stale_after_days,
        )

        return ReactObservation(
            tool_name="get_data_quality",
            tool_input={
                "symbol": normalized_symbol,
                "market": market,
                "timeframe": timeframe,
                "limit": limit,
                "adjust_type": adjust_type,
                "source": source,
                "min_required": min_required,
                "stale_after_days": stale_after_days,
            },
            tool_output=self._serialize_data_quality_report(report),
            success=True,
            created_at=datetime.now(UTC),
        )

    async def get_user_preference(
        self,
        *,
        user_id: int,
    ) -> ReactObservation:
        preference = await self.user_preference_repo.get_by_user_id(user_id)

        return ReactObservation(
            tool_name="get_user_preference",
            tool_input={
                "user_id": user_id,
            },
            tool_output=self._serialize_user_preference(preference),
            success=True,
            created_at=datetime.now(UTC),
        )

    async def get_watchlist(
        self,
        *,
        user_id: int,
        limit: int = 50,
    ) -> ReactObservation:
        items = await self.watchlist_repo.list_by_user_id(user_id)
        safe_limit = max(0, min(limit, 50))
        limited_items = items[:safe_limit]

        return ReactObservation(
            tool_name="get_watchlist",
            tool_input={
                "user_id": user_id,
                "limit": safe_limit,
            },
            tool_output={
                "count": len(items),
                "returned_count": len(limited_items),
                "items": [
                    self._serialize_watchlist_item(item)
                    for item in limited_items
                ],
            },
            success=True,
            created_at=datetime.now(UTC),
        )

    async def get_backtest_result(
        self,
        *,
        symbol: str,
        market: MarketCode,
        start_date: Any,
        end_date: Any,
        initial_cash: Any = "100000",
        position_size_ratio: float = 1.0,
        timeframe: CandleTimeframe = "1d",
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
        min_required_candles: int = 60,
        enforce_data_quality: bool = True,
        data_quality_stale_after_days: int | None = None,
    ) -> ReactObservation:
        normalized_symbol = symbol.strip().upper()

        request = BacktestRequest(
            symbol=normalized_symbol,
            market=market,
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash,
            position_size_ratio=position_size_ratio,
            timeframe=timeframe,
            adjust_type=adjust_type,
            source=source,
            min_required_candles=min_required_candles,
            enforce_data_quality=enforce_data_quality,
            data_quality_stale_after_days=data_quality_stale_after_days,
            include_trades=False,
            include_daily_equity=False,
            include_signal_snapshots=False,
        )

        response = await self.backtest_query_service.run_backtest(request)

        return ReactObservation(
            tool_name="get_backtest_result",
            tool_input={
                "symbol": normalized_symbol,
                "market": market,
                "start_date": str(request.start_date),
                "end_date": str(request.end_date),
                "initial_cash": str(request.initial_cash),
                "position_size_ratio": request.position_size_ratio,
                "timeframe": request.timeframe,
                "adjust_type": request.adjust_type,
                "source": request.source,
                "min_required_candles": request.min_required_candles,
                "enforce_data_quality": request.enforce_data_quality,
                "data_quality_stale_after_days": request.data_quality_stale_after_days,
                "include_trades": request.include_trades,
                "include_daily_equity": request.include_daily_equity,
                "include_signal_snapshots": request.include_signal_snapshots,
            },
            tool_output=self._serialize_backtest_response(response),
            success=True,
            created_at=datetime.now(UTC),
        )


    def _serialize_analysis_record(
        self,
        record: AnalysisRecord,
    ) -> dict[str, Any]:
        result_snapshot = record.result_snapshot or {}
        context_snapshot = result_snapshot.get("context_snapshot") or {}
        result = result_snapshot.get("result") or {}

        return {
            "id": record.id,
            "analysis_thread_id": record.analysis_thread_id,
            "symbol": record.symbol,
            "market": record.market,
            "analysis_type": record.analysis_type,
            "status": record.status,
            "summary": record.summary,
            "result": result,
            "context_snapshot": context_snapshot,
            "graph_route": result_snapshot.get("graph_route"),
            "quality_context": result_snapshot.get("quality_context"),
            "technical_indicators_available": self._get_nested_value(
                result_snapshot,
                "metadata",
                "ai_context",
                "technical_indicators_available",
            ),
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    def _serialize_market_overview(
        self,
        overview: MarketOverviewResponse,
    ) -> dict[str, Any]:
        payload = overview.model_dump(mode="json")

        candles = payload.get("candles") or []
        if len(candles) > 30:
            payload["candles"] = candles[-30:]

        return payload

    def _serialize_technical_indicators(
        self,
        indicators: TechnicalIndicatorResponse,
    ) -> dict[str, Any]:
        payload = indicators.model_dump(mode="json")

        summary = payload.get("summary") or {}
        warnings = summary.get("warnings") or []
        interpretation = summary.get("interpretation") or []

        if len(warnings) > 5:
            summary["warnings"] = warnings[:5]

        if len(interpretation) > 8:
            summary["interpretation"] = interpretation[:8]

        payload["summary"] = summary
        return payload

    def _serialize_data_quality_report(
        self,
        report: MarketDataQualityReport,
    ) -> dict[str, Any]:
        payload = report.model_dump(mode="json")

        errors = payload.get("errors") or []
        warnings = payload.get("warnings") or []

        if len(errors) > 10:
            payload["errors"] = errors[:10]

        if len(warnings) > 10:
            payload["warnings"] = warnings[:10]

        return payload

    def _serialize_backtest_response(
        self,
        response: BacktestResponse,
    ) -> dict[str, Any]:
        payload = response.model_dump(mode="json")
        metrics = payload.get("metrics") or None
        warnings = payload.get("warnings") or []

        return {
            "symbol": payload.get("symbol"),
            "market": payload.get("market"),
            "date_range": {
                "start_date": payload.get("start_date"),
                "end_date": payload.get("end_date"),
            },
            "status": payload.get("status"),
            "unavailable_reason": payload.get("unavailable_reason"),
            "summary": payload.get("summary"),
            "metrics": self._build_backtest_metrics_observation(metrics),
            "data_context": self._build_backtest_data_context(payload),
            "output_limits": {
                "warnings_returned": min(len(warnings), 5),
                "warnings_total": len(warnings),
                "trades_returned": 0,
                "daily_equity_returned": 0,
                "signal_snapshots_returned": 0,
                "detail_policy": (
                    "trades, daily_equity, and signal_snapshots are not returned "
                    "to the ReAct observation to keep the LLM context concise."
                ),
            },
            "warnings": warnings[:5],
            "calculated_at": payload.get("calculated_at"),
            "disclaimer": payload.get("disclaimer"),
        }

    def _build_backtest_metrics_observation(
        self,
        metrics: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if metrics is None:
            return None

        return {
            "capital": {
                "initial_cash": metrics.get("initial_cash"),
                "final_equity": metrics.get("final_equity"),
            },
            "return_metrics": {
                "total_return": metrics.get("total_return"),
                "annualized_return": metrics.get("annualized_return"),
                "average_daily_return": metrics.get("average_daily_return"),
            },
            "risk_metrics": {
                "max_drawdown": metrics.get("max_drawdown"),
                "daily_return_volatility": metrics.get("daily_return_volatility"),
                "annualized_volatility": metrics.get("annualized_volatility"),
                "sharpe_ratio": metrics.get("sharpe_ratio"),
                "return_drawdown_ratio": metrics.get("return_drawdown_ratio"),
            },
            "trade_quality": {
                "trade_count": metrics.get("trade_count"),
                "completed_trade_count": metrics.get("completed_trade_count"),
                "win_rate": metrics.get("win_rate"),
                "average_win": metrics.get("average_win"),
                "average_loss": metrics.get("average_loss"),
                "profit_loss_ratio": metrics.get("profit_loss_ratio"),
                "average_realized_return": metrics.get("average_realized_return"),
                "average_holding_days": metrics.get("average_holding_days"),
                "best_trade_pnl": metrics.get("best_trade_pnl"),
                "worst_trade_pnl": metrics.get("worst_trade_pnl"),
            },
            "benchmark": {
                "buy_and_hold_return": metrics.get("buy_and_hold_return"),
                "excess_return": metrics.get("excess_return"),
                "outperformed_buy_and_hold": metrics.get("outperformed_buy_and_hold"),
            },
        }

    def _build_backtest_data_context(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        input_snapshot = payload.get("input_snapshot") or {}

        return {
            "input_snapshot": {
                "candle_count": input_snapshot.get("candle_count"),
                "first_candle_date": input_snapshot.get("first_candle_date"),
                "last_candle_date": input_snapshot.get("last_candle_date"),
                "strategy_name": input_snapshot.get("strategy_name"),
                "timeframe": input_snapshot.get("timeframe"),
                "adjust_type": input_snapshot.get("adjust_type"),
                "source": input_snapshot.get("source"),
                "min_required_candles": input_snapshot.get("min_required_candles"),
                "position_size_ratio": input_snapshot.get("position_size_ratio"),
            },
            "result_lists": {
                "trades_count": len(payload.get("trades") or []),
                "daily_equity_count": len(payload.get("daily_equity") or []),
                "signal_snapshots_count": len(payload.get("signal_snapshots") or []),
            },
        }

    def _serialize_user_preference(
        self,
        preference: UserPreference | None,
    ) -> dict[str, Any]:
        if preference is None:
            return {
                "available": False,
                "risk_preference": "balanced",
                "timezone": "Asia/Shanghai",
                "daily_report_enabled": False,
                "abnormal_alert_enabled": False,
                "default_watchlist_alert_enabled": False,
                "note": "user preference not found, fallback defaults are used",
            }

        return {
            "available": True,
            "id": preference.id,
            "risk_preference": preference.risk_preference,
            "timezone": preference.timezone,
            "daily_report_enabled": preference.daily_report_enabled,
            "abnormal_alert_enabled": preference.abnormal_alert_enabled,
            "default_watchlist_alert_enabled": preference.default_watchlist_alert_enabled,
            "created_at": preference.created_at.isoformat() if preference.created_at else None,
            "updated_at": preference.updated_at.isoformat() if preference.updated_at else None,
        }

    def _serialize_watchlist_item(
        self,
        item: WatchlistItem,
    ) -> dict[str, Any]:
        return {
            "id": item.id,
            "symbol": item.symbol,
            "market": item.market,
            "name": item.name,
            "notes": item.notes,
            "alert_enabled": item.alert_enabled,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }

    def _get_nested_value(
        self,
        source: dict[str, Any],
        *keys: str,
    ) -> Any:
        current: Any = source

        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)

        return current