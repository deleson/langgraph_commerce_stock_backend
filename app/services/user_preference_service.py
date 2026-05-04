from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_preference import UserPreference
from app.repositories.user_preference_repo import UserPreferenceRepository
from app.schemas.preference import UserPreferenceUpdateRequest
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user_preference_repo import AsyncUserPreferenceRepository


class UserPreferenceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.preference_repo = UserPreferenceRepository(db)

    def get_or_create_my_preference(self, user: User) -> UserPreference:
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
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.preference_repo = AsyncUserPreferenceRepository(db)

    async def get_or_create_my_preference(self, user: User) -> UserPreference:
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