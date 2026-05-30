from __future__ import annotations

import logging
import math
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_memory import UserMemory
from app.models.user_memory_embedding import UserMemoryEmbedding
from app.repositories.user_memory_embedding_repo import (
    AsyncUserMemoryEmbeddingRepository,
)
from app.repositories.user_memory_repo import AsyncUserMemoryRepository
from app.schemas.user_memory_embedding import (
    UserMemoryEmbeddingProvider,
    UserMemoryRetrievalInputSnapshot,
    UserMemoryRetrievalItem,
    UserMemoryRetrievalRequest,
    UserMemoryRetrievalResponse,
)
from app.services.embedding_service import EmbeddingResult, EmbeddingService


logger = logging.getLogger(__name__)


class UserMemoryRetrievalService:
    """Retrieve semantically similar user memories.

    The first version uses JSON-stored vectors and Python cosine similarity.
    It does not call DeepSeek and does not write database records.
    """

    DEFAULT_CANDIDATE_LIMIT = 500
    DEFAULT_CONTENT_EXCERPT_LENGTH = 300

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

    async def search_similar_memories(
        self,
        *,
        user_id: int,
        request: UserMemoryRetrievalRequest,
        provider: UserMemoryEmbeddingProvider = "mock",
        model_name: str | None = None,
        dimension: int = EmbeddingService.DEFAULT_DIMENSION,
    ) -> UserMemoryRetrievalResponse:
        try:
            query_embedding = self.embedding_service.embed_text(
                request.query,
                provider=provider,
                model_name=model_name,
                dimension=dimension,
            )
        except Exception:
            logger.exception(
                "build query embedding failed",
                extra={"user_id": user_id},
            )
            return self._build_unavailable_response(
                request=request,
                unavailable_reason="embedding_unavailable",
                summary="相似记忆检索暂时不可用：无法生成查询向量。",
                warnings=["生成查询向量失败，已返回空检索结果。"],
            )

        candidate_embeddings = (
            await self.embedding_repository.list_active_embeddings_for_retrieval(
                user_id=user_id,
                memory_types=list(request.memory_types),
                include_inactive=request.include_inactive,
                limit=self.DEFAULT_CANDIDATE_LIMIT,
            )
        )

        if not candidate_embeddings:
            return self._build_unavailable_response(
                request=request,
                unavailable_reason="no_embeddings",
                summary="当前用户暂无可用于语义检索的记忆向量。",
                warnings=["当前没有可检索的用户记忆向量，可先创建记忆或执行 embedding 重建。"],
                query_embedding=query_embedding,
            )

        scored_embeddings = self._score_embeddings(
            query_vector=query_embedding.vector,
            embeddings=candidate_embeddings,
        )

        filtered_embeddings = self._filter_scored_embeddings(
            scored_embeddings=scored_embeddings,
            min_similarity_score=request.min_similarity_score,
        )

        top_embeddings = filtered_embeddings[: request.top_k]

        items = await self._build_retrieval_items(
            user_id=user_id,
            scored_embeddings=top_embeddings,
            include_content=request.include_content,
        )

        return UserMemoryRetrievalResponse(
            status="available",
            unavailable_reason=None,
            summary=self._build_available_summary(
                matched_count=len(items),
                candidate_count=len(candidate_embeddings),
            ),
            items=items,
            input_snapshot=self._build_input_snapshot(
                request=request,
                query_embedding=query_embedding,
            ),
            warnings=self._build_warnings(
                candidate_count=len(candidate_embeddings),
                matched_count=len(items),
                min_similarity_score=request.min_similarity_score,
            ),
        )

    def _score_embeddings(
        self,
        *,
        query_vector: list[float],
        embeddings: list[UserMemoryEmbedding],
    ) -> list[tuple[UserMemoryEmbedding, float]]:
        scored: list[tuple[UserMemoryEmbedding, float]] = []

        for embedding in embeddings:
            similarity_score = self._calculate_cosine_similarity(
                query_vector=query_vector,
                memory_vector=self._normalize_vector_value(
                    embedding.embedding_vector
                ),
            )
            scored.append((embedding, similarity_score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored

    def _filter_scored_embeddings(
        self,
        *,
        scored_embeddings: list[tuple[UserMemoryEmbedding, float]],
        min_similarity_score: float | None,
    ) -> list[tuple[UserMemoryEmbedding, float]]:
        if min_similarity_score is None:
            return scored_embeddings

        return [
            (embedding, score)
            for embedding, score in scored_embeddings
            if score >= min_similarity_score
        ]

    async def _build_retrieval_items(
        self,
        *,
        user_id: int,
        scored_embeddings: list[tuple[UserMemoryEmbedding, float]],
        include_content: bool,
    ) -> list[UserMemoryRetrievalItem]:
        items: list[UserMemoryRetrievalItem] = []

        for embedding, similarity_score in scored_embeddings:
            memory = await self.memory_repository.get_memory(
                user_id=user_id,
                memory_id=embedding.memory_id,
            )
            if memory is None:
                continue

            if memory.status != "active":
                continue

            items.append(
                self._build_retrieval_item(
                    memory=memory,
                    embedding=embedding,
                    similarity_score=similarity_score,
                    include_content=include_content,
                )
            )

        return items

    def _build_retrieval_item(
        self,
        *,
        memory: UserMemory,
        embedding: UserMemoryEmbedding,
        similarity_score: float,
        include_content: bool,
    ) -> UserMemoryRetrievalItem:
        return UserMemoryRetrievalItem(
            memory_id=memory.id,
            memory_type=memory.memory_type,
            confidence=memory.confidence,
            title=memory.title,
            summary=memory.summary,
            content_excerpt=self._build_content_excerpt(
                memory.content,
                include_content=include_content,
            ),
            keywords=list(memory.keywords or []),
            source_type=memory.source_type,
            source_ref=memory.source_ref,
            similarity_score=self._round_similarity_score(similarity_score),
            embedding_id=embedding.id,
            embedding_model=embedding.embedding_model,
            occurred_at=memory.occurred_at,
            expires_at=memory.expires_at,
        )

    def _calculate_cosine_similarity(
        self,
        *,
        query_vector: list[float],
        memory_vector: list[float],
    ) -> float:
        if not query_vector or not memory_vector:
            return 0.0

        length = min(len(query_vector), len(memory_vector))
        if length == 0:
            return 0.0

        query_values = query_vector[:length]
        memory_values = memory_vector[:length]

        dot_product = sum(
            query_value * memory_value
            for query_value, memory_value in zip(query_values, memory_values)
        )
        query_norm = math.sqrt(sum(value * value for value in query_values))
        memory_norm = math.sqrt(sum(value * value for value in memory_values))

        if query_norm == 0 or memory_norm == 0:
            return 0.0

        cosine = dot_product / (query_norm * memory_norm)

        # Convert cosine from [-1, 1] into API-friendly [0, 1].
        return max(0.0, min(1.0, (cosine + 1.0) / 2.0))

    def _normalize_vector_value(
        self,
        value: Any,
    ) -> list[float]:
        if not isinstance(value, list):
            return []

        normalized: list[float] = []
        for item in value:
            try:
                normalized.append(float(item))
            except (TypeError, ValueError):
                continue

        return normalized

    def _build_input_snapshot(
        self,
        *,
        request: UserMemoryRetrievalRequest,
        query_embedding: EmbeddingResult | None = None,
    ) -> UserMemoryRetrievalInputSnapshot:
        return UserMemoryRetrievalInputSnapshot(
            query=request.query,
            top_k=request.top_k,
            min_similarity_score=request.min_similarity_score,
            memory_types=list(request.memory_types),
            include_inactive=request.include_inactive,
            include_content=request.include_content,
            embedding_provider=query_embedding.provider if query_embedding else None,
            embedding_model=query_embedding.model_name if query_embedding else None,
        )

    def _build_unavailable_response(
        self,
        *,
        request: UserMemoryRetrievalRequest,
        unavailable_reason: str,
        summary: str,
        warnings: list[str] | None = None,
        query_embedding: EmbeddingResult | None = None,
    ) -> UserMemoryRetrievalResponse:
        return UserMemoryRetrievalResponse(
            status="unavailable",
            unavailable_reason=unavailable_reason,
            summary=summary,
            items=[],
            input_snapshot=self._build_input_snapshot(
                request=request,
                query_embedding=query_embedding,
            ),
            warnings=warnings or [],
        )

    def _build_available_summary(
        self,
        *,
        matched_count: int,
        candidate_count: int,
    ) -> str:
        if matched_count == 0:
            return f"已检索 {candidate_count} 条候选记忆，但没有命中满足条件的相似记忆。"

        return f"已从 {candidate_count} 条候选记忆向量中检索出 {matched_count} 条相关记忆。"

    def _build_warnings(
        self,
        *,
        candidate_count: int,
        matched_count: int,
        min_similarity_score: float | None,
    ) -> list[str]:
        warnings = [
            "相似记忆检索只用于补充用户历史上下文，不构成投资建议。",
            "第一版使用本地 mock/local embedding，语义效果以链路验证为主。",
        ]

        if candidate_count >= self.DEFAULT_CANDIDATE_LIMIT:
            warnings.append("候选向量数量达到本次检索上限，结果可能不是全量记忆中的最优结果。")

        if min_similarity_score is not None and matched_count == 0:
            warnings.append("当前相似度阈值下没有命中结果，可适当降低 min_similarity_score。")

        return warnings

    def _build_content_excerpt(
        self,
        content: str,
        *,
        include_content: bool,
    ) -> str | None:
        if not include_content:
            return None

        normalized_content = str(content or "").strip()
        if not normalized_content:
            return None

        return normalized_content[: self.DEFAULT_CONTENT_EXCERPT_LENGTH]

    def _round_similarity_score(
        self,
        value: float,
    ) -> float:
        return round(max(0.0, min(1.0, value)), 6)