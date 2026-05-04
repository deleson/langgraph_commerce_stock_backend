from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.notification import NotificationResponse
from app.services.notification_service import AsyncNotificationService
from app.utils.responses import success_response

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    summary="List My Notifications",
    response_model=ApiResponse[list[NotificationResponse]],
)
async def list_my_notifications(
    current_user: CurrentUser,
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
    response_model=ApiResponse[NotificationResponse],
)
async def get_my_notification(
    notification_id: int,
    current_user: CurrentUser,
    db: AsyncDBSession,
):
    notification = await AsyncNotificationService(db).get_my_notification(
        user=current_user,
        notification_id=notification_id,
    )
    return success_response(data=NotificationResponse.model_validate(notification))


@router.patch(
    "/{notification_id}/read",
    summary="Mark My Notification As Read",
    response_model=ApiResponse[NotificationResponse],
)
async def mark_my_notification_as_read(
    notification_id: int,
    current_user: CurrentUser,
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
    current_user: CurrentUser,
    db: AsyncDBSession,
):
    updated_count = await AsyncNotificationService(db).mark_all_my_notifications_as_read(current_user)
    return success_response(data={"updated_count": updated_count})