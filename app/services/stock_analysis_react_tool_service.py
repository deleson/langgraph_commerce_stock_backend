from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.analysis_record import AnalysisRecord
from app.repositories.analysis_record_repo import AsyncAnalysisRecordRepository
from app.schemas.stock_analysis_react import ReactObservation


class StockAnalysisReactToolService:
    """Business tool executor used by the stock analysis ReAct graph.

    This service wraps project business capabilities as safe ReAct tools.
    It does not let the LLM access database objects directly.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.analysis_record_repo = AsyncAnalysisRecordRepository(db)

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