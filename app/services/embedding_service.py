from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from app.core.exceptions import BadRequestException
from app.schemas.user_memory_embedding import UserMemoryEmbeddingProvider


@dataclass(frozen=True)
class EmbeddingResult:
    provider: UserMemoryEmbeddingProvider
    model_name: str
    dimension: int
    vector: list[float]


class EmbeddingService:
    """Build text embeddings.

    The first version uses deterministic local vectors so the memory retrieval
    pipeline can be developed and tested without an external embedding API.
    """

    DEFAULT_PROVIDER: UserMemoryEmbeddingProvider = "mock"
    DEFAULT_MODEL_NAME = "mock-hash-embedding-v1"
    DEFAULT_DIMENSION = 128
    MAX_TEXT_LENGTH = 2000

    SUPPORTED_LOCAL_PROVIDERS: set[str] = {
        "mock",
        "local",
    }

    def embed_text(
        self,
        text: str,
        *,
        provider: UserMemoryEmbeddingProvider = DEFAULT_PROVIDER,
        model_name: str | None = None,
        dimension: int = DEFAULT_DIMENSION,
    ) -> EmbeddingResult:
        normalized_text = self._normalize_text(text)

        if provider not in self.SUPPORTED_LOCAL_PROVIDERS:
            raise BadRequestException(
                message=f"embedding provider '{provider}' is not implemented"
            )

        normalized_dimension = self._normalize_dimension(dimension)
        resolved_model_name = model_name or self._default_model_name(provider)

        vector = self._build_deterministic_vector(
            text=normalized_text,
            dimension=normalized_dimension,
        )

        return EmbeddingResult(
            provider=provider,
            model_name=resolved_model_name,
            dimension=normalized_dimension,
            vector=vector,
        )

    def embed_texts(
        self,
        texts: list[str],
        *,
        provider: UserMemoryEmbeddingProvider = DEFAULT_PROVIDER,
        model_name: str | None = None,
        dimension: int = DEFAULT_DIMENSION,
    ) -> list[EmbeddingResult]:
        return [
            self.embed_text(
                text,
                provider=provider,
                model_name=model_name,
                dimension=dimension,
            )
            for text in texts
        ]

    def build_content_hash(self, text: str) -> str:
        normalized_text = self._normalize_text(text)
        return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()

    def _build_deterministic_vector(
        self,
        *,
        text: str,
        dimension: int,
    ) -> list[float]:
        raw_values: list[float] = []

        for index in range(dimension):
            digest = hashlib.sha256(f"{text}:{index}".encode("utf-8")).digest()
            integer_value = int.from_bytes(digest[:8], byteorder="big", signed=False)

            # Convert the integer into a stable value in [-1, 1].
            normalized_value = (integer_value / ((1 << 64) - 1)) * 2 - 1
            raw_values.append(normalized_value)

        return self._normalize_vector(raw_values)

    def _normalize_vector(self, vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector

        return [value / norm for value in vector]

    def _normalize_text(self, text: str) -> str:
        normalized_text = str(text or "").strip()
        if not normalized_text:
            raise BadRequestException(message="embedding text cannot be empty")

        return normalized_text[: self.MAX_TEXT_LENGTH]

    def _normalize_dimension(self, dimension: int) -> int:
        try:
            normalized_dimension = int(dimension)
        except (TypeError, ValueError):
            raise BadRequestException(message="embedding dimension must be an integer")

        if normalized_dimension <= 0 or normalized_dimension > 8192:
            raise BadRequestException(
                message="embedding dimension must be between 1 and 8192"
            )

        return normalized_dimension

    def _default_model_name(
        self,
        provider: UserMemoryEmbeddingProvider,
    ) -> str:
        if provider == "local":
            return "local-hash-embedding-v1"

        return self.DEFAULT_MODEL_NAME