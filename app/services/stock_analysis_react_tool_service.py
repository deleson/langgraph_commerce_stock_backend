from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.analysis_record import AnalysisRecord
from app.repositories.analysis_record_repo import AsyncAnalysisRecordRepository
from app.schemas.market import CandleTimeframe, MarketCode, MarketOverviewResponse
from app.schemas.market_data import AdjustType, MarketDataSource
from app.schemas.stock_analysis_react import ReactObservation
from app.schemas.technical_indicator import TechnicalIndicatorResponse
from app.services.market_service import MarketService
from app.services.technical_indicator_query_service import TechnicalIndicatorQueryService

class StockAnalysisReactToolService:
    """Business tool executor used by the stock analysis ReAct graph.

    This service wraps project business capabilities as safe ReAct tools.
    It does not let the LLM access database objects directly.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.analysis_record_repo = AsyncAnalysisRecordRepository(db)
        self.market_service = MarketService(db)
        self.technical_indicator_query_service = TechnicalIndicatorQueryService(db)

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