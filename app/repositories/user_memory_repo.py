from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_memory import UserMemory
from app.models.user_profile import UserProfile
from app.schemas.user_memory import (
    UserMemoryCreate,
    UserMemoryListQuery,
    UserMemoryUpdate,
    UserProfileCreate,
    UserProfileUpdate,
)


class AsyncUserMemoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_memory(self, payload: UserMemoryCreate) -> UserMemory:
        memory = UserMemory(**payload.model_dump())
        self.db.add(memory)
        await self.db.commit()
        await self.db.refresh(memory)
        return memory

    async def get_memory(
        self,
        *,
        memory_id: int,
        user_id: int,
    ) -> UserMemory | None:
        stmt = select(UserMemory).where(
            UserMemory.id == memory_id,
            UserMemory.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_memories(
        self,
        *,
        user_id: int,
        query: UserMemoryListQuery,
    ) -> list[UserMemory]:
        stmt = self._apply_memory_filters(
            select(UserMemory),
            user_id=user_id,
            query=query,
        )

        stmt = (
            stmt.order_by(
                UserMemory.weight.desc(),
                UserMemory.created_at.desc(),
            )
            .offset(query.offset)
            .limit(query.limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_memories(
        self,
        *,
        user_id: int,
        query: UserMemoryListQuery,
    ) -> int:
        stmt = self._apply_memory_filters(
            select(func.count(UserMemory.id)),
            user_id=user_id,
            query=query,
        )

        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def list_active_memories_for_profile(
        self,
        *,
        user_id: int,
        include_expired: bool = False,
        limit: int = 200,
    ) -> list[UserMemory]:
        stmt = select(UserMemory).where(
            UserMemory.user_id == user_id,
            UserMemory.status == "active",
        )

        if not include_expired:
            now = self._now()
            stmt = stmt.where(
                or_(
                    UserMemory.expires_at.is_(None),
                    UserMemory.expires_at > now,
                )
            )

        stmt = stmt.order_by(
            UserMemory.weight.desc(),
            UserMemory.created_at.desc(),
        ).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_memory(
        self,
        memory: UserMemory,
        payload: UserMemoryUpdate,
    ) -> UserMemory:
        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(memory, field, value)

        self.db.add(memory)
        await self.db.commit()
        await self.db.refresh(memory)
        return memory

    async def deactivate_memory(
        self,
        memory: UserMemory,
    ) -> UserMemory:
        memory.status = "inactive"

        self.db.add(memory)
        await self.db.commit()
        await self.db.refresh(memory)
        return memory

    async def get_profile(
        self,
        *,
        user_id: int,
    ) -> UserProfile | None:
        stmt = select(UserProfile).where(UserProfile.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_profile(
        self,
        payload: UserProfileCreate,
    ) -> UserProfile:
        profile = UserProfile(**payload.model_dump())
        self.db.add(profile)
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    async def get_or_create_profile(
        self,
        *,
        user_id: int,
    ) -> UserProfile:
        existing = await self.get_profile(user_id=user_id)
        if existing is not None:
            return existing

        return await self.create_profile(UserProfileCreate(user_id=user_id))

    async def update_profile(
        self,
        profile: UserProfile,
        payload: UserProfileUpdate,
    ) -> UserProfile:
        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(profile, field, value)

        self.db.add(profile)
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    def _apply_memory_filters(
        self,
        stmt,
        *,
        user_id: int,
        query: UserMemoryListQuery,
    ):
        stmt = stmt.where(UserMemory.user_id == user_id)

        if not query.include_inactive:
            stmt = stmt.where(UserMemory.status == "active")
        elif query.status is not None:
            stmt = stmt.where(UserMemory.status == query.status)

        if query.memory_type is not None:
            stmt = stmt.where(UserMemory.memory_type == query.memory_type)

        if query.confidence is not None:
            stmt = stmt.where(UserMemory.confidence == query.confidence)

        if query.source_type is not None:
            stmt = stmt.where(UserMemory.source_type == query.source_type)

        if query.keyword is not None:
            pattern = f"%{query.keyword}%"
            stmt = stmt.where(
                or_(
                    UserMemory.title.ilike(pattern),
                    UserMemory.content.ilike(pattern),
                    UserMemory.summary.ilike(pattern),
                    UserMemory.source_ref.ilike(pattern),
                )
            )

        return stmt

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)