"""通知 Service。

本文件负责通知列表、详情、创建和已读状态更新。
通知来自分析完成、日报生成、量化提醒等模块，读取和修改时必须绑定当前用户。
"""

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.notification import Notification
from app.models.user import User
from app.repositories.analysis_record_repo import AsyncAnalysisRecordRepository
from app.repositories.daily_report_repo import AsyncDailyReportRepository
from app.repositories.notification_repo import (
    AsyncNotificationRepository,
    NotificationRepository,
)
from app.schemas.analysis_record import AnalysisRecordResponse
from app.schemas.daily_report import DailyReportResponse
from app.schemas.notification import (
    NotificationCreateRequest,
    NotificationDetailResponse,
    NotificationResponse,
)


class NotificationService:
    """同步通知业务服务。"""

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
        """查询当前用户通知详情。"""

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
        """标记当前用户的一条通知为已读。"""

        notification = self.get_my_notification(
            user=user,
            notification_id=notification_id,
        )

        if notification.is_read:
            return notification

        return self.notification_repo.mark_as_read(notification)

    def mark_all_my_notifications_as_read(self, user: User) -> int:
        return self.notification_repo.mark_all_as_read(user.id)

    def delete_my_notification(
        self,
        *,
        user: User,
        notification_id: int,
    ) -> None:
        notification = self.get_my_notification(
            user=user,
            notification_id=notification_id,
        )
        self.notification_repo.delete(notification)

class AsyncNotificationService:
    """异步通知业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.notification_repo = AsyncNotificationRepository(db)
        self.analysis_record_repo = AsyncAnalysisRecordRepository(db)
        self.daily_report_repo = AsyncDailyReportRepository(db)

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
        """查询当前用户通知详情。"""

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

    async def get_my_notification_detail(
            self,
            *,
            user: User,
            notification_id: int,
    ) -> NotificationDetailResponse:
        notification = await self.get_my_notification(
            user=user,
            notification_id=notification_id,
        )

        analysis_record = None
        daily_report = None
        if notification.notification_type == "analysis_completed" and notification.related_record_id:
            record = await self.analysis_record_repo.get_by_id_for_user(
                record_id=notification.related_record_id,
                user_id=user.id,
            )
            if record is not None:
                analysis_record = AnalysisRecordResponse.model_validate(record)

        if notification.notification_type == "daily_report":
            if notification.related_record_id:
                report = await self.daily_report_repo.get_report(
                    report_id=notification.related_record_id,
                    user_id=user.id,
                )
            else:
                report = await self.daily_report_repo.get_report_by_notification_id(
                    notification_id=notification.id,
                    user_id=user.id,
                )
            if report is not None:
                daily_report = DailyReportResponse.model_validate(report)

        base_notification = NotificationResponse.model_validate(notification)
        return NotificationDetailResponse(
            **base_notification.model_dump(),
            analysis_record=analysis_record,
            daily_report=daily_report,
        )

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
        """标记当前用户的一条通知为已读。"""

        notification = await self.get_my_notification(
            user=user,
            notification_id=notification_id,
        )

        if notification.is_read:
            return notification

        return await self.notification_repo.mark_as_read(notification)

    async def mark_all_my_notifications_as_read(self, user: User) -> int:
        return await self.notification_repo.mark_all_as_read(user.id)

    async def delete_my_notification(
        self,
        *,
        user: User,
        notification_id: int,
    ) -> None:
        """删除当前用户的一条通知，但保留其来源业务记录。"""

        notification = await self.get_my_notification(
            user=user,
            notification_id=notification_id,
        )
        await self.notification_repo.delete(notification)
