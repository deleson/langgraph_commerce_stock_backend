"""用户偏好 Repository。

本文件封装 user_preferences 表的数据访问。每个用户通常只有一份偏好配置，
Service 层会在需要时获取或创建默认偏好。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.user_preference import UserPreference


class UserPreferenceRepository:
    """同步用户偏好数据访问对象。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_user_id(self, user_id: int) -> UserPreference | None:
        stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def create_default(
        self,
        user_id: int,
        *,
        timezone: str = "Asia/Shanghai",
        risk_preference: str = "balanced",
    ) -> UserPreference:
        preference = UserPreference(
            user_id=user_id,
            risk_preference=risk_preference,
            timezone=timezone,
            daily_report_enabled=False,
            abnormal_alert_enabled=False,
            default_watchlist_alert_enabled=False,
        )
        self.db.add(preference)
        self.db.commit()
        self.db.refresh(preference)
        return preference

    def save(self, preference: UserPreference) -> UserPreference:
        self.db.add(preference)
        self.db.commit()
        self.db.refresh(preference)
        return preference


class AsyncUserPreferenceRepository:
    """异步用户偏好数据访问对象。

    Repository 只保存偏好字段，不决定这些偏好如何影响日报、提醒或候选评分。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_default(
        self,
        user_id: int,
        *,
        timezone: str = "Asia/Shanghai",
        risk_preference: str = "balanced",
    ) -> UserPreference:
        preference = UserPreference(
            user_id=user_id,
            risk_preference=risk_preference,
            timezone=timezone,
            daily_report_enabled=False,
            abnormal_alert_enabled=False,
            default_watchlist_alert_enabled=False,
        )
        self.db.add(preference)
        await self.db.commit()
        await self.db.refresh(preference)
        return preference

    async def get_by_user_id(self,user_id: int) -> UserPreference | None:
        stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def save(self, preference: UserPreference) -> UserPreference:
        self.db.add(preference)
        await self.db.commit()
        await self.db.refresh(preference)
        return preference

