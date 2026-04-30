from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.schemas.common import ApiResponse
from app.schemas.notification import NotificationResponse
from app.services.notification_service import NotificationService
from app.utils.responses import success_response

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    summary="List My Notifications",
    response_model=ApiResponse[list[NotificationResponse]],
)
def list_my_notifications(
    current_user: CurrentUser,
    db: DBSession,
    unread_only: bool = Query(default=False, description="Only return unread notifications"),
):
    # Notification list is scoped by CurrentUser so users cannot read others' messages.
    notifications = NotificationService(db).list_my_notifications(
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
def get_my_notification(
    notification_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    notification = NotificationService(db).get_my_notification(
        user=current_user,
        notification_id=notification_id,
    )
    return success_response(data=NotificationResponse.model_validate(notification))


@router.patch(
    "/{notification_id}/read",
    summary="Mark My Notification As Read",
    response_model=ApiResponse[NotificationResponse],
)
def mark_my_notification_as_read(
    notification_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    # Mark-read is idempotent: reading an already-read notification returns it unchanged.
    notification = NotificationService(db).mark_my_notification_as_read(
        user=current_user,
        notification_id=notification_id,
    )
    return success_response(data=NotificationResponse.model_validate(notification))


@router.patch(
    "/read-all",
    summary="Mark All My Notifications As Read",
    response_model=ApiResponse[dict[str, int]],
)
def mark_all_my_notifications_as_read(
    current_user: CurrentUser,
    db: DBSession,
):
    updated_count = NotificationService(db).mark_all_my_notifications_as_read(current_user)
    return success_response(data={"updated_count": updated_count})