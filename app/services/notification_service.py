from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.notification import Notification
from app.models.user import User
from app.repositories.notification_repo import NotificationRepository,AsyncNotificationRepository
from app.schemas.notification import NotificationCreateRequest


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.notification_repo = NotificationRepository(db)

    def list_my_notifications(
        self,
        user: User,
        *,
        unread_only: bool = False,
    ) -> list[Notification]:
        return self.notification_repo.list_by_user_id(
            user.id,
            unread_only=unread_only,
        )

    def get_my_notification(
        self,
        *,
        user: User,
        notification_id: int,
    ) -> Notification:
        notification = self.notification_repo.get_by_id_for_user(
            notification_id=notification_id,
            user_id=user.id,
        )
        if notification is None:
            raise NotFoundException(
                message="notification not found",
                details=[
                    {
                        "field": "notification_id",
                        "reason": "notification does not exist",
                    }
                ],
            )

        return notification

    def create_notification(
        self,
        *,
        user: User,
        payload: NotificationCreateRequest,
    ) -> Notification:
        return self.notification_repo.create(
            user_id=user.id,
            title=payload.title,
            content=payload.content,
            notification_type=payload.notification_type,
            related_record_id=payload.related_record_id,
        )

    def mark_my_notification_as_read(
        self,
        *,
        user: User,
        notification_id: int,
    ) -> Notification:
        notification = self.get_my_notification(
            user=user,
            notification_id=notification_id,
        )

        if notification.is_read:
            return notification

        return self.notification_repo.mark_as_read(notification)

    def mark_all_my_notifications_as_read(self, user: User) -> int:
        return self.notification_repo.mark_all_as_read(user.id)

class AsyncNotificationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.notification_repo = AsyncNotificationRepository(db)

    async def list_my_notifications(
            self,
            user: User,
            *,
            unread_only: bool = False,
    ) -> list[Notification]:
        return await self.notification_repo.list_by_user_id(
            user.id,
            unread_only=unread_only,
        )

    async def get_my_notification(
            self,
            *,
            user: User,
            notification_id: int,
    ) -> Notification:
        notification = await self.notification_repo.get_by_id_for_user(
            notification_id=notification_id,
            user_id=user.id,
        )
        if notification is None:
            raise NotFoundException(
                message="notification not found",
                details=[
                    {
                        "field": "notification_id",
                        "reason": "notification does not exist",
                    }
                ],
            )

        return notification

    async def create_notification(
            self,
            *,
            user: User,
            payload: NotificationCreateRequest,
    ) -> Notification:
        return await self.notification_repo.create(
            user_id=user.id,
            title=payload.title,
            content=payload.content,
            notification_type=payload.notification_type,
            related_record_id=payload.related_record_id,
        )

    async def mark_my_notification_as_read(
            self,
            *,
            user: User,
            notification_id: int,
    ) -> Notification:
        notification = await self.get_my_notification(
            user=user,
            notification_id=notification_id,
        )

        if notification.is_read:
            return notification

        return await self.notification_repo.mark_as_read(notification)

    async def mark_all_my_notifications_as_read(self, user: User) -> int:
        return await self.notification_repo.mark_all_as_read(user.id)