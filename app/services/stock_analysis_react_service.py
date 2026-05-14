from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.graphs.stock_analysis_react_graph import arun_stock_analysis_react_graph
from app.models.analysis_record import AnalysisRecord
from app.models.user import User
from app.repositories.analysis_record_repo import AsyncAnalysisRecordRepository
from app.schemas.stock_analysis_react import (
    ReactObservation,
    ReactToolName,
    ReactToolTrace,
    StockAnalysisReactFollowUpRequest,
    StockAnalysisReactFollowUpResponse,
)
from app.services.stock_analysis_react_tool_service import StockAnalysisReactToolService


class StockAnalysisReactService:
    """Coordinate ReAct follow-up analysis for an existing stock analysis record.

    ReAct follow-up must start from an existing AnalysisRecord.
    This protects the business rule: users analyze first, then ask follow-up questions.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.analysis_record_repo = AsyncAnalysisRecordRepository(db)
        self.tool_service = StockAnalysisReactToolService(db)

    async def follow_up_stock_analysis(
        self,
        *,
        user: User,
        payload: StockAnalysisReactFollowUpRequest,
    ) -> StockAnalysisReactFollowUpResponse:
        record = await self.analysis_record_repo.get_latest_by_thread_id_for_user(
            thread_id=payload.analysis_thread_id,
            user_id=user.id,
        )

        if record is None:
            raise NotFoundException(
                message="stock analysis thread not found",
                details=[
                    {
                        "field": "analysis_thread_id",
                        "reason": "analysis thread does not exist or does not belong to current user",
                    }
                ],
            )

        initial_state = self._build_initial_state(
            user=user,
            payload=payload,
            record=record,
        )

        final_state = await arun_stock_analysis_react_graph(
            initial_state,
            tool_service=self.tool_service,
            react_graph_checkpoint_id=initial_state.get("react_graph_checkpoint_id"),
        )

        return self._build_response(
            payload=payload,
            record=record,
            final_state=final_state,
        )

    def _build_initial_state(
        self,
        *,
        user: User,
        payload: StockAnalysisReactFollowUpRequest,
        record: AnalysisRecord,
    ) -> dict[str, Any]:
        result_snapshot = record.result_snapshot or {}
        context_snapshot = result_snapshot.get("context_snapshot") or {}

        return {
            "analysis_thread_id": payload.analysis_thread_id,
            "user_id": user.id,
            "message": payload.message,
            "referenced_analysis_record_id": record.id,
            "referenced_symbol": record.symbol,
            "referenced_market": record.market,
            "context_snapshot": context_snapshot,
            "result_snapshot": result_snapshot,
            "observations": [],
            "trace": [],
            "iteration_count": 0,
            "max_iterations": payload.max_iterations,
            "metadata": {
                "source": "stock_analysis_react_service",
                "analysis_record_id": record.id,
            },
        }

    def _build_response(
        self,
        *,
        payload: StockAnalysisReactFollowUpRequest,
        record: AnalysisRecord,
        final_state: dict[str, Any],
    ) -> StockAnalysisReactFollowUpResponse:
        observations = self._normalize_observations(
            final_state.get("observations", [])
        )
        trace = self._normalize_trace(final_state.get("trace", []))
        answer = self._resolve_final_answer(final_state)

        return StockAnalysisReactFollowUpResponse(
            analysis_thread_id=payload.analysis_thread_id,
            react_graph_checkpoint_id=final_state.get("react_graph_checkpoint_id"),
            answer=answer,
            used_tools=self._extract_used_tools(observations),
            observations=observations,
            trace=trace,
            referenced_analysis_record_id=record.id,
            referenced_symbol=record.symbol,
            referenced_market=record.market,
            created_at=datetime.now(UTC),
        )

    def _resolve_final_answer(
        self,
        final_state: dict[str, Any],
    ) -> str:
        answer = str(final_state.get("final_answer") or "").strip()
        if answer:
            return answer

        error_message = str(final_state.get("error_message") or "").strip()
        if error_message:
            return (
                "当前 ReAct 追问流程没有生成有效回答。"
                f"系统记录到的错误是：{error_message}。"
                "建议稍后重试，或换一个更具体的问题继续追问。"
            )

        return (
            "当前 ReAct 追问流程没有生成有效回答。"
            "建议稍后重试，或换一个更具体的问题继续追问。"
        )

    def _normalize_observations(
        self,
        observations: list[Any],
    ) -> list[ReactObservation]:
        result: list[ReactObservation] = []

        for observation in observations:
            if isinstance(observation, ReactObservation):
                result.append(observation)
                continue

            if isinstance(observation, dict):
                result.append(ReactObservation.model_validate(observation))

        return result

    def _normalize_trace(
        self,
        trace: list[Any],
    ) -> list[ReactToolTrace]:
        result: list[ReactToolTrace] = []

        for trace_item in trace:
            if isinstance(trace_item, ReactToolTrace):
                result.append(trace_item)
                continue

            if isinstance(trace_item, dict):
                result.append(ReactToolTrace.model_validate(trace_item))

        return result

    def _extract_used_tools(
        self,
        observations: list[ReactObservation],
    ) -> list[ReactToolName]:
        used_tools: list[ReactToolName] = []

        for observation in observations:
            tool_name = observation.tool_name
            if tool_name not in used_tools:
                used_tools.append(tool_name)

        return used_tools