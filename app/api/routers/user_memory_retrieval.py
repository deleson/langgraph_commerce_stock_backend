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
    """Search similar memories owned by the current user.

    Router only handles HTTP concerns:
    - receive and validate request payload
    - require authenticated user
    - inject AsyncSession
    - call UserMemoryRetrievalService
    - return unified API response
    """

    result = await UserMemoryRetrievalService(db).search_similar_memories(
        user_id=current_user.id,
        request=payload,
    )
    return success_response(data=result)