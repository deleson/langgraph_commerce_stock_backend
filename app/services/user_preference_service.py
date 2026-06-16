"""用户偏好 Service。

本文件负责用户偏好的获取、默认创建和更新。偏好会影响自选股默认提醒、
每日简报、量化提醒和候选评分等后续业务模块。
"""

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_preference import UserPreference
from app.repositories.user_preference_repo import UserPreferenceRepository
from app.schemas.preference import UserPreferenceUpdateRequest
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user_preference_repo import AsyncUserPreferenceRepository


class UserPreferenceService:
    """同步用户偏好业务服务。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.preference_repo = UserPreferenceRepository(db)

    def get_or_create_my_preference(self, user: User) -> UserPreference:
        """获取或创建当前用户偏好。

        默认偏好保证新用户无需手动配置，也能安全进入后续业务流程。
        """

        preference = self.preference_repo.get_by_user_id(user.id)
        if preference is not None:
            return preference

        return self.preference_repo.create_default(user.id)

    def update_my_preference(
        self,
        user: User,
        payload: UserPreferenceUpdateRequest,
    ) -> UserPreference:
        preference = self.get_or_create_my_preference(user)

        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(preference, field, value)

        return self.preference_repo.save(preference)


class AsyncUserPreferenceService:
    """异步用户偏好业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.preference_repo = AsyncUserPreferenceRepository(db)

    async def get_or_create_my_preference(self, user: User) -> UserPreference:
        """获取或创建当前用户偏好。"""

        preference = await self.preference_repo.get_by_user_id(user.id)
        if preference is not None:
            return preference

        return await self.preference_repo.create_default(user.id)

    async def update_my_preference(
        self,
        user: User,
        payload: UserPreferenceUpdateRequest,
    ) -> UserPreference:
        preference = await self.get_or_create_my_preference(user)

        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(preference, field, value)

        return await self.preference_repo.save(preference)

    async def get_daily_report_mode(self, user: User) -> UserPreference:
        """读取当前用户的日报模式配置。"""

        return await self.get_or_create_my_preference(user)

    async def update_daily_report_mode(
        self,
        user: User,
        *,
        enabled: bool,
    ) -> UserPreference:
        """开启或关闭当前用户的日报模式。"""

        preference = await self.get_or_create_my_preference(user)
        preference.daily_report_enabled = enabled
        return await self.preference_repo.save(preference)
