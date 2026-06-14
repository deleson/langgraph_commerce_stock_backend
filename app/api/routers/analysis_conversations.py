"""分析会话 API Router。

该 Router 用于查询个股分析线程中的会话消息、ReAct Trace 和聚合上下文。
所有查询都基于当前登录用户，避免用户读取其他人的分析会话。
"""

from fastapi import APIRouter, Path, Query

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.analysis_conversation import (
    AnalysisConversationContext,
    AnalysisConversationMessageQuery,
    AnalysisConversationMessageResponse,
    AnalysisReactTraceQuery,
    AnalysisReactTraceResponse,
    ConversationMessageType,
    ConversationRole,
)
from app.schemas.common import ApiResponse
from app.schemas.stock_analysis_react import ReactToolName
from app.services.analysis_conversation_service import AnalysisConversationService
from app.utils.responses import success_response


router = APIRouter(
    prefix="/analysis-conversations",
    tags=["analysis-conversations"],
)


@router.get(
    "/{analysis_thread_id}/messages",
    summary="List Analysis Conversation Messages",
    response_model=ApiResponse[list[AnalysisConversationMessageResponse]],
)
async def list_analysis_conversation_messages(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    analysis_thread_id: str = Path(
        min_length=1,
        max_length=120,
        description="Analysis conversation thread id returned by stock analysis API.",
    ),
    role: ConversationRole | None = Query(
        default=None,
        description="Optional message role filter: user, assistant, tool, or system.",
    ),
    message_type: ConversationMessageType | None = Query(
        default=None,
        description="Optional message type filter.",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of messages.",
    ),
) -> ApiResponse[list[AnalysisConversationMessageResponse]]:
    messages = await AnalysisConversationService(db).get_messages(
        user_id=current_user.id,
        query=AnalysisConversationMessageQuery(
            analysis_thread_id=analysis_thread_id,
            role=role,
            message_type=message_type,
            limit=limit,
        ),
    )

    return success_response(data=messages)


@router.get(
    "/{analysis_thread_id}/traces",
    summary="List Analysis ReAct Traces",
    response_model=ApiResponse[list[AnalysisReactTraceResponse]],
)
async def list_analysis_react_traces(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    analysis_thread_id: str = Path(
        min_length=1,
        max_length=120,
        description="Analysis conversation thread id returned by stock analysis API.",
    ),
    react_graph_checkpoint_id: str | None = Query(
        default=None,
        max_length=160,
        description="Optional ReAct graph checkpoint id filter.",
    ),
    tool_name: ReactToolName | None = Query(
        default=None,
        description="Optional ReAct tool name filter.",
    ),
    success: bool | None = Query(
        default=None,
        description="Optional success filter.",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of traces.",
    ),
) -> ApiResponse[list[AnalysisReactTraceResponse]]:
    traces = await AnalysisConversationService(db).get_traces(
        user_id=current_user.id,
        query=AnalysisReactTraceQuery(
            analysis_thread_id=analysis_thread_id,
            react_graph_checkpoint_id=react_graph_checkpoint_id,
            tool_name=tool_name,
            success=success,
            limit=limit,
        ),
    )

    return success_response(data=traces)


@router.get(
    "/{analysis_thread_id}/context",
    summary="Get Recent Analysis Conversation Context",
    response_model=ApiResponse[AnalysisConversationContext],
)
async def get_analysis_conversation_context(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    analysis_thread_id: str = Path(
        min_length=1,
        max_length=120,
        description="Analysis conversation thread id returned by stock analysis API.",
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=20,
        description="Maximum recent context messages.",
    ),
) -> ApiResponse[AnalysisConversationContext]:
    context = await AnalysisConversationService(db).get_context(
        user_id=current_user.id,
        analysis_thread_id=analysis_thread_id,
        limit=limit,
    )

    return success_response(data=context)
