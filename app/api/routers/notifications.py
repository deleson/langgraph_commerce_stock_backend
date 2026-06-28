"""通知 API Router。

该 Router 提供当前用户通知列表、详情、单条已读和全部已读接口。
通知数据必须按当前用户隔离，不能跨用户读取或修改。
"""

from fastapi import APIRouter, Query

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.notification import NotificationDetailResponse, NotificationResponse
from app.services.notification_service import AsyncNotificationService
from app.utils.responses import success_response

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    summary="List My Notifications",
    response_model=ApiResponse[list[NotificationResponse]],
)
async def list_my_notifications(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    unread_only: bool = Query(default=False, description="Only return unread notifications"),
):
    # Notification list is scoped by CurrentUser so users cannot read others' messages.
    notifications = await AsyncNotificationService(db).list_my_notifications(
        current_user,
        unread_only=unread_only,
    )
    return success_response(
        data=[
            NotificationResponse.model_validate(notification)
            for notification in notifications
        ]
    )


@router.get(
    "/{notification_id}",
    summary="Get My Notification",
    response_model=ApiResponse[NotificationDetailResponse],
)
async def get_my_notification(
    notification_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
):
    detail = await AsyncNotificationService(db).get_my_notification_detail(
        user=current_user,
        notification_id=notification_id,
    )
    return success_response(data=detail)


@router.patch(
    "/{notification_id}/read",
    summary="Mark My Notification As Read",
    response_model=ApiResponse[NotificationResponse],
)
async def mark_my_notification_as_read(
    notification_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
):
    # Mark-read is idempotent: reading an already-read notification returns it unchanged.
    notification = await AsyncNotificationService(db).mark_my_notification_as_read(
        user=current_user,
        notification_id=notification_id,
    )
    return success_response(data=NotificationResponse.model_validate(notification))


@router.patch(
    "/read-all",
    summary="Mark All My Notifications As Read",
    response_model=ApiResponse[dict[str, int]],
)
async def mark_all_my_notifications_as_read(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
):
    updated_count = await AsyncNotificationService(db).mark_all_my_notifications_as_read(current_user)
    return success_response(data={"updated_count": updated_count})
