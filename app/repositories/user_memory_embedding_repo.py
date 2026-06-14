"""用户记忆向量 Repository。

本文件封装 user_memory_embeddings 表的数据访问。向量用于记忆检索，但仍然必须按 user_id 隔离，
避免把一个用户的长期偏好或历史对话暴露给另一个用户。
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_memory_embedding import UserMemoryEmbedding
from app.schemas.user_memory_embedding import (
    UserMemoryEmbeddingCreate,
    UserMemoryEmbeddingListQuery,
    UserMemoryEmbeddingUpdate,
)


class AsyncUserMemoryEmbeddingRepository:
    """异步用户记忆向量数据访问对象。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_embedding(
        self,
        payload: UserMemoryEmbeddingCreate,
    ) -> UserMemoryEmbedding:
        embedding = UserMemoryEmbedding(**payload.model_dump())
        self.db.add(embedding)
        await self.db.commit()
        await self.db.refresh(embedding)
        return embedding

    async def get_embedding(
        self,
        *,
        embedding_id: int,
        user_id: int,
    ) -> UserMemoryEmbedding | None:
        stmt = select(UserMemoryEmbedding).where(
            UserMemoryEmbedding.id == embedding_id,
            UserMemoryEmbedding.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_embedding_by_memory(
        self,
        *,
        memory_id: int,
        user_id: int,
        embedding_provider: str | None = None,
        embedding_model: str | None = None,
        content_hash: str | None = None,
    ) -> UserMemoryEmbedding | None:
        stmt = select(UserMemoryEmbedding).where(
            UserMemoryEmbedding.memory_id == memory_id,
            UserMemoryEmbedding.user_id == user_id,
        )

        if embedding_provider is not None:
            stmt = stmt.where(
                UserMemoryEmbedding.embedding_provider == embedding_provider
            )

        if embedding_model is not None:
            stmt = stmt.where(UserMemoryEmbedding.embedding_model == embedding_model)

        if content_hash is not None:
            stmt = stmt.where(UserMemoryEmbedding.content_hash == content_hash)

        stmt = stmt.order_by(UserMemoryEmbedding.created_at.desc()).limit(1)

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_embeddings(
        self,
        *,
        user_id: int,
        query: UserMemoryEmbeddingListQuery,
    ) -> list[UserMemoryEmbedding]:
        stmt = self._apply_filters(
            select(UserMemoryEmbedding),
            user_id=user_id,
            query=query,
        )

        stmt = (
            stmt.order_by(UserMemoryEmbedding.created_at.desc())
            .offset(query.offset)
            .limit(query.limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_embeddings(
        self,
        *,
        user_id: int,
        query: UserMemoryEmbeddingListQuery,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count(UserMemoryEmbedding.id)),
            user_id=user_id,
            query=query,
        )

        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def list_active_embeddings_for_retrieval(
        self,
        *,
        user_id: int,
        memory_types: list[str] | None = None,
        include_inactive: bool = False,
        limit: int = 500,
    ) -> list[UserMemoryEmbedding]:
        """查询可用于相似度检索的记忆向量。

        检索候选只来自当前 user_id，保证用户记忆不会跨账号混用。
        """

        stmt = select(UserMemoryEmbedding).where(
            UserMemoryEmbedding.user_id == user_id,
        )

        if not include_inactive:
            stmt = stmt.where(UserMemoryEmbedding.status == "active")

        if memory_types:
            stmt = stmt.where(UserMemoryEmbedding.memory_type.in_(memory_types))

        stmt = stmt.order_by(UserMemoryEmbedding.updated_at.desc()).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_embeddings_by_memory_ids(
        self,
        *,
        user_id: int,
        memory_ids: list[int],
    ) -> list[UserMemoryEmbedding]:
        if not memory_ids:
            return []

        stmt = select(UserMemoryEmbedding).where(
            UserMemoryEmbedding.user_id == user_id,
            UserMemoryEmbedding.memory_id.in_(memory_ids),
        )

        stmt = stmt.order_by(UserMemoryEmbedding.created_at.desc())

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_embedding(
        self,
        embedding: UserMemoryEmbedding,
        payload: UserMemoryEmbeddingUpdate,
    ) -> UserMemoryEmbedding:
        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(embedding, field, value)

        self.db.add(embedding)
        await self.db.commit()
        await self.db.refresh(embedding)
        return embedding

    async def mark_stale_by_memory(
        self,
        *,
        user_id: int,
        memory_id: int,
    ) -> int:
        """当记忆内容变化时，将对应向量标记为 stale。"""

        embeddings = await self.list_embeddings_by_memory_ids(
            user_id=user_id,
            memory_ids=[memory_id],
        )

        updated_count = 0

        for embedding in embeddings:
            if embedding.status == "active":
                embedding.status = "stale"
                self.db.add(embedding)
                updated_count += 1

        if updated_count > 0:
            await self.db.commit()

        return updated_count

    async def mark_inactive_by_memory(
        self,
        *,
        user_id: int,
        memory_id: int,
    ) -> int:
        embeddings = await self.list_embeddings_by_memory_ids(
            user_id=user_id,
            memory_ids=[memory_id],
        )

        updated_count = 0

        for embedding in embeddings:
            if embedding.status != "inactive":
                embedding.status = "inactive"
                self.db.add(embedding)
                updated_count += 1

        if updated_count > 0:
            await self.db.commit()

        return updated_count

    async def mark_failed(
        self,
        *,
        embedding: UserMemoryEmbedding,
        error_message: str,
    ) -> UserMemoryEmbedding:
        embedding.status = "failed"
        embedding.error_message = error_message
        embedding.last_embedded_at = self._now()

        self.db.add(embedding)
        await self.db.commit()
        await self.db.refresh(embedding)
        return embedding

    async def count_by_status(
        self,
        *,
        user_id: int,
        status: str | None = None,
    ) -> int:
        stmt = select(func.count(UserMemoryEmbedding.id)).where(
            UserMemoryEmbedding.user_id == user_id,
        )

        if status is not None:
            stmt = stmt.where(UserMemoryEmbedding.status == status)

        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def get_last_embedded_at(
        self,
        *,
        user_id: int,
    ) -> datetime | None:
        stmt = select(func.max(UserMemoryEmbedding.last_embedded_at)).where(
            UserMemoryEmbedding.user_id == user_id,
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _apply_filters(
        self,
        stmt,
        *,
        user_id: int,
        query: UserMemoryEmbeddingListQuery,
    ):
        """为向量列表和计数复用筛选条件。"""

        stmt = stmt.where(UserMemoryEmbedding.user_id == user_id)

        if not query.include_inactive:
            stmt = stmt.where(UserMemoryEmbedding.status != "inactive")
        elif query.status is not None:
            stmt = stmt.where(UserMemoryEmbedding.status == query.status)

        if query.status is not None and not query.include_inactive:
            stmt = stmt.where(UserMemoryEmbedding.status == query.status)

        if query.memory_type is not None:
            stmt = stmt.where(UserMemoryEmbedding.memory_type == query.memory_type)

        if query.source_type is not None:
            stmt = stmt.where(UserMemoryEmbedding.source_type == query.source_type)

        if query.embedding_provider is not None:
            stmt = stmt.where(
                UserMemoryEmbedding.embedding_provider == query.embedding_provider
            )

        return stmt

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)
