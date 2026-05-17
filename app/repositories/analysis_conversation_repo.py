from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_conversation_message import AnalysisConversationMessage
from app.models.analysis_react_trace import AnalysisReactTrace
from app.schemas.analysis_conversation import (
    AnalysisConversationMessageCreate,
    AnalysisConversationMessageQuery,
    AnalysisReactTraceCreate,
    AnalysisReactTraceQuery,
)


class AsyncAnalysisConversationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_next_sequence_no(
        self,
        *,
        user_id: int,
        analysis_thread_id: str,
    ) -> int:
        stmt = select(func.max(AnalysisConversationMessage.sequence_no)).where(
            AnalysisConversationMessage.user_id == user_id,
            AnalysisConversationMessage.analysis_thread_id == analysis_thread_id,
        )

        result = await self.db.execute(stmt)
        max_sequence_no = result.scalar_one_or_none()

        if max_sequence_no is None:
            return 1

        return int(max_sequence_no) + 1

    async def create_message(
        self,
        payload: AnalysisConversationMessageCreate,
    ) -> AnalysisConversationMessage:
        message = AnalysisConversationMessage(**payload.model_dump())
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def create_messages(
        self,
        payloads: list[AnalysisConversationMessageCreate],
    ) -> list[AnalysisConversationMessage]:
        messages = [
            AnalysisConversationMessage(**payload.model_dump())
            for payload in payloads
        ]

        self.db.add_all(messages)
        await self.db.commit()

        for message in messages:
            await self.db.refresh(message)

        return messages

    async def list_messages(
        self,
        *,
        user_id: int,
        query: AnalysisConversationMessageQuery,
    ) -> list[AnalysisConversationMessage]:
        stmt = select(AnalysisConversationMessage).where(
            AnalysisConversationMessage.user_id == user_id,
            AnalysisConversationMessage.analysis_thread_id == query.analysis_thread_id,
        )

        if query.role is not None:
            stmt = stmt.where(AnalysisConversationMessage.role == query.role)

        if query.message_type is not None:
            stmt = stmt.where(
                AnalysisConversationMessage.message_type == query.message_type
            )

        stmt = stmt.order_by(AnalysisConversationMessage.sequence_no.asc()).limit(
            query.limit
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_recent_context_messages(
        self,
        *,
        user_id: int,
        analysis_thread_id: str,
        limit: int = 10,
    ) -> list[AnalysisConversationMessage]:
        safe_limit = max(1, min(limit, 20))

        stmt = (
            select(AnalysisConversationMessage)
            .where(
                AnalysisConversationMessage.user_id == user_id,
                AnalysisConversationMessage.analysis_thread_id == analysis_thread_id,
                AnalysisConversationMessage.role.in_(("user", "assistant", "tool")),
            )
            .order_by(AnalysisConversationMessage.sequence_no.desc())
            .limit(safe_limit)
        )

        result = await self.db.execute(stmt)
        messages = list(result.scalars().all())
        return list(reversed(messages))

    async def create_trace(
        self,
        payload: AnalysisReactTraceCreate,
    ) -> AnalysisReactTrace:
        trace = AnalysisReactTrace(**payload.model_dump())
        self.db.add(trace)
        await self.db.commit()
        await self.db.refresh(trace)
        return trace

    async def create_traces(
        self,
        payloads: list[AnalysisReactTraceCreate],
    ) -> list[AnalysisReactTrace]:
        traces = [
            AnalysisReactTrace(**payload.model_dump())
            for payload in payloads
        ]

        self.db.add_all(traces)
        await self.db.commit()

        for trace in traces:
            await self.db.refresh(trace)

        return traces

    async def list_traces(
        self,
        *,
        user_id: int,
        query: AnalysisReactTraceQuery,
    ) -> list[AnalysisReactTrace]:
        stmt = select(AnalysisReactTrace).where(
            AnalysisReactTrace.user_id == user_id,
            AnalysisReactTrace.analysis_thread_id == query.analysis_thread_id,
        )

        if query.react_graph_checkpoint_id is not None:
            stmt = stmt.where(
                AnalysisReactTrace.react_graph_checkpoint_id
                == query.react_graph_checkpoint_id
            )

        if query.tool_name is not None:
            stmt = stmt.where(AnalysisReactTrace.tool_name == query.tool_name)

        if query.success is not None:
            stmt = stmt.where(AnalysisReactTrace.success == query.success)

        stmt = stmt.order_by(AnalysisReactTrace.step.asc()).limit(query.limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())