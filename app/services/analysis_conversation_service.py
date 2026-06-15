"""分析会话 Service。

本文件负责保存普通追问、ReAct 追问、工具 Observation 和 ReAct trace。
这些记录用于恢复上下文、审计工具调用，并在用户消息中异步抽取长期记忆。
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.graphs.react_safety import (
    MAX_CONVERSATION_CONTENT_LENGTH,
    MAX_CONVERSATION_CONTEXT_MESSAGES,
    MAX_CONVERSATION_CONTEXT_MESSAGES_MAX,
    MAX_CONVERSATION_TOOL_CONTENT_LENGTH,
    MAX_CONVERSATION_TRACE_REASON_LENGTH,
    clamp_int,
    sanitize_for_react,
    sanitize_tool_input,
    sanitize_tool_output,
    truncate_text,
)
from app.repositories.analysis_conversation_repo import (
    AsyncAnalysisConversationRepository,
)
from app.schemas.analysis_conversation import (
    AnalysisConversationContext,
    AnalysisConversationContextMessage,
    AnalysisConversationMessageCreate,
    AnalysisConversationMessageQuery,
    AnalysisConversationMessageResponse,
    AnalysisReactTraceCreate,
    AnalysisReactTraceQuery,
    AnalysisReactTraceResponse,
    ConversationMessageType,
    ConversationRole,
    ConversationSource,
)
from app.schemas.stock_analysis_react import ReactObservation, ReactToolTrace
from app.services.user_memory_extraction_service import UserMemoryExtractionService

logger = logging.getLogger(__name__)

class AnalysisConversationService:
    """分析会话业务服务。

    会话数据属于用户私有上下文，所有保存和查询都必须携带 user_id。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.repo = AsyncAnalysisConversationRepository(db)
        self.memory_extraction_service = UserMemoryExtractionService(db)

    async def save_user_message(
        self,
        *,
        user_id: int,
        analysis_thread_id: str,
        content: str,
        analysis_record_id: int | None = None,
        source: ConversationSource = "react_follow_up",
        message_type: ConversationMessageType = "react_follow_up",
        payload: dict[str, Any] | None = None,
    ) -> AnalysisConversationMessageResponse:
        """保存用户消息，并尝试抽取用户记忆。

        记忆抽取失败不会影响主会话保存，避免附属能力拖垮追问流程。
        """

        message = await self._create_message(
            user_id=user_id,
            analysis_thread_id=analysis_thread_id,
            analysis_record_id=analysis_record_id,
            role="user",
            message_type=message_type,
            content=content,
            payload=payload,
            source=source,
        )

        await self._extract_memory_from_user_message(message)

        return message

    async def save_assistant_message(
        self,
        *,
        user_id: int,
        analysis_thread_id: str,
        content: str,
        analysis_record_id: int | None = None,
        source: ConversationSource = "react_follow_up",
        message_type: ConversationMessageType = "react_follow_up",
        payload: dict[str, Any] | None = None,
    ) -> AnalysisConversationMessageResponse:
        return await self._create_message(
            user_id=user_id,
            analysis_thread_id=analysis_thread_id,
            analysis_record_id=analysis_record_id,
            role="assistant",
            message_type=message_type,
            content=content,
            payload=payload,
            source=source,
        )

    async def save_tool_observation_messages(
        self,
        *,
        user_id: int,
        analysis_thread_id: str,
        observations: list[ReactObservation],
        analysis_record_id: int | None = None,
    ) -> list[AnalysisConversationMessageResponse]:
        """保存 ReAct 工具 Observation 消息。

        工具返回内容会经过清洗和截断，避免过长或不适合落库的内容污染会话历史。
        """

        if not observations:
            return []

        next_sequence_no = await self.repo.get_next_sequence_no(
            user_id=user_id,
            analysis_thread_id=analysis_thread_id,
        )

        payloads = [
            AnalysisConversationMessageCreate(
                user_id=user_id,
                analysis_record_id=analysis_record_id,
                analysis_thread_id=analysis_thread_id,
                role="tool",
                message_type="tool_observation",
                content=self._build_tool_observation_content(observation),
                payload=self._observation_to_payload(observation),
                source="react_follow_up",
                sequence_no=next_sequence_no + index,
            )
            for index, observation in enumerate(observations)
        ]

        messages = await self.repo.create_messages(payloads)
        return [
            AnalysisConversationMessageResponse.model_validate(message)
            for message in messages
        ]

    async def save_react_traces(
        self,
        *,
        user_id: int,
        analysis_thread_id: str,
        traces: list[ReactToolTrace],
        analysis_record_id: int | None = None,
        react_graph_checkpoint_id: str | None = None,
    ) -> list[AnalysisReactTraceResponse]:
        """保存 ReAct 工具调用 trace。

        trace 用于审计模型每一步工具选择、执行结果和失败原因。
        """

        if not traces:
            return []

        payloads = [
            AnalysisReactTraceCreate(
                user_id=user_id,
                analysis_record_id=analysis_record_id,
                analysis_thread_id=analysis_thread_id,
                react_graph_checkpoint_id=react_graph_checkpoint_id,
                step=trace.step,
                action=trace.action,
                tool_name=trace.tool_name,
                reason=(
                    truncate_text(
                        trace.reason,
                        max_length=MAX_CONVERSATION_TRACE_REASON_LENGTH,
                    )
                    if trace.reason is not None
                    else None
                ),
                tool_input=None,
                tool_output=None,
                success=trace.success,
                error_message=(
                    truncate_text(
                        trace.error_message,
                        max_length=MAX_CONVERSATION_TRACE_REASON_LENGTH,
                    )
                    if trace.error_message is not None
                    else None
                ),
                duration_ms=trace.duration_ms,
            )
            for trace in traces
        ]

        saved_traces = await self.repo.create_traces(payloads)
        return [
            AnalysisReactTraceResponse.model_validate(trace)
            for trace in saved_traces
        ]

    async def get_messages(
        self,
        *,
        user_id: int,
        query: AnalysisConversationMessageQuery,
    ) -> list[AnalysisConversationMessageResponse]:
        messages = await self.repo.list_messages(user_id=user_id, query=query)
        return [
            AnalysisConversationMessageResponse.model_validate(message)
            for message in messages
        ]

    async def get_traces(
        self,
        *,
        user_id: int,
        query: AnalysisReactTraceQuery,
    ) -> list[AnalysisReactTraceResponse]:
        traces = await self.repo.list_traces(user_id=user_id, query=query)
        return [
            AnalysisReactTraceResponse.model_validate(trace)
            for trace in traces
        ]

    async def get_context(
        self,
        *,
        user_id: int,
        analysis_thread_id: str,
        limit: int = 10,
    ) -> AnalysisConversationContext:
        """读取最近会话上下文。

        limit 会被限制在安全范围内，避免一次性把过多历史消息塞回 LLM 上下文。
        """

        safe_limit = clamp_int(
            limit,
            default=MAX_CONVERSATION_CONTEXT_MESSAGES,
            min_value=1,
            max_value=MAX_CONVERSATION_CONTEXT_MESSAGES_MAX,
        )
        messages = await self.repo.list_recent_context_messages(
            user_id=user_id,
            analysis_thread_id=analysis_thread_id,
            limit=safe_limit,
        )

        context_messages = [
            AnalysisConversationContextMessage(
                role=message.role,
                content=self._normalize_content(message.content),
                payload=self._normalize_payload(message.payload),
                message_type=message.message_type,
                sequence_no=message.sequence_no,
            )
            for message in messages
        ]

        return AnalysisConversationContext(
            analysis_thread_id=analysis_thread_id,
            messages=context_messages,
            message_count=len(context_messages),
        )

    async def _extract_memory_from_user_message(
        self,
        message: AnalysisConversationMessageResponse,
    ) -> None:
        """从用户消息中抽取长期记忆。

        这是附属增强能力，失败时只记录日志，不影响用户追问主链路。
        """

        try:
            await self.memory_extraction_service.extract_from_conversation_message(
                user_id=message.user_id,
                message_id=message.id,
                analysis_thread_id=message.analysis_thread_id,
                analysis_record_id=message.analysis_record_id,
                content=message.content,
                message_type=message.message_type,
                source=message.source,
                payload=message.payload,
            )
        except Exception:
            logger.exception(
                "failed to extract user memory from conversation message",
                extra={
                    "user_id": message.user_id,
                    "message_id": message.id,
                    "analysis_thread_id": message.analysis_thread_id,
                },
            )

    async def _create_message(
        self,
        *,
        user_id: int,
        analysis_thread_id: str,
        role: ConversationRole,
        message_type: ConversationMessageType,
        source: ConversationSource,
        content: str | None = None,
        payload: dict[str, Any] | None = None,
        analysis_record_id: int | None = None,
    ) -> AnalysisConversationMessageResponse:
        """创建单条会话消息并分配线程内序号。"""

        sequence_no = await self.repo.get_next_sequence_no(
            user_id=user_id,
            analysis_thread_id=analysis_thread_id,
        )

        message = await self.repo.create_message(
            AnalysisConversationMessageCreate(
                user_id=user_id,
                analysis_record_id=analysis_record_id,
                analysis_thread_id=analysis_thread_id,
                role=role,
                message_type=message_type,
                content=self._normalize_content(content),
                payload=self._normalize_payload(payload),
                source=source,
                sequence_no=sequence_no,
            )
        )

        return AnalysisConversationMessageResponse.model_validate(message)

    def _normalize_content(self, content: str | None) -> str | None:
        if content is None:
            return None
        return truncate_text(
            content,
            max_length=MAX_CONVERSATION_CONTENT_LENGTH,
        )

    def _normalize_payload(
        self,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """清洗可落库的 payload。

        ReAct 相关 payload 可能来自工具输入输出，落库前需要做安全清洗。
        """

        if payload is None:
            return None

        sanitized = sanitize_for_react(payload)
        if isinstance(sanitized, dict):
            return sanitized

        return {"value": sanitized}

    def _build_tool_observation_content(
        self,
        observation: ReactObservation,
    ) -> str:
        if observation.success:
            return f"Tool observation: {observation.tool_name}"

        error_message = observation.error_message or "unknown tool error"
        return truncate_text(
            f"Tool observation failed: {observation.tool_name}; {error_message}",
            max_length=MAX_CONVERSATION_TOOL_CONTENT_LENGTH,
        )

    def _observation_to_payload(
        self,
        observation: ReactObservation,
    ) -> dict[str, Any]:
        return {
            "tool_name": observation.tool_name,
            "tool_input": sanitize_tool_input(observation.tool_input),
            "tool_output": sanitize_tool_output(observation.tool_output),
            "success": observation.success,
            "error_message": observation.error_message,
            "created_at": (
                observation.created_at.isoformat()
                if observation.created_at is not None
                else None
            ),
        }
