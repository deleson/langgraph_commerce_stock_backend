from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_user_id(
        self,
        user_id: int,
        *,
        unread_only: bool = False,
    ) -> list[Notification]:
        stmt = select(Notification).where(Notification.user_id == user_id)

        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))

        stmt = stmt.order_by(Notification.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def get_by_id_for_user(
        self,
        *,
        notification_id: int,
        user_id: int,
    ) -> Notification | None:
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def create(
        self,
        *,
        user_id: int,
        title: str,
        content: str,
        notification_type: str = "system",
        related_record_id: int | None = None,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            title=title,
            content=content,
            notification_type=notification_type,
            related_record_id=related_record_id,
            is_read=False,
        )
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def mark_as_read(self, notification: Notification) -> Notification:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def mark_all_as_read(self, user_id: int) -> int:
        notifications = self.list_by_user_id(user_id, unread_only=True)
        read_at = datetime.now(timezone.utc)

        for notification in notifications:
            notification.is_read = True
            notification.read_at = read_at
            self.db.add(notification)

        self.db.commit()
        return len(notifications)

class AsyncNotificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_user_id(
        self,
        user_id: int,
        *,
        unread_only: bool = False,
    ) -> list[Notification]:
        stmt = select(Notification).where(Notification.user_id == user_id)

        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))

        stmt = stmt.order_by(Notification.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_for_user(
        self,
        *,
        notification_id: int,
        user_id: int,
    ) -> Notification | None:
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: int,
        title: str,
        content: str,
        notification_type: str = "system",
        related_record_id: int | None = None,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            title=title,
            content=content,
            notification_type=notification_type,
            related_record_id=related_record_id,
            is_read=False,
        )
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def mark_as_read(self, notification: Notification) -> Notification:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def mark_all_as_read(self, user_id: int) -> int:
        notifications = await self.list_by_user_id(user_id, unread_only=True)
        read_at = datetime.now(timezone.utc)

        for notification in notifications:
            notification.is_read = True
            notification.read_at = read_at
            self.db.add(notification)

        await self.db.commit()
        return len(notifications)