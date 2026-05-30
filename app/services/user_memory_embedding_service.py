from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.user_memory import UserMemory
from app.repositories.user_memory_embedding_repo import (
    AsyncUserMemoryEmbeddingRepository,
)
from app.repositories.user_memory_repo import AsyncUserMemoryRepository
from app.schemas.user_memory_embedding import (
    UserMemoryEmbeddingBuildSource,
    UserMemoryEmbeddingCreate,
    UserMemoryEmbeddingProvider,
    UserMemoryEmbeddingResponse,
    UserMemoryEmbeddingUpdate,
)
from app.services.embedding_service import EmbeddingService


class UserMemoryEmbeddingService:
    """Build and persist embeddings for UserMemory records.

    This service coordinates memory loading, embedding text construction,
    vector generation, and database persistence. It does not perform similarity
    search; retrieval will be handled by UserMemoryRetrievalService later.
    """

    MAX_EMBEDDING_TEXT_LENGTH = 2000
    DEFAULT_BUILD_LIMIT = 100

    def __init__(
        self,
        db: AsyncSession,
        *,
        memory_repository: AsyncUserMemoryRepository | None = None,
        embedding_repository: AsyncUserMemoryEmbeddingRepository | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.db = db
        self.memory_repository = memory_repository or AsyncUserMemoryRepository(db)
        self.embedding_repository = (
            embedding_repository or AsyncUserMemoryEmbeddingRepository(db)
        )
        self.embedding_service = embedding_service or EmbeddingService()

    async def build_embedding_for_memory(
        self,
        *,
        user_id: int,
        memory_id: int,
        provider: UserMemoryEmbeddingProvider = "mock",
        model_name: str | None = None,
        dimension: int = EmbeddingService.DEFAULT_DIMENSION,
        build_source: UserMemoryEmbeddingBuildSource = "system",
        force_rebuild: bool = False,
    ) -> UserMemoryEmbeddingResponse:
        memory = await self.memory_repository.get_memory(
            user_id=user_id,
            memory_id=memory_id,
        )
        if memory is None:
            raise NotFoundException(message="用户记忆不存在")

        embedding_text = self.build_embedding_text(memory)
        content_hash = self.embedding_service.build_content_hash(embedding_text)

        embedding_result = self.embedding_service.embed_text(
            embedding_text,
            provider=provider,
            model_name=model_name,
            dimension=dimension,
        )

        existing_embedding = await self.embedding_repository.get_embedding_by_memory(
            user_id=user_id,
            memory_id=memory_id,
            embedding_provider=embedding_result.provider,
            embedding_model=embedding_result.model_name,
            content_hash=content_hash,
        )

        if existing_embedding is not None:
            if not force_rebuild and existing_embedding.status == "active":
                return self._build_embedding_response(existing_embedding)

            updated_embedding = await self.embedding_repository.update_embedding(
                existing_embedding,
                UserMemoryEmbeddingUpdate(
                    status="active",
                    embedding_provider=embedding_result.provider,
                    embedding_model=embedding_result.model_name,
                    embedding_dimension=embedding_result.dimension,
                    embedding_vector=embedding_result.vector,
                    embedding_text=embedding_text,
                    content_hash=content_hash,
                    build_source=build_source,
                    source_metadata=self._build_source_metadata(memory),
                    last_embedded_at=self._now(),
                    error_message=None,
                ),
            )
            return self._build_embedding_response(updated_embedding)

        await self.embedding_repository.mark_stale_by_memory(
            user_id=user_id,
            memory_id=memory_id,
        )

        created_embedding = await self.embedding_repository.create_embedding(
            UserMemoryEmbeddingCreate(
                user_id=user_id,
                memory_id=memory_id,
                status="active",
                embedding_provider=embedding_result.provider,
                embedding_model=embedding_result.model_name,
                embedding_dimension=embedding_result.dimension,
                embedding_vector=embedding_result.vector,
                embedding_text=embedding_text,
                content_hash=content_hash,
                build_source=build_source,
                memory_type=memory.memory_type,
                source_type=memory.source_type,
                source_ref=memory.source_ref,
                source_metadata=self._build_source_metadata(memory),
                last_embedded_at=self._now(),
                error_message=None,
            )
        )
        return self._build_embedding_response(created_embedding)

    async def build_embeddings_for_user(
        self,
        *,
        user_id: int,
        provider: UserMemoryEmbeddingProvider = "mock",
        model_name: str | None = None,
        dimension: int = EmbeddingService.DEFAULT_DIMENSION,
        build_source: UserMemoryEmbeddingBuildSource = "manual_rebuild",
        force_rebuild: bool = False,
        limit: int = DEFAULT_BUILD_LIMIT,
    ) -> list[UserMemoryEmbeddingResponse]:
        memories = await self.memory_repository.list_active_memories_for_profile(
            user_id=user_id,
            include_expired=False,
            limit=limit,
        )

        results: list[UserMemoryEmbeddingResponse] = []
        for memory in memories:
            embedding = await self.build_embedding_for_memory(
                user_id=user_id,
                memory_id=memory.id,
                provider=provider,
                model_name=model_name,
                dimension=dimension,
                build_source=build_source,
                force_rebuild=force_rebuild,
            )
            results.append(embedding)

        return results

    async def mark_memory_embedding_stale(
        self,
        *,
        user_id: int,
        memory_id: int,
    ) -> int:
        return await self.embedding_repository.mark_stale_by_memory(
            user_id=user_id,
            memory_id=memory_id,
        )

    async def mark_memory_embedding_inactive(
        self,
        *,
        user_id: int,
        memory_id: int,
    ) -> int:
        return await self.embedding_repository.mark_inactive_by_memory(
            user_id=user_id,
            memory_id=memory_id,
        )

    def build_embedding_text(
        self,
        memory: UserMemory,
    ) -> str:
        parts: list[str] = [
            f"记忆类型：{memory.memory_type}",
            f"标题：{memory.title}",
        ]

        if memory.summary:
            parts.append(f"摘要：{memory.summary}")

        if memory.content:
            parts.append(f"内容：{memory.content}")

        if memory.keywords:
            parts.append(f"关键词：{'、'.join(memory.keywords)}")

        if memory.confidence:
            parts.append(f"置信度：{memory.confidence}")

        if memory.source_type:
            parts.append(f"来源类型：{memory.source_type}")

        embedding_text = "\n".join(parts).strip()
        return embedding_text[: self.MAX_EMBEDDING_TEXT_LENGTH]

    def _build_source_metadata(
        self,
        memory: UserMemory,
    ) -> dict[str, Any]:
        return {
            "memory_id": memory.id,
            "memory_type": memory.memory_type,
            "confidence": memory.confidence,
            "weight": memory.weight,
            "source_type": memory.source_type,
            "source_id": memory.source_id,
            "source_ref": memory.source_ref,
            "source_metadata": memory.source_metadata or {},
            "embedding_text_version": "stage_7_6a_step_7_v1",
        }

    def _build_embedding_response(
        self,
        embedding,
    ) -> UserMemoryEmbeddingResponse:
        return UserMemoryEmbeddingResponse.model_validate(embedding)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)