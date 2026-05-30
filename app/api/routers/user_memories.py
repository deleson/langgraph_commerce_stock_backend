from fastapi import APIRouter, Query, status

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.user_memory import (
    UserMemoryConfidence,
    UserMemoryListQuery,
    UserMemoryListResponse,
    UserMemoryResponse,
    UserMemorySourceType,
    UserMemoryStatus,
    UserMemoryType,
    UserMemoryUpdate,
    UserProfileRefreshRequest,
    UserProfileRefreshResponse,
    UserProfileResponse,
)
from app.services.user_memory_query_service import UserMemoryQueryService
from app.utils.responses import success_response


router = APIRouter(prefix="/user-memories", tags=["user-memories"])


@router.get(
    "",
    summary="List User Memories",
    description=(
        "List long-term user memories for the current user. "
        "Users can only access their own memories."
    ),
    response_model=ApiResponse[UserMemoryListResponse],
    status_code=status.HTTP_200_OK,
)
async def list_user_memories(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    memory_type: UserMemoryType | None = Query(default=None),
    memory_status: UserMemoryStatus | None = Query(default=None, alias="status"),
    confidence: UserMemoryConfidence | None = Query(default=None),
    source_type: UserMemorySourceType | None = Query(default=None),
    keyword: str | None = Query(default=None, min_length=1, max_length=50),
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[UserMemoryListResponse]:
    """List memories owned by the current user."""

    query = UserMemoryListQuery(
        memory_type=memory_type,
        status=memory_status,
        confidence=confidence,
        source_type=source_type,
        keyword=keyword,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )

    result = await UserMemoryQueryService(db).list_memories(
        user_id=current_user.id,
        query=query,
    )
    return success_response(data=result)


@router.get(
    "/profile",
    summary="Get User Profile",
    description=(
        "Get the current user's aggregated profile. "
        "If the profile does not exist, the first version creates an empty profile."
    ),
    response_model=ApiResponse[UserProfileResponse],
    status_code=status.HTTP_200_OK,
)
async def get_user_profile(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[UserProfileResponse]:
    """Get current user's profile."""

    result = await UserMemoryQueryService(db).get_profile(
        user_id=current_user.id,
        create_if_missing=True,
    )
    return success_response(data=result)


@router.post(
    "/profile/refresh",
    summary="Refresh User Profile",
    description=(
        "Refresh the current user's profile from memories, user preference, "
        "watchlist, and analysis records."
    ),
    response_model=ApiResponse[UserProfileRefreshResponse],
    status_code=status.HTTP_200_OK,
)
async def refresh_user_profile(
    payload: UserProfileRefreshRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[UserProfileRefreshResponse]:
    """Refresh current user's profile."""

    result = await UserMemoryQueryService(db).refresh_profile(
        user_id=current_user.id,
        request=payload,
    )
    return success_response(data=result)


@router.get(
    "/{memory_id}",
    summary="Get User Memory",
    description=(
        "Get one user memory by id. "
        "Users can only access their own memories."
    ),
    response_model=ApiResponse[UserMemoryResponse],
    status_code=status.HTTP_200_OK,
)
async def get_user_memory(
    memory_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[UserMemoryResponse]:
    """Get one memory owned by the current user."""

    result = await UserMemoryQueryService(db).get_memory(
        user_id=current_user.id,
        memory_id=memory_id,
    )
    return success_response(data=result)


@router.patch(
    "/{memory_id}",
    summary="Update User Memory",
    description=(
        "Update one user memory. "
        "Users can only update memories that belong to themselves."
    ),
    response_model=ApiResponse[UserMemoryResponse],
    status_code=status.HTTP_200_OK,
)
async def update_user_memory(
    memory_id: int,
    payload: UserMemoryUpdate,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[UserMemoryResponse]:
    """Update one memory owned by the current user."""

    result = await UserMemoryQueryService(db).update_memory(
        user_id=current_user.id,
        memory_id=memory_id,
        request=payload,
    )
    return success_response(data=result)


@router.post(
    "/{memory_id}/deactivate",
    summary="Deactivate User Memory",
    description=(
        "Deactivate one user memory instead of deleting it. "
        "The memory will become inactive and can be excluded from profile aggregation."
    ),
    response_model=ApiResponse[UserMemoryResponse],
    status_code=status.HTTP_200_OK,
)
async def deactivate_user_memory(
    memory_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[UserMemoryResponse]:
    """Deactivate one memory owned by the current user."""

    result = await UserMemoryQueryService(db).deactivate_memory(
        user_id=current_user.id,
        memory_id=memory_id,
    )
    return success_response(data=result)