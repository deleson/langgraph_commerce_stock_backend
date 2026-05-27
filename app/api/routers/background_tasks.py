from fastapi import APIRouter, Query, status

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.background_task import (
    BackgroundTaskCreateRequest,
    BackgroundTaskListQuery,
    BackgroundTaskListResponse,
    BackgroundTaskResponse,
    BackgroundTaskStatus,
    BackgroundTaskSubmitResponse,
    BackgroundTaskType,
)
from app.schemas.common import ApiResponse
from app.services.background_task_service import BackgroundTaskService
from app.utils.responses import success_response


router = APIRouter(prefix="/background-tasks", tags=["background-tasks"])


@router.post(
    "",
    summary="Submit Background Task",
    description=(
        "Submit a background task for the current user. "
        "The task will be recorded in database and dispatched to Celery."
    ),
    response_model=ApiResponse[BackgroundTaskSubmitResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_background_task(
    payload: BackgroundTaskCreateRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[BackgroundTaskSubmitResponse]:
    """Submit one background task.

    The router only handles HTTP concerns:
    - receive and validate request payload
    - require authenticated user
    - inject AsyncSession
    - call BackgroundTaskService
    - return unified API response
    """

    result = await BackgroundTaskService(db).submit_task(
        request=payload,
        user_id=current_user.id,
    )
    return success_response(data=result)


@router.get(
    "",
    summary="List Background Tasks",
    description=(
        "List background tasks submitted by the current user. "
        "Users can only see their own tasks."
    ),
    response_model=ApiResponse[BackgroundTaskListResponse],
    status_code=status.HTTP_200_OK,
)
async def list_background_tasks(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    task_type: BackgroundTaskType | None = Query(default=None),
    task_status: BackgroundTaskStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[BackgroundTaskListResponse]:
    """List current user's background tasks.

    The user_id is taken from the login token, not from query parameters,
    so users cannot read other users' background task records.
    """

    query = BackgroundTaskListQuery(
        task_type=task_type,
        status=task_status,
        limit=limit,
        offset=offset,
    )

    result = await BackgroundTaskService(db).list_tasks(
        query=query,
        user_id=current_user.id,
    )
    return success_response(data=result)


@router.get(
    "/{task_id}",
    summary="Get Background Task",
    description=(
        "Get one background task by id. "
        "Users can only access their own tasks."
    ),
    response_model=ApiResponse[BackgroundTaskResponse],
    status_code=status.HTTP_200_OK,
)
async def get_background_task(
    task_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[BackgroundTaskResponse]:
    """Get one background task detail."""

    result = await BackgroundTaskService(db).get_task(
        task_id=task_id,
        user_id=current_user.id,
    )
    return success_response(data=result)


@router.post(
    "/{task_id}/cancel",
    summary="Cancel Background Task",
    description=(
        "Cancel one background task. "
        "The first version only updates database status and does not revoke "
        "a running Celery task."
    ),
    response_model=ApiResponse[BackgroundTaskResponse],
    status_code=status.HTTP_200_OK,
)
async def cancel_background_task(
    task_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[BackgroundTaskResponse]:
    """Cancel one background task owned by the current user."""

    result = await BackgroundTaskService(db).cancel_task(
        task_id=task_id,
        user_id=current_user.id,
    )
    return success_response(data=result)