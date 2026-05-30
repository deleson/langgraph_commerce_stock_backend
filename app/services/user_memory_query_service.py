from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user_memory import (
    UserMemoryListQuery,
    UserMemoryListResponse,
    UserMemoryResponse,
    UserMemoryUpdate,
    UserProfileRefreshRequest,
    UserProfileRefreshResponse,
    UserProfileResponse,
)
from app.services.user_memory_service import UserMemoryService
from app.services.user_profile_service import UserProfileService


class UserMemoryQueryService:
    """User memory query and profile orchestration service.

    This service is the unified entry for future API endpoints and Graph context
    injection. It does not extract memories and does not call the LLM.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        memory_service: UserMemoryService | None = None,
        profile_service: UserProfileService | None = None,
    ) -> None:
        self.db = db
        self.memory_service = memory_service or UserMemoryService(db)
        self.profile_service = profile_service or UserProfileService(db)

    async def list_memories(
        self,
        *,
        user_id: int,
        query: UserMemoryListQuery,
    ) -> UserMemoryListResponse:
        return await self.memory_service.list_memories(
            user_id=user_id,
            query=query,
        )

    async def get_memory(
        self,
        *,
        user_id: int,
        memory_id: int,
    ) -> UserMemoryResponse:
        return await self.memory_service.get_memory(
            user_id=user_id,
            memory_id=memory_id,
        )

    async def update_memory(
        self,
        *,
        user_id: int,
        memory_id: int,
        request: UserMemoryUpdate,
    ) -> UserMemoryResponse:
        return await self.memory_service.update_memory(
            user_id=user_id,
            memory_id=memory_id,
            request=request,
        )

    async def deactivate_memory(
        self,
        *,
        user_id: int,
        memory_id: int,
    ) -> UserMemoryResponse:
        return await self.memory_service.deactivate_memory(
            user_id=user_id,
            memory_id=memory_id,
        )

    async def get_profile(
        self,
        *,
        user_id: int,
        create_if_missing: bool = True,
    ) -> UserProfileResponse:
        if create_if_missing:
            return await self.profile_service.get_or_create_profile(user_id=user_id)

        return await self.memory_service.get_profile(user_id=user_id)

    async def refresh_profile(
        self,
        *,
        user_id: int,
        request: UserProfileRefreshRequest,
    ) -> UserProfileRefreshResponse:
        return await self.profile_service.refresh_profile(
            user_id=user_id,
            request=request,
        )

    async def get_profile_context(
        self,
        *,
        user_id: int,
        create_if_missing: bool = True,
    ) -> dict[str, Any]:
        profile = await self.get_profile(
            user_id=user_id,
            create_if_missing=create_if_missing,
        )

        return self._build_profile_context(profile)

    def _build_profile_context(
        self,
        profile: UserProfileResponse,
    ) -> dict[str, Any]:
        summary = profile.summary

        return {
            "status": profile.status,
            "profile_version": profile.profile_version,
            "risk_preference": summary.risk_preference,
            "preferred_markets": summary.preferred_markets,
            "frequent_symbols": summary.frequent_symbols,
            "interest_tags": summary.interest_tags,
            "research_preferences": summary.research_preferences,
            "risk_focuses": summary.risk_focuses,
            "communication_preferences": summary.communication_preferences,
            "summary": summary.summary,
            "evidence_count": summary.evidence_count,
            "refreshed_at": (
                profile.refreshed_at.isoformat()
                if profile.refreshed_at is not None
                else None
            ),
        }