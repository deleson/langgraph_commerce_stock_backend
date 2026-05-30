from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user_memory import (
    UserMemoryCreate,
    UserMemoryListQuery,
    UserMemoryResponse,
    UserMemoryUpdate,
)
from app.services.user_memory_service import UserMemoryService


@dataclass(slots=True)
class ConversationMemoryCandidate:
    memory_type: str
    title: str
    content: str
    summary: str | None
    keywords: list[str]
    confidence: str
    weight: int


class UserMemoryExtractionService:
    MAX_CONTENT_LENGTH = 1000
    MAX_SUMMARY_LENGTH = 500
    MAX_TITLE_LENGTH = 120
    MAX_KEYWORDS = 20

    RISK_FOCUS_RULES = {
        "最大回撤": ("最大回撤", "回撤"),
        "止损": ("止损",),
        "止盈": ("止盈",),
        "波动率": ("波动率", "波动"),
        "手续费": ("手续费", "交易成本"),
        "滑点": ("滑点",),
        "数据质量": ("数据质量", "数据可靠", "数据是否可靠"),
    }

    RESEARCH_PREFERENCE_RULES = {
        "回测": ("回测", "历史验证"),
        "胜率": ("胜率",),
        "夏普比率": ("夏普", "sharpe"),
        "收益回撤比": ("收益回撤比",),
        "策略信号": ("策略信号",),
        "技术指标": ("技术指标", "RSI", "MACD", "均线"),
        "候选评分": ("候选评分", "候选股", "股票候选"),
        "组合回测": ("组合回测", "组合"),
    }

    COMMUNICATION_PREFERENCE_RULES = {
        "表格": ("表格",),
        "流程图": ("流程图", "mermaid", "图示"),
        "详细步骤": ("详细", "一步步", "按步骤", "不要省略"),
        "代码位置": ("代码位置", "文件位置", "添加在哪", "修改在哪"),
        "新手解释": ("新手", "看不懂", "解释一下", "为什么"),
    }

    ANALYSIS_CONTEXT_RULES = {
        "数据质量": ("数据质量",),
        "真实行情": ("真实行情", "baostock", "tushare"),
        "自选股": ("自选股",),
        "用户偏好": ("用户偏好", "风险偏好"),
        "回测结果": ("回测结果", "绩效指标"),
    }

    MARKET_RULES = {
        "US": ("美股", "US", "AAPL", "MSFT", "TSLA"),
        "CN": ("A股", "A 股", "CN", "沪深"),
        "HK": ("港股", "HK"),
    }

    def __init__(
        self,
        db: AsyncSession,
        *,
        memory_service: UserMemoryService | None = None,
    ) -> None:
        self.db = db
        self.memory_service = memory_service or UserMemoryService(db)

    async def extract_from_conversation_message(
        self,
        *,
        user_id: int,
        message_id: int,
        analysis_thread_id: str,
        content: str | None,
        message_type: str,
        source: str,
        analysis_record_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> list[UserMemoryResponse]:
        normalized_content = self._normalize_text(content)
        if not normalized_content:
            return []

        candidates = self._build_candidates(normalized_content)
        if not candidates:
            return []

        memories: list[UserMemoryResponse] = []
        for candidate in candidates:
            memory = await self._create_or_update_memory(
                user_id=user_id,
                message_id=message_id,
                analysis_thread_id=analysis_thread_id,
                message_type=message_type,
                source=source,
                analysis_record_id=analysis_record_id,
                payload=payload,
                candidate=candidate,
            )
            memories.append(memory)

        return memories

    def _build_candidates(
        self,
        content: str,
    ) -> list[ConversationMemoryCandidate]:
        candidates: list[ConversationMemoryCandidate] = []

        risk_preference = self._extract_risk_preference(content)
        if risk_preference is not None:
            candidates.append(
                ConversationMemoryCandidate(
                    memory_type="risk_preference",
                    title=f"用户风险偏好：{risk_preference}",
                    content=f"用户在追问中表达了 {risk_preference} 风险偏好。",
                    summary=f"风险偏好：{risk_preference}",
                    keywords=["风险偏好", risk_preference],
                    confidence="high",
                    weight=90,
                )
            )

        risk_focuses = self._match_rule_labels(content, self.RISK_FOCUS_RULES)
        if risk_focuses:
            joined = "、".join(risk_focuses)
            candidates.append(
                ConversationMemoryCandidate(
                    memory_type="risk_focus",
                    title=f"用户关注风险点：{joined}",
                    content=f"用户在追问中表达关注这些风险点：{joined}。",
                    summary=f"关注风险点：{joined}",
                    keywords=risk_focuses,
                    confidence="medium",
                    weight=60,
                )
            )

        research_preferences = self._match_rule_labels(
            content,
            self.RESEARCH_PREFERENCE_RULES,
        )
        if research_preferences:
            joined = "、".join(research_preferences)
            candidates.append(
                ConversationMemoryCandidate(
                    memory_type="research_preference",
                    title=f"用户研究偏好：{joined}",
                    content=f"用户在追问中表现出这些研究偏好：{joined}。",
                    summary=f"研究偏好：{joined}",
                    keywords=research_preferences,
                    confidence="medium",
                    weight=60,
                )
            )

        communication_preferences = self._match_rule_labels(
            content,
            self.COMMUNICATION_PREFERENCE_RULES,
        )
        if communication_preferences:
            joined = "、".join(communication_preferences)
            candidates.append(
                ConversationMemoryCandidate(
                    memory_type="communication_preference",
                    title=f"用户沟通偏好：{joined}",
                    content=f"用户在追问中表现出这些沟通偏好：{joined}。",
                    summary=f"沟通偏好：{joined}",
                    keywords=communication_preferences,
                    confidence="high",
                    weight=80,
                )
            )

        analysis_context_preferences = self._match_rule_labels(
            content,
            self.ANALYSIS_CONTEXT_RULES,
        )
        if analysis_context_preferences:
            joined = "、".join(analysis_context_preferences)
            candidates.append(
                ConversationMemoryCandidate(
                    memory_type="analysis_context_preference",
                    title=f"用户分析上下文偏好：{joined}",
                    content=f"用户在追问中表现出这些分析上下文偏好：{joined}。",
                    summary=f"分析上下文偏好：{joined}",
                    keywords=analysis_context_preferences,
                    confidence="medium",
                    weight=50,
                )
            )

        markets = self._match_rule_labels(content, self.MARKET_RULES)
        if markets:
            joined = "、".join(markets)
            candidates.append(
                ConversationMemoryCandidate(
                    memory_type="market_interest",
                    title=f"用户关注市场：{joined}",
                    content=f"用户在追问中表现出对这些市场的关注：{joined}。",
                    summary=f"关注市场：{joined}",
                    keywords=markets,
                    confidence="medium",
                    weight=45,
                )
            )

        return candidates

    async def _create_or_update_memory(
        self,
        *,
        user_id: int,
        message_id: int,
        analysis_thread_id: str,
        message_type: str,
        source: str,
        analysis_record_id: int | None,
        payload: dict[str, Any] | None,
        candidate: ConversationMemoryCandidate,
    ) -> UserMemoryResponse:
        existing = await self._find_similar_memory(
            user_id=user_id,
            candidate=candidate,
        )

        if existing is not None:
            return await self.memory_service.update_memory(
                user_id=user_id,
                memory_id=existing.id,
                request=UserMemoryUpdate(
                    confidence=self._max_confidence(
                        existing.confidence,
                        candidate.confidence,
                    ),
                    content=self._truncate(candidate.content, self.MAX_CONTENT_LENGTH),
                    summary=self._truncate_optional(
                        candidate.summary,
                        self.MAX_SUMMARY_LENGTH,
                    ),
                    keywords=self._normalize_keywords(
                        list(existing.keywords) + candidate.keywords
                    ),
                    weight=max(existing.weight, candidate.weight),
                ),
            )

        return await self.memory_service.create_memory(
            user_id=user_id,
            request=UserMemoryCreate(
                user_id=user_id,
                memory_type=candidate.memory_type,
                status="active",
                confidence=candidate.confidence,
                title=self._truncate(candidate.title, self.MAX_TITLE_LENGTH),
                content=self._truncate(candidate.content, self.MAX_CONTENT_LENGTH),
                summary=self._truncate_optional(
                    candidate.summary,
                    self.MAX_SUMMARY_LENGTH,
                ),
                source_type="conversation_message",
                source_id=message_id,
                source_ref=analysis_thread_id,
                source_metadata={
                    "analysis_thread_id": analysis_thread_id,
                    "analysis_record_id": analysis_record_id,
                    "message_type": message_type,
                    "conversation_source": source,
                    "payload_keys": sorted((payload or {}).keys()),
                    "extraction_version": "stage_7_6_step_8_v1",
                },
                keywords=self._normalize_keywords(candidate.keywords),
                weight=candidate.weight,
            ),
        )

    async def _find_similar_memory(
        self,
        *,
        user_id: int,
        candidate: ConversationMemoryCandidate,
    ) -> UserMemoryResponse | None:
        keyword = candidate.keywords[0] if candidate.keywords else None

        query = UserMemoryListQuery(
            memory_type=candidate.memory_type,
            keyword=keyword,
            include_inactive=False,
            limit=20,
            offset=0,
        )
        result = await self.memory_service.list_memories(
            user_id=user_id,
            query=query,
        )

        candidate_keywords = {keyword.lower() for keyword in candidate.keywords}
        for memory in result.items:
            memory_keywords = {keyword.lower() for keyword in memory.keywords}
            if candidate_keywords & memory_keywords:
                return memory

        return None

    def _extract_risk_preference(
        self,
        content: str,
    ) -> str | None:
        normalized = content.lower()

        if any(
            token in normalized
            for token in ("保守", "稳健", "低风险", "不激进", "不要太激进", "不想太激进")
        ):
            return "conservative"

        if any(
            token in normalized
            for token in ("激进", "进取", "高风险", "能承受波动", "可以承受波动")
        ):
            return "aggressive"

        if any(token in normalized for token in ("均衡", "平衡", "balanced")):
            return "balanced"

        return None

    def _match_rule_labels(
        self,
        content: str,
        rules: dict[str, tuple[str, ...]],
    ) -> list[str]:
        normalized = content.lower()
        labels: list[str] = []

        for label, patterns in rules.items():
            for pattern in patterns:
                if pattern.lower() in normalized:
                    labels.append(label)
                    break

        return labels

    def _normalize_text(
        self,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            return None

        return normalized

    def _normalize_keywords(
        self,
        keywords: list[str],
    ) -> list[str]:
        normalized_keywords: list[str] = []
        seen: set[str] = set()

        for item in keywords:
            keyword = str(item).strip()
            if not keyword:
                continue

            lowered = keyword.lower()
            if lowered in seen:
                continue

            seen.add(lowered)
            normalized_keywords.append(keyword[:50])

            if len(normalized_keywords) >= self.MAX_KEYWORDS:
                break

        return normalized_keywords

    def _max_confidence(
        self,
        old_confidence: str,
        new_confidence: str,
    ) -> str:
        priority = {
            "low": 1,
            "medium": 2,
            "high": 3,
        }

        if priority.get(new_confidence, 0) >= priority.get(old_confidence, 0):
            return new_confidence

        return old_confidence

    def _truncate(
        self,
        value: str,
        max_length: int,
    ) -> str:
        return value[:max_length]

    def _truncate_optional(
        self,
        value: str | None,
        max_length: int,
    ) -> str | None:
        if value is None:
            return None

        return value[:max_length]