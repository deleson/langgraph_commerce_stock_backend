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
from app.repositories.user_repo import AsyncUserRepository
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
from app.schemas.stock_candidate import (
    StockCandidateRequest,
    StockCandidateResponse,
    StockCandidateSymbol,
)
from app.schemas.stock_candidate_ai_explanation import (
    StockCandidateAIExplanationRequest,
    StockCandidateAIExplanationResponse,
)
from app.services.stock_candidate_ai_explanation_query_service import (
    StockCandidateAIExplanationQueryService,
)
from app.services.stock_candidate_query_service import StockCandidateQueryService

class StockAnalysisReactToolService:
    """Business tool executor used by the stock analysis ReAct graph.

    This service wraps project business capabilities as safe ReAct tools.
    It does not let the LLM access database objects directly.
    """

    MAX_STOCK_CANDIDATE_OBSERVATION_ITEMS = 10
    MAX_STOCK_CANDIDATE_EXCLUDED_ITEMS = 5
    MAX_STOCK_CANDIDATE_REASONS = 3
    MAX_STOCK_CANDIDATE_RISKS = 3
    MAX_STOCK_CANDIDATE_WARNINGS = 5
    MAX_STOCK_CANDIDATE_DATA_QUALITY_MESSAGES = 3
    MAX_STOCK_CANDIDATE_AI_EXPLANATIONS = 5
    MAX_STOCK_CANDIDATE_AI_COMPARISONS = 5
    MAX_STOCK_CANDIDATE_AI_PRIORITIES = 5
    MAX_STOCK_CANDIDATE_AI_TEXT_LENGTH = 600
    MAX_STOCK_CANDIDATE_AI_LIST_ITEMS = 3

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.analysis_record_repo = AsyncAnalysisRecordRepository(db)
        self.user_repo = AsyncUserRepository(db)
        self.user_preference_repo = AsyncUserPreferenceRepository(db)
        self.watchlist_repo = AsyncWatchlistRepository(db)
        self.market_service = MarketService(db)
        self.technical_indicator_query_service = TechnicalIndicatorQueryService(db)
        self.market_data_quality_report_service = MarketDataQualityReportService(db)
        self.backtest_query_service = BacktestQueryService(db)
        self.stock_candidate_query_service = StockCandidateQueryService(db)
        self.stock_candidate_ai_explanation_query_service = (
            StockCandidateAIExplanationQueryService(db)
        )

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

    async def get_stock_candidates(
        self,
        *,
        user_id: int,
        universe_source: str = "watchlist",
        symbols: list[dict[str, Any]] | None = None,
        top_n: int = 5,
        market: MarketCode | None = None,
        timeframe: CandleTimeframe = "1d",
        limit: int = 120,
        min_required_candles: int = 60,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
        include_excluded: bool = False,
        include_score_breakdown: bool = True,
        include_ai_explanation: bool = False,
        explanation_style: str = "balanced",
        max_candidates_to_explain: int = 3,
        enforce_data_quality: bool = True,
        data_quality_stale_after_days: int | None = None,
    ) -> ReactObservation:
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundException(
                message="current user does not exist",
                details=[
                    {
                        "field": "user_id",
                        "reason": "user not found",
                    }
                ],
            )

        normalized_universe_source = self._normalize_stock_candidate_universe_source(
            universe_source
        )
        safe_top_n = max(1, min(int(top_n), 10))
        safe_limit = max(30, min(int(limit), 300))
        safe_min_required_candles = max(
            30,
            min(int(min_required_candles), safe_limit),
        )

        candidate_symbols = self._build_stock_candidate_symbols(
            symbols=symbols or [],
            default_market=market,
        )

        request = StockCandidateRequest(
            universe_source=normalized_universe_source,
            symbols=candidate_symbols,
            top_n=safe_top_n,
            timeframe=timeframe,
            limit=safe_limit,
            min_required_candles=safe_min_required_candles,
            adjust_type=adjust_type,
            source=source,
            enforce_data_quality=enforce_data_quality,
            data_quality_stale_after_days=data_quality_stale_after_days,
            include_excluded=include_excluded,
            include_score_breakdown=include_score_breakdown,
            include_strategy_signal=True,
            include_data_quality=True,
        )

        ai_explanation_response: StockCandidateAIExplanationResponse | None = None

        if include_ai_explanation:
            ai_request = StockCandidateAIExplanationRequest(
                candidate_request=request,
                explanation_style=explanation_style,
                max_candidates_to_explain=min(
                    int(max_candidates_to_explain),
                    request.top_n,
                ),
                include_comparison=True,
                include_research_priority=True,
                include_risk_summary=True,
                allow_fallback=True,
            )

            ai_explanation_response = (
                await self.stock_candidate_ai_explanation_query_service.run_ai_explanation(
                    request=ai_request,
                    user=user,
                )
            )

            response = ai_explanation_response.source_candidate_result

            if response is None:
                response = await self.stock_candidate_query_service.run_stock_candidates(
                    request=request,
                    user=user,
                )
        else:
            response = await self.stock_candidate_query_service.run_stock_candidates(
                request=request,
                user=user,
            )

        return ReactObservation(
            tool_name="get_stock_candidates",
            tool_input={
                "user_id": user_id,
                "universe_source": request.universe_source,
                "symbols": [
                    item.model_dump(mode="json")
                    for item in request.symbols
                ],
                "top_n": request.top_n,
                "market": market,
                "timeframe": request.timeframe,
                "limit": request.limit,
                "min_required_candles": request.min_required_candles,
                "adjust_type": request.adjust_type,
                "source": request.source,
                "include_excluded": request.include_excluded,
                "include_score_breakdown": request.include_score_breakdown,
                "include_ai_explanation": include_ai_explanation,
                "explanation_style": explanation_style,
                "max_candidates_to_explain": max_candidates_to_explain,
                "enforce_data_quality": request.enforce_data_quality,
                "data_quality_stale_after_days": request.data_quality_stale_after_days,
            },
            tool_output=self._serialize_stock_candidate_response(
                response,
                include_ai_explanation=include_ai_explanation,
                ai_explanation_response=ai_explanation_response,
            ),
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
            "warnings": warnings[: self.MAX_STOCK_CANDIDATE_WARNINGS],
            "calculated_at": payload.get("calculated_at"),
            "disclaimer": payload.get("disclaimer"),
        }

    def _serialize_stock_candidate_item(
        self,
        item: dict[str, Any],
        *,
        include_score_breakdown: bool = True,
        include_strategy_signal: bool = True,
        include_data_quality: bool = True,
    ) -> dict[str, Any]:
        reasons = item.get("reasons") or []
        risks = item.get("risks") or []

        return {
            "symbol": item.get("symbol"),
            "market": item.get("market"),
            "name": item.get("name"),
            "decision": item.get("decision"),
            "excluded_reason": item.get("excluded_reason"),
            "rank": item.get("rank"),
            "score": item.get("score"),
            "grade": item.get("grade"),
            "reasons": reasons[: self.MAX_STOCK_CANDIDATE_REASONS],
            "risks": risks[: self.MAX_STOCK_CANDIDATE_RISKS],
            "score_breakdown": (
                self._build_stock_candidate_score_breakdown_observation(
                    item.get("score_breakdown")
                )
                if include_score_breakdown
                else None
            ),
            "strategy_signal": (
                self._build_stock_candidate_strategy_signal_observation(
                    item.get("strategy_signal")
                )
                if include_strategy_signal
                else None
            ),
            "data_quality": (
                self._build_stock_candidate_data_quality_observation(
                    item.get("data_quality")
                )
                if include_data_quality
                else None
            ),
        }

    def _serialize_stock_candidate_response(
        self,
        response: StockCandidateResponse,
        *,
        include_ai_explanation: bool = False,
        ai_explanation_response: StockCandidateAIExplanationResponse | None = None,
    ) -> dict[str, Any]:
        payload = response.model_dump(mode="json")
        candidates = payload.get("candidates") or []
        excluded = payload.get("excluded") or []
        warnings = payload.get("warnings") or []
        input_snapshot = payload.get("input_snapshot") or {}

        returned_candidates = candidates[
            : self.MAX_STOCK_CANDIDATE_OBSERVATION_ITEMS
        ]
        returned_excluded = excluded[
            : self.MAX_STOCK_CANDIDATE_EXCLUDED_ITEMS
        ]

        return {
            "status": payload.get("status"),
            "unavailable_reason": payload.get("unavailable_reason"),
            "summary": payload.get("summary"),
            "universe": {
                "source": input_snapshot.get("universe_source"),
                "requested_symbol_count": input_snapshot.get("requested_symbol_count"),
                "evaluated_symbol_count": input_snapshot.get("evaluated_symbol_count"),
                "candidate_count": input_snapshot.get("candidate_count"),
                "excluded_count": input_snapshot.get("excluded_count"),
                "top_n": input_snapshot.get("top_n"),
                "timeframe": input_snapshot.get("timeframe"),
                "limit": input_snapshot.get("limit"),
                "min_required_candles": input_snapshot.get("min_required_candles"),
                "adjust_type": input_snapshot.get("adjust_type"),
                "source_provider": input_snapshot.get("source"),
                "enforce_data_quality": input_snapshot.get("enforce_data_quality"),
            },
            "score_summary": self._build_stock_candidate_score_summary(candidates),
            "candidates": [
                self._serialize_stock_candidate_item(
                    item,
                    include_score_breakdown=True,
                    include_strategy_signal=True,
                    include_data_quality=True,
                )
                for item in returned_candidates
            ],
            "excluded": [
                self._serialize_stock_candidate_item(
                    item,
                    include_score_breakdown=False,
                    include_strategy_signal=False,
                    include_data_quality=True,
                )
                for item in returned_excluded
            ],
            "ai_explanation": self._serialize_stock_candidate_ai_explanation(
                ai_explanation_response,
                include_ai_explanation=include_ai_explanation,
            ),
            "warnings": warnings[:5],
            "calculated_at": payload.get("calculated_at"),
            "disclaimer": payload.get("disclaimer"),
            "output_limits": {
                "candidates_returned": len(returned_candidates),
                "candidates_total": len(candidates),
                "max_candidates_returned": self.MAX_STOCK_CANDIDATE_OBSERVATION_ITEMS,
                "excluded_returned": len(returned_excluded),
                "excluded_total": len(excluded),
                "max_excluded_returned": self.MAX_STOCK_CANDIDATE_EXCLUDED_ITEMS,
                "warnings_returned": min(
                    len(warnings),
                    self.MAX_STOCK_CANDIDATE_WARNINGS,
                ),
                "warnings_total": len(warnings),
                "reasons_per_candidate": self.MAX_STOCK_CANDIDATE_REASONS,
                "risks_per_candidate": self.MAX_STOCK_CANDIDATE_RISKS,
                "candidate_fields_policy": {
                    "candidates_include_score_breakdown": True,
                    "candidates_include_strategy_signal": True,
                    "candidates_include_data_quality": True,
                    "excluded_include_score_breakdown": False,
                    "excluded_include_strategy_signal": False,
                    "excluded_include_data_quality": True,
                },
                "full_source_candidate_result_included": False,
                "full_rule_results_included": False,
                "full_technical_indicators_included": False,
                "full_candles_included": False,
                "detail_policy": (
                    "Only trimmed candidate summaries are returned to the ReAct "
                    "observation. Full candidate response, full rule_results, "
                    "technical indicator objects, and K-line data are not included."
                ),
            },
        }

    def _build_stock_candidate_score_summary(
        self,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        scores = [
            item.get("score")
            for item in candidates
            if isinstance(item.get("score"), int | float)
        ]

        if not scores:
            return {
                "available": False,
                "highest_score": None,
                "lowest_score": None,
                "average_score": None,
            }

        return {
            "available": True,
            "highest_score": max(scores),
            "lowest_score": min(scores),
            "average_score": round(sum(scores) / len(scores), 2),
        }

    def _normalize_stock_candidate_universe_source(
        self,
        universe_source: str,
    ) -> str:
        normalized = str(universe_source or "watchlist").strip().lower()

        if normalized in {"manual", "watchlist"}:
            return normalized

        return "watchlist"

    def _build_stock_candidate_symbols(
        self,
        *,
        symbols: list[dict[str, Any]],
        default_market: MarketCode | None,
    ) -> list[StockCandidateSymbol]:
        candidate_symbols: list[StockCandidateSymbol] = []

        for item in symbols:
            if not isinstance(item, dict):
                continue

            raw_symbol = item.get("symbol")
            raw_market = item.get("market") or default_market

            if not raw_symbol or not raw_market:
                continue

            candidate_symbols.append(
                StockCandidateSymbol(
                    symbol=str(raw_symbol).strip().upper(),
                    market=raw_market,
                )
            )

        return candidate_symbols

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
            "risk_control_costs": {
                "total_commission": metrics.get("total_commission"),
                "total_slippage_cost": metrics.get("total_slippage_cost"),
            },
            "risk_control_triggers": {
                "stop_loss_trigger_count": metrics.get("stop_loss_trigger_count"),
                "take_profit_trigger_count": metrics.get("take_profit_trigger_count"),
                "cooldown_skip_count": metrics.get("cooldown_skip_count"),
                "drawdown_guard_trigger_count": metrics.get("drawdown_guard_trigger_count"),
            },
        }

    def _build_stock_candidate_strategy_signal_observation(
        self,
        strategy_signal: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not strategy_signal:
            return None

        return {
            "status": strategy_signal.get("status"),
            "signal": strategy_signal.get("signal"),
            "strength": strategy_signal.get("strength"),
            "score": strategy_signal.get("score"),
            "summary": strategy_signal.get("summary"),
        }

    def _build_backtest_data_context(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        input_snapshot = payload.get("input_snapshot") or {}
        risk_control = input_snapshot.get("risk_control") or {}

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
                "risk_control": {
                    "commission_rate": risk_control.get("commission_rate"),
                    "min_commission": risk_control.get("min_commission"),
                    "slippage_rate": risk_control.get("slippage_rate"),
                    "enable_stop_loss": risk_control.get("enable_stop_loss"),
                    "stop_loss_rate": risk_control.get("stop_loss_rate"),
                    "enable_take_profit": risk_control.get("enable_take_profit"),
                    "take_profit_rate": risk_control.get("take_profit_rate"),
                    "enable_cooldown": risk_control.get("enable_cooldown"),
                    "cooldown_days": risk_control.get("cooldown_days"),
                    "enable_max_drawdown_guard": risk_control.get("enable_max_drawdown_guard"),
                    "max_drawdown_guard_rate": risk_control.get("max_drawdown_guard_rate"),
                },
            },
            "result_lists": {
                "trades_count": len(payload.get("trades") or []),
                "daily_equity_count": len(payload.get("daily_equity") or []),
                "signal_snapshots_count": len(payload.get("signal_snapshots") or []),
            },
        }

    def _build_stock_candidate_score_breakdown_observation(
        self,
        score_breakdown: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not score_breakdown:
            return None

        return {
            "formula_version": score_breakdown.get("formula_version"),
            "base_score": score_breakdown.get("base_score"),
            "raw_score": score_breakdown.get("raw_score"),
            "final_score": score_breakdown.get("final_score"),
            "data_quality_score": score_breakdown.get("data_quality_score"),
            "trend_score": score_breakdown.get("trend_score"),
            "momentum_score": score_breakdown.get("momentum_score"),
            "rsi_score": score_breakdown.get("rsi_score"),
            "macd_score": score_breakdown.get("macd_score"),
            "volatility_score": score_breakdown.get("volatility_score"),
            "volume_score": score_breakdown.get("volume_score"),
            "strategy_signal_score": score_breakdown.get("strategy_signal_score"),
            "user_preference_score": score_breakdown.get("user_preference_score"),
            "risk_score": score_breakdown.get("risk_score"),
            "liquidity_score": score_breakdown.get("liquidity_score"),
            "backtest_performance_score": score_breakdown.get(
                "backtest_performance_score"
            ),
        }

    def _build_stock_candidate_data_quality_observation(
        self,
        data_quality: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not data_quality:
            return None

        warnings = data_quality.get("warnings") or []
        errors = data_quality.get("errors") or []

        return {
            "status": data_quality.get("status"),
            "candle_count": data_quality.get("candle_count"),
            "is_empty": data_quality.get("is_empty"),
            "is_enough": data_quality.get("is_enough"),
            "is_stale": data_quality.get("is_stale"),
            "warnings": warnings[: self.MAX_STOCK_CANDIDATE_DATA_QUALITY_MESSAGES],
            "errors": errors[: self.MAX_STOCK_CANDIDATE_DATA_QUALITY_MESSAGES],
        }

    def _serialize_stock_candidate_ai_explanation(
            self,
            response: StockCandidateAIExplanationResponse | None,
            *,
            include_ai_explanation: bool,
    ) -> dict[str, Any] | None:
        if not include_ai_explanation:
            return None

        if response is None:
            return {
                "included": False,
                "reason": "AI candidate explanation was requested but no response was generated.",
            }

        payload = response.model_dump(
            mode="json",
            exclude={"source_candidate_result"},
        )

        candidate_explanations = payload.get("candidate_explanations") or []
        comparisons = payload.get("comparisons") or []
        research_priorities = payload.get("research_priorities") or []
        warnings = payload.get("warnings") or []

        return {
            "included": True,
            "status": payload.get("status"),
            "unavailable_reason": payload.get("unavailable_reason"),
            "ai_used": payload.get("ai_used"),
            "fallback_reason": payload.get("fallback_reason"),
            "summary": self._limit_stock_candidate_ai_text(payload.get("summary")),
            "candidate_explanations": [
                self._serialize_stock_candidate_ai_explanation_item(item)
                for item in candidate_explanations[
                            : self.MAX_STOCK_CANDIDATE_AI_EXPLANATIONS
                            ]
            ],
            "comparisons": [
                self._serialize_stock_candidate_ai_comparison_item(item)
                for item in comparisons[: self.MAX_STOCK_CANDIDATE_AI_COMPARISONS]
            ],
            "research_priorities": [
                self._serialize_stock_candidate_ai_priority_item(item)
                for item in research_priorities[
                            : self.MAX_STOCK_CANDIDATE_AI_PRIORITIES
                            ]
            ],
            "risk_summary": self._serialize_stock_candidate_ai_risk_summary(
                payload.get("risk_summary")
            ),
            "warnings": warnings[: self.MAX_STOCK_CANDIDATE_WARNINGS],
            "generated_at": payload.get("generated_at"),
            "disclaimer": payload.get("disclaimer"),
            "output_limits": {
                "source_candidate_result_included": False,
                "max_candidate_explanations": self.MAX_STOCK_CANDIDATE_AI_EXPLANATIONS,
                "max_comparisons": self.MAX_STOCK_CANDIDATE_AI_COMPARISONS,
                "max_research_priorities": self.MAX_STOCK_CANDIDATE_AI_PRIORITIES,
                "max_text_length": self.MAX_STOCK_CANDIDATE_AI_TEXT_LENGTH,
                "max_list_items": self.MAX_STOCK_CANDIDATE_AI_LIST_ITEMS,
                "detail_policy": (
                    "AI explanation is trimmed before being returned to ReAct. "
                    "The original source_candidate_result is not nested here because "
                    "the deterministic candidate result is already returned separately."
                ),
            },
        }

    def _serialize_stock_candidate_ai_explanation_item(
            self,
            item: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "symbol": item.get("symbol"),
            "market": item.get("market"),
            "name": item.get("name"),
            "rank": item.get("rank"),
            "score": item.get("score"),
            "grade": item.get("grade"),
            "explanation": self._limit_stock_candidate_ai_text(
                item.get("explanation")
            ),
            "key_strengths": self._limit_stock_candidate_ai_list(
                item.get("key_strengths")
            ),
            "key_risks": self._limit_stock_candidate_ai_list(
                item.get("key_risks")
            ),
            "research_focus": self._limit_stock_candidate_ai_list(
                item.get("research_focus")
            ),
        }

    def _serialize_stock_candidate_ai_comparison_item(
            self,
            item: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "symbol": item.get("symbol"),
            "market": item.get("market"),
            "compared_with": (item.get("compared_with") or [])[
                             : self.MAX_STOCK_CANDIDATE_AI_LIST_ITEMS
                             ],
            "relative_strengths": self._limit_stock_candidate_ai_list(
                item.get("relative_strengths")
            ),
            "relative_weaknesses": self._limit_stock_candidate_ai_list(
                item.get("relative_weaknesses")
            ),
            "comparison_summary": self._limit_stock_candidate_ai_text(
                item.get("comparison_summary")
            ),
        }

    def _serialize_stock_candidate_ai_priority_item(
            self,
            item: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "priority_rank": item.get("priority_rank"),
            "priority_level": item.get("priority_level"),
            "symbol": item.get("symbol"),
            "market": item.get("market"),
            "grade": item.get("grade"),
            "score": item.get("score"),
            "reason": self._limit_stock_candidate_ai_text(item.get("reason")),
            "suggested_next_steps": self._limit_stock_candidate_ai_list(
                item.get("suggested_next_steps")
            ),
        }

    def _serialize_stock_candidate_ai_risk_summary(
            self,
            risk_summary: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not risk_summary:
            return None

        return {
            "overall_risk_level": risk_summary.get("overall_risk_level"),
            "summary": self._limit_stock_candidate_ai_text(
                risk_summary.get("summary")
            ),
            "key_risks": self._limit_stock_candidate_ai_list(
                risk_summary.get("key_risks")
            ),
            "risk_controls": self._limit_stock_candidate_ai_list(
                risk_summary.get("risk_controls")
            ),
        }

    def _limit_stock_candidate_ai_text(
            self,
            value: Any,
    ) -> str | None:
        if value is None:
            return None

        text = str(value).strip()
        if len(text) <= self.MAX_STOCK_CANDIDATE_AI_TEXT_LENGTH:
            return text

        return text[: self.MAX_STOCK_CANDIDATE_AI_TEXT_LENGTH] + "..."

    def _limit_stock_candidate_ai_list(
            self,
            values: Any,
    ) -> list[str]:
        if not isinstance(values, list):
            return []

        result: list[str] = []
        for value in values[: self.MAX_STOCK_CANDIDATE_AI_LIST_ITEMS]:
            text = self._limit_stock_candidate_ai_text(value)
            if text:
                result.append(text)

        return result

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