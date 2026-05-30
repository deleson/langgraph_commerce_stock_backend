import logging
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
from app.graphs.react_safety import sanitize_tool_output, truncate_text
from app.services.analysis_conversation_service import AnalysisConversationService
from app.services.user_memory_query_service import UserMemoryQueryService
from app.services.user_memory_retrieval_service import UserMemoryRetrievalService
from app.schemas.user_memory_embedding import UserMemoryRetrievalRequest

logger = logging.getLogger(__name__)

class StockAnalysisReactService:
    """Coordinate ReAct follow-up analysis for an existing stock analysis record.

    ReAct follow-up must start from an existing AnalysisRecord.
    This protects the business rule: users analyze first, then ask follow-up questions.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.analysis_record_repo = AsyncAnalysisRecordRepository(db)
        self.tool_service = StockAnalysisReactToolService(db)
        self.conversation_service = AnalysisConversationService(db)
        self.user_memory_query_service = UserMemoryQueryService(db)
        self.user_memory_retrieval_service = UserMemoryRetrievalService(db)

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

        conversation_context = await self.conversation_service.get_context(
            user_id=user.id,
            analysis_thread_id=payload.analysis_thread_id,
            limit=10,
        )
        user_profile_context = await self._load_user_profile_context(
            user_id=user.id,
        )
        relevant_memories_context = await self._load_relevant_memories_context(
            user_id=user.id,
            message=payload.message,
            symbol=record.symbol,
            market=record.market,
            user_profile_context=user_profile_context,
        )

        await self.conversation_service.save_user_message(
            user_id=user.id,
            analysis_record_id=record.id,
            analysis_thread_id=payload.analysis_thread_id,
            content=payload.message,
            source="react_follow_up",
            message_type="react_follow_up",
            payload={
                "referenced_symbol": record.symbol,
                "referenced_market": record.market,
                "max_iterations": payload.max_iterations,
            },
        )

        initial_state = self._build_initial_state(
            user=user,
            payload=payload,
            record=record,
            conversation_context=conversation_context.model_dump(mode="json"),
            user_profile_context=user_profile_context,
            relevant_memories_context=relevant_memories_context,
        )

        final_state = await arun_stock_analysis_react_graph(
            initial_state,
            tool_service=self.tool_service,
            react_graph_checkpoint_id=initial_state.get("react_graph_checkpoint_id"),
        )

        response = self._build_response(
            payload=payload,
            record=record,
            final_state=final_state,
        )

        await self.conversation_service.save_tool_observation_messages(
            user_id=user.id,
            analysis_record_id=record.id,
            analysis_thread_id=payload.analysis_thread_id,
            observations=response.observations,
        )

        await self.conversation_service.save_assistant_message(
            user_id=user.id,
            analysis_record_id=record.id,
            analysis_thread_id=payload.analysis_thread_id,
            content=response.answer,
            source="react_follow_up",
            message_type="react_follow_up",
            payload={
                "react_graph_checkpoint_id": response.react_graph_checkpoint_id,
                "used_tools": response.used_tools,
                "observation_count": len(response.observations),
                "trace_count": len(response.trace),
                "referenced_symbol": record.symbol,
                "referenced_market": record.market,
                "user_profile_context_available": user_profile_context is not None,
                "relevant_memories_context_available": relevant_memories_context is not None,
            },
        )

        await self.conversation_service.save_react_traces(
            user_id=user.id,
            analysis_record_id=record.id,
            analysis_thread_id=payload.analysis_thread_id,
            react_graph_checkpoint_id=response.react_graph_checkpoint_id,
            traces=response.trace,
        )

        return response

    def _build_initial_state(
        self,
        *,
        user: User,
        payload: StockAnalysisReactFollowUpRequest,
        record: AnalysisRecord,
        conversation_context: dict[str, Any],
        user_profile_context: dict[str, Any] | None,
        relevant_memories_context: dict[str, Any] | None,
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
            "conversation_context": conversation_context,
            "user_profile_context": user_profile_context,
            "relevant_memories_context": relevant_memories_context,
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
            return truncate_text(answer, max_length=3000)

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
                payload = observation.model_dump(mode="python")
                payload["tool_output"] = sanitize_tool_output(payload.get("tool_output"))
                result.append(ReactObservation.model_validate(payload))
                continue

            if isinstance(observation, dict):
                observation["tool_output"] = sanitize_tool_output(observation.get("tool_output"))
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

    async def _load_user_profile_context(
        self,
        *,
        user_id: int,
    ) -> dict[str, Any] | None:
        try:
            return await self.user_memory_query_service.get_profile_context(
                user_id=user_id,
                create_if_missing=True,
            )
        except Exception:
            logger.exception(
                "load user profile context for react failed",
                extra={"user_id": user_id},
            )
            return None

    async def _load_relevant_memories_context(
        self,
        *,
        user_id: int,
        message: str,
        symbol: str,
        market: str,
        user_profile_context: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        try:
            query = self._build_relevant_memory_query(
                message=message,
                symbol=symbol,
                market=market,
                user_profile_context=user_profile_context,
            )

            response = await self.user_memory_retrieval_service.search_similar_memories(
                user_id=user_id,
                request=UserMemoryRetrievalRequest(
                    query=query,
                    top_k=5,
                    min_similarity_score=None,
                    memory_types=[],
                    include_inactive=False,
                    include_content=False,
                ),
            )

            return {
                "available": response.status == "available",
                "status": response.status,
                "unavailable_reason": response.unavailable_reason,
                "summary": response.summary,
                "items": [
                    {
                        "memory_id": item.memory_id,
                        "memory_type": item.memory_type,
                        "confidence": item.confidence,
                        "title": item.title,
                        "summary": item.summary,
                        "keywords": item.keywords[:8],
                        "source_type": item.source_type,
                        "source_ref": item.source_ref,
                        "similarity_score": item.similarity_score,
                    }
                    for item in response.items[:5]
                ],
                "warnings": response.warnings[:3],
                "disclaimer": response.disclaimer,
            }
        except Exception:
            logger.exception(
                "load react relevant memories context failed",
                extra={
                    "user_id": user_id,
                    "symbol": symbol,
                    "market": market,
                },
            )
            return None

    def _build_relevant_memory_query(
        self,
        *,
        message: str,
        symbol: str,
        market: str,
        user_profile_context: dict[str, Any] | None,
    ) -> str:
        profile_summary = ""

        if isinstance(user_profile_context, dict):
            summary = user_profile_context.get("summary") or {}
            profile_summary = str(summary)

        return (
            f"用户正在围绕股票 {market}:{symbol} 进行追问。"
            f"用户追问内容：{message}。"
            f"请检索和该追问相关的用户长期记忆，包括风险关注点、研究偏好、沟通偏好、"
            f"分析上下文偏好、市场关注点和股票关注点。"
            f"用户画像摘要：{profile_summary}"
        )