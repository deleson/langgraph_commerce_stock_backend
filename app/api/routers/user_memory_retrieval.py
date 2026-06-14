"""用户记忆检索 API Router。

该 Router 提供当前用户相似记忆检索接口。
检索结果只来自当前用户记忆，用于为 AI 分析和追问提供个性化上下文。
"""

from fastapi import APIRouter, status

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.user_memory_embedding import (
    UserMemoryRetrievalRequest,
    UserMemoryRetrievalResponse,
)
from app.services.user_memory_retrieval_service import UserMemoryRetrievalService
from app.utils.responses import success_response


router = APIRouter(
    prefix="/user-memory-retrieval",
    tags=["user-memory-retrieval"],
)


@router.post(
    "/search",
    summary="Search Similar User Memories",
    description=(
        "Search semantically similar long-term memories for the current user. "
        "The result is only used as user context and does not constitute "
        "investment advice."
    ),
    response_model=ApiResponse[UserMemoryRetrievalResponse],
    status_code=status.HTTP_200_OK,
)
async def search_similar_user_memories(
    payload: UserMemoryRetrievalRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[UserMemoryRetrievalResponse]:
    """检索当前用户的相似长期记忆。

    Router 只负责请求体、当前用户和数据库会话。
    向量检索、相似度计算和结果裁剪由 UserMemoryRetrievalService 处理。
    """

    result = await UserMemoryRetrievalService(db).search_similar_memories(
        user_id=current_user.id,
        request=payload,
    )
    return success_response(data=result)
