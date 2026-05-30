from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.user_memory import UserMemory
from app.repositories.user_memory_repo import AsyncUserMemoryRepository
from app.schemas.user_memory import (
    UserMemoryCreate,
    UserMemoryListQuery,
    UserMemoryListResponse,
    UserMemoryResponse,
    UserMemoryUpdate,
    UserProfileResponse,
)


class UserMemoryService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncUserMemoryRepository | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncUserMemoryRepository(db)

    async def create_memory(
        self,
        *,
        user_id: int,
        request: UserMemoryCreate,
    ) -> UserMemoryResponse:
        if request.user_id != user_id:
            raise BadRequestException(message="记忆所属用户与当前用户不一致")

        memory = await self.repository.create_memory(request)
        return self._build_memory_response(memory)

    async def get_memory(
        self,
        *,
        user_id: int,
        memory_id: int,
    ) -> UserMemoryResponse:
        memory = await self._get_memory_or_raise(
            user_id=user_id,
            memory_id=memory_id,
        )
        return self._build_memory_response(memory)

    async def list_memories(
        self,
        *,
        user_id: int,
        query: UserMemoryListQuery,
    ) -> UserMemoryListResponse:
        memories = await self.repository.list_memories(
            user_id=user_id,
            query=query,
        )
        total = await self.repository.count_memories(
            user_id=user_id,
            query=query,
        )

        return UserMemoryListResponse(
            items=[self._build_memory_response(memory) for memory in memories],
            total=total,
            limit=query.limit,
            offset=query.offset,
        )

    async def update_memory(
        self,
        *,
        user_id: int,
        memory_id: int,
        request: UserMemoryUpdate,
    ) -> UserMemoryResponse:
        memory = await self._get_memory_or_raise(
            user_id=user_id,
            memory_id=memory_id,
        )

        updated_memory = await self.repository.update_memory(
            memory,
            request,
        )
        return self._build_memory_response(updated_memory)

    async def deactivate_memory(
        self,
        *,
        user_id: int,
        memory_id: int,
    ) -> UserMemoryResponse:
        memory = await self._get_memory_or_raise(
            user_id=user_id,
            memory_id=memory_id,
        )

        deactivated_memory = await self.repository.deactivate_memory(memory)
        return self._build_memory_response(deactivated_memory)

    async def get_profile(
        self,
        *,
        user_id: int,
    ) -> UserProfileResponse:
        profile = await self.repository.get_profile(user_id=user_id)
        if profile is None:
            raise NotFoundException(message="用户画像不存在")

        return UserProfileResponse.model_validate(profile)

    async def get_or_create_profile(
        self,
        *,
        user_id: int,
    ) -> UserProfileResponse:
        profile = await self.repository.get_or_create_profile(user_id=user_id)
        return UserProfileResponse.model_validate(profile)

    async def _get_memory_or_raise(
        self,
        *,
        user_id: int,
        memory_id: int,
    ) -> UserMemory:
        memory = await self.repository.get_memory(
            user_id=user_id,
            memory_id=memory_id,
        )
        if memory is None:
            raise NotFoundException(message="用户记忆不存在")

        return memory

    def _build_memory_response(
        self,
        memory: UserMemory,
    ) -> UserMemoryResponse:
        return UserMemoryResponse.model_validate(memory)