from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_record import AnalysisRecord
from app.models.user_memory import UserMemory
from app.models.watchlist_item import WatchlistItem
from app.repositories.analysis_record_repo import AsyncAnalysisRecordRepository
from app.repositories.user_memory_repo import AsyncUserMemoryRepository
from app.repositories.user_preference_repo import AsyncUserPreferenceRepository
from app.repositories.watchlist_repo import AsyncWatchlistRepository
from app.schemas.user_memory import (
    UserMemoryListQuery,
    UserProfileRefreshRequest,
    UserProfileRefreshResponse,
    UserProfileResponse,
    UserProfileSummary,
    UserProfileUpdate,
)


class UserProfileService:
    MAX_PROFILE_MEMORIES = 200
    MAX_PROFILE_ANALYSIS_RECORDS = 100
    MAX_LIST_ITEMS = 20

    def __init__(
        self,
        db: AsyncSession,
        *,
        memory_repo: AsyncUserMemoryRepository | None = None,
        preference_repo: AsyncUserPreferenceRepository | None = None,
        watchlist_repo: AsyncWatchlistRepository | None = None,
        analysis_record_repo: AsyncAnalysisRecordRepository | None = None,
    ) -> None:
        self.db = db
        self.memory_repo = memory_repo or AsyncUserMemoryRepository(db)
        self.preference_repo = preference_repo or AsyncUserPreferenceRepository(db)
        self.watchlist_repo = watchlist_repo or AsyncWatchlistRepository(db)
        self.analysis_record_repo = analysis_record_repo or AsyncAnalysisRecordRepository(db)

    async def refresh_profile(
        self,
        *,
        user_id: int,
        request: UserProfileRefreshRequest,
    ) -> UserProfileRefreshResponse:
        memories = await self._list_memories_for_refresh(
            user_id=user_id,
            include_inactive=request.include_inactive_memories,
        )
        preference = await self.preference_repo.get_by_user_id(user_id)
        watchlist_items = await self.watchlist_repo.list_by_user_id(user_id)
        analysis_records = await self.analysis_record_repo.list_by_user_id(user_id)

        summary = self._build_profile_summary(
            memories=memories,
            preference_risk=getattr(preference, "risk_preference", None),
            watchlist_items=watchlist_items,
            analysis_records=analysis_records,
        )

        profile = await self.memory_repo.get_or_create_profile(user_id=user_id)
        next_version = profile.profile_version + 1

        updated_profile = await self.memory_repo.update_profile(
            profile,
            UserProfileUpdate(
                status="active",
                profile_version=next_version,
                summary=summary,
                generated_from_memory_count=len(memories),
                generated_from_message_count=0,
                generated_from_analysis_count=min(
                    len(analysis_records),
                    self.MAX_PROFILE_ANALYSIS_RECORDS,
                ),
                refreshed_at=self._now(),
            ),
        )

        return UserProfileRefreshResponse(
            status=updated_profile.status,
            profile=UserProfileResponse.model_validate(updated_profile),
            refreshed=True,
            memory_count=len(memories),
            message="用户画像已刷新",
        )

    async def get_or_create_profile(
        self,
        *,
        user_id: int,
    ) -> UserProfileResponse:
        profile = await self.memory_repo.get_or_create_profile(user_id=user_id)
        return UserProfileResponse.model_validate(profile)

    async def _list_memories_for_refresh(
        self,
        *,
        user_id: int,
        include_inactive: bool,
    ) -> list[UserMemory]:
        if include_inactive:
            return await self.memory_repo.list_memories(
                user_id=user_id,
                query=UserMemoryListQuery(
                    include_inactive=True,
                    limit=self.MAX_PROFILE_MEMORIES,
                    offset=0,
                ),
            )

        return await self.memory_repo.list_active_memories_for_profile(
            user_id=user_id,
            include_expired=False,
            limit=self.MAX_PROFILE_MEMORIES,
        )

    def _build_profile_summary(
        self,
        *,
        memories: list[UserMemory],
        preference_risk: str | None,
        watchlist_items: list[WatchlistItem],
        analysis_records: list[AnalysisRecord],
    ) -> UserProfileSummary:
        risk_preference = self._resolve_risk_preference(
            memories=memories,
            preference_risk=preference_risk,
        )
        preferred_markets = self._build_preferred_markets(
            memories=memories,
            watchlist_items=watchlist_items,
            analysis_records=analysis_records,
        )
        frequent_symbols = self._build_frequent_symbols(
            memories=memories,
            watchlist_items=watchlist_items,
            analysis_records=analysis_records,
        )
        interest_tags = self._build_interest_tags(memories)
        research_preferences = self._build_memory_texts(
            memories=memories,
            memory_type="research_preference",
        )
        risk_focuses = self._build_memory_texts(
            memories=memories,
            memory_type="risk_focus",
        )
        communication_preferences = self._build_memory_texts(
            memories=memories,
            memory_type="communication_preference",
        )

        evidence_count = (
            len(memories)
            + len(watchlist_items)
            + min(len(analysis_records), self.MAX_PROFILE_ANALYSIS_RECORDS)
        )

        return UserProfileSummary(
            risk_preference=risk_preference,
            preferred_markets=preferred_markets,
            frequent_symbols=frequent_symbols,
            interest_tags=interest_tags,
            research_preferences=research_preferences,
            risk_focuses=risk_focuses,
            communication_preferences=communication_preferences,
            summary=self._build_summary_text(
                risk_preference=risk_preference,
                preferred_markets=preferred_markets,
                frequent_symbols=frequent_symbols,
                interest_tags=interest_tags,
                risk_focuses=risk_focuses,
            ),
            evidence_count=evidence_count,
            profile_metadata={
                "memory_count": len(memories),
                "watchlist_count": len(watchlist_items),
                "analysis_record_count": min(
                    len(analysis_records),
                    self.MAX_PROFILE_ANALYSIS_RECORDS,
                ),
                "aggregation_version": "stage_7_6_v1",
                "generated_by": "UserProfileService",
            },
        )

    def _resolve_risk_preference(
        self,
        *,
        memories: list[UserMemory],
        preference_risk: str | None,
    ) -> str | None:
        explicit_memory = self._find_highest_weight_memory(
            memories=memories,
            memory_type="risk_preference",
        )
        if explicit_memory is not None:
            value = self._normalize_risk_preference(explicit_memory.content)
            if value is not None:
                return value

        return self._normalize_risk_preference(preference_risk)

    def _build_preferred_markets(
        self,
        *,
        memories: list[UserMemory],
        watchlist_items: list[WatchlistItem],
        analysis_records: list[AnalysisRecord],
    ) -> list[str]:
        counter: Counter[str] = Counter()

        for item in watchlist_items:
            if item.market:
                counter[item.market.upper()] += 3

        for record in analysis_records[: self.MAX_PROFILE_ANALYSIS_RECORDS]:
            if record.market:
                counter[record.market.upper()] += 1

        for memory in memories:
            if memory.memory_type == "market_interest":
                for keyword in memory.keywords or []:
                    normalized = keyword.upper()
                    if normalized in {"US", "CN", "HK"}:
                        counter[normalized] += memory.weight

        return self._top_counter_keys(counter)

    def _build_frequent_symbols(
        self,
        *,
        memories: list[UserMemory],
        watchlist_items: list[WatchlistItem],
        analysis_records: list[AnalysisRecord],
    ) -> list[str]:
        counter: Counter[str] = Counter()

        for item in watchlist_items:
            if item.symbol:
                counter[item.symbol.upper()] += 3

        for record in analysis_records[: self.MAX_PROFILE_ANALYSIS_RECORDS]:
            if record.symbol:
                counter[record.symbol.upper()] += 1

        for memory in memories:
            if memory.memory_type == "symbol_interest":
                for keyword in memory.keywords or []:
                    normalized = keyword.upper()
                    if normalized:
                        counter[normalized] += memory.weight

        return self._top_counter_keys(counter)

    def _build_interest_tags(
        self,
        memories: list[UserMemory],
    ) -> list[str]:
        counter: Counter[str] = Counter()

        for memory in memories:
            if memory.memory_type:
                counter[memory.memory_type] += 1

            for keyword in memory.keywords or []:
                normalized = keyword.strip()
                if normalized:
                    counter[normalized] += memory.weight

        return self._top_counter_keys(counter)

    def _build_memory_texts(
        self,
        *,
        memories: list[UserMemory],
        memory_type: str,
    ) -> list[str]:
        texts: list[str] = []
        seen: set[str] = set()

        matching_memories = [
            memory for memory in memories if memory.memory_type == memory_type
        ]
        matching_memories.sort(
            key=lambda memory: (memory.weight, memory.created_at),
            reverse=True,
        )

        for memory in matching_memories:
            text = (memory.summary or memory.content or memory.title).strip()
            if not text:
                continue

            normalized = text.lower()
            if normalized in seen:
                continue

            seen.add(normalized)
            texts.append(text[:120])

            if len(texts) >= self.MAX_LIST_ITEMS:
                break

        return texts

    def _find_highest_weight_memory(
        self,
        *,
        memories: list[UserMemory],
        memory_type: str,
    ) -> UserMemory | None:
        matching_memories = [
            memory for memory in memories if memory.memory_type == memory_type
        ]
        if not matching_memories:
            return None

        return max(
            matching_memories,
            key=lambda memory: (memory.weight, memory.created_at),
        )

    def _normalize_risk_preference(
        self,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip().lower()
        if normalized in {"conservative", "balanced", "aggressive"}:
            return normalized

        if "保守" in normalized:
            return "conservative"

        if "激进" in normalized or "进取" in normalized:
            return "aggressive"

        if "均衡" in normalized or "平衡" in normalized:
            return "balanced"

        return None

    def _top_counter_keys(
        self,
        counter: Counter[str],
    ) -> list[str]:
        return [
            item
            for item, _count in counter.most_common(self.MAX_LIST_ITEMS)
            if item
        ]

    def _build_summary_text(
        self,
        *,
        risk_preference: str | None,
        preferred_markets: list[str],
        frequent_symbols: list[str],
        interest_tags: list[str],
        risk_focuses: list[str],
    ) -> str:
        parts: list[str] = []

        if risk_preference:
            parts.append(f"用户当前风险偏好为 {risk_preference}")

        if preferred_markets:
            parts.append(f"常关注市场包括 {', '.join(preferred_markets[:5])}")

        if frequent_symbols:
            parts.append(f"常关注股票包括 {', '.join(frequent_symbols[:5])}")

        if interest_tags:
            parts.append(f"主要研究兴趣包括 {', '.join(interest_tags[:5])}")

        if risk_focuses:
            parts.append(f"较关注的风险点包括 {', '.join(risk_focuses[:3])}")

        if not parts:
            return "当前用户画像证据较少，后续会随着偏好、自选股、分析记录和长期记忆逐步完善。"

        return "；".join(parts) + "。"

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)