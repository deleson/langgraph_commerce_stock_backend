from __future__ import annotations

"""每日简报数据收集服务。

本文件负责把生成日报所需的数据一次性收集成 DailyReportDataContext：
自选股、用户偏好、市场概览、策略信号、候选评分、用户画像和相关记忆。

它只做数据准备，不生成日报文案，也不调用 AI。
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.daily_report import (
    DailyReportGenerateRequest,
    DailyReportInputSnapshot,
    DailyReportSource,
)
from app.schemas.market_data import MarketCode
from app.schemas.stock_candidate import (
    StockCandidateRequest,
    StockCandidateSymbol,
)
from app.schemas.user_memory_embedding import UserMemoryRetrievalRequest
from app.services.market_service import MarketService
from app.services.stock_candidate_query_service import StockCandidateQueryService
from app.services.strategy_signal_query_service import StrategySignalQueryService
from app.services.user_memory_query_service import UserMemoryQueryService
from app.services.user_memory_retrieval_service import UserMemoryRetrievalService
from app.services.user_preference_service import AsyncUserPreferenceService
from app.services.watchlist_service import AsyncWatchlistService


@dataclass(slots=True)
class DailyReportStockDataItem:
    """日报中单只自选股的数据快照。"""

    symbol: str
    market: str
    name: str | None = None
    market_overview: dict[str, Any] | None = None
    strategy_signal: dict[str, Any] | None = None
    warnings: list[str] | None = None


@dataclass(slots=True)
class DailyReportDataContext:
    """日报生成上下文。

    DailyReportService 会基于这个上下文生成确定性日报；
    DailyReportAIService 也只会在这个上下文基础上润色，不额外编造信息。
    """

    user_id: int
    report_date: date
    request: DailyReportGenerateRequest
    input_snapshot: DailyReportInputSnapshot
    watchlist_items: list[dict[str, Any]]
    stock_items: list[DailyReportStockDataItem]
    user_preference: dict[str, Any] | None
    user_profile_context: dict[str, Any] | None
    relevant_memories_context: dict[str, Any] | None
    candidate_result: dict[str, Any] | None
    warnings: list[str]


class DailyReportDataService:
    """收集每日简报所需的用户与行情上下文。"""

    MAX_WARNING_COUNT = 30
    RELEVANT_MEMORY_TOP_K = 5

    def __init__(
        self,
        db: AsyncSession,
        *,
        watchlist_service: AsyncWatchlistService | None = None,
        user_preference_service: AsyncUserPreferenceService | None = None,
        market_service: MarketService | None = None,
        strategy_signal_query_service: StrategySignalQueryService | None = None,
        stock_candidate_query_service: StockCandidateQueryService | None = None,
        user_memory_query_service: UserMemoryQueryService | None = None,
        user_memory_retrieval_service: UserMemoryRetrievalService | None = None,
    ) -> None:
        self.db = db
        self.watchlist_service = watchlist_service or AsyncWatchlistService(db)
        self.user_preference_service = (
            user_preference_service or AsyncUserPreferenceService(db)
        )
        self.market_service = market_service or MarketService(db)
        self.strategy_signal_query_service = (
            strategy_signal_query_service or StrategySignalQueryService(db)
        )
        self.stock_candidate_query_service = (
            stock_candidate_query_service or StockCandidateQueryService(db)
        )
        self.user_memory_query_service = (
            user_memory_query_service or UserMemoryQueryService(db)
        )
        self.user_memory_retrieval_service = (
            user_memory_retrieval_service or UserMemoryRetrievalService(db)
        )

    async def collect_daily_report_data(
        self,
        *,
        user: User,
        request: DailyReportGenerateRequest,
        report_date: date,
        source: DailyReportSource,
    ) -> DailyReportDataContext:
        """收集某个用户某一天的日报数据。

        自选股是日报的核心股票池；用户画像和记忆是增强上下文；
        候选评分用于提供研究优先级。任何单只股票读取失败只进入 warnings，
        不应导致整个日报生成直接崩溃。
        """

        warnings: list[str] = []

        watchlist_models = await self.watchlist_service.list_my_watchlist(user)
        limited_watchlist = watchlist_models[: request.max_watchlist_items]

        if len(watchlist_models) > len(limited_watchlist):
            warnings.append(
                f"自选股数量为 {len(watchlist_models)}，本次简报仅纳入前 {len(limited_watchlist)} 只。"
            )

        watchlist_items = [
            self._serialize_watchlist_item(item)
            for item in limited_watchlist
        ]

        user_preference = await self._load_user_preference(user=user)

        user_profile_context = None
        if request.include_user_profile:
            user_profile_context = await self._load_user_profile_context(
                user_id=user.id,
                warnings=warnings,
            )

        relevant_memories_context = None
        if request.include_relevant_memories:
            relevant_memories_context = await self._load_relevant_memories_context(
                user_id=user.id,
                watchlist_items=watchlist_items,
                user_profile_context=user_profile_context,
                warnings=warnings,
            )

        stock_items = await self._load_stock_items(
            watchlist_items=watchlist_items,
            warnings=warnings,
        )

        candidate_result = None
        if request.include_candidates and watchlist_items:
            candidate_result = await self._load_candidate_result(
                user=user,
                watchlist_items=watchlist_items,
                request=request,
                warnings=warnings,
            )

        input_snapshot = DailyReportInputSnapshot(
            report_date=report_date,
            source=source,
            watchlist_count=len(watchlist_models),
            included_stock_count=len(limited_watchlist),
            include_candidates=request.include_candidates,
            include_user_profile=request.include_user_profile,
            include_relevant_memories=request.include_relevant_memories,
            use_ai=request.use_ai,
            notify=request.notify,
        )

        return DailyReportDataContext(
            user_id=user.id,
            report_date=report_date,
            request=request,
            input_snapshot=input_snapshot,
            watchlist_items=watchlist_items,
            stock_items=stock_items,
            user_preference=user_preference,
            user_profile_context=user_profile_context,
            relevant_memories_context=relevant_memories_context,
            candidate_result=candidate_result,
            warnings=self._limit_warnings(warnings),
        )

    async def _load_stock_items(
        self,
        *,
        watchlist_items: list[dict[str, Any]],
        warnings: list[str],
    ) -> list[DailyReportStockDataItem]:
        """逐只自选股读取市场概览和策略信号。

        这里采用安全读取：某只股票失败只记录 warning，日报仍可基于其他股票继续生成。
        """

        stock_items: list[DailyReportStockDataItem] = []

        for item in watchlist_items:
            symbol = item["symbol"]
            market = item["market"]
            item_warnings: list[str] = []

            market_overview = await self._safe_get_market_overview(
                symbol=symbol,
                market=market,
                warnings=item_warnings,
            )
            strategy_signal = await self._safe_get_strategy_signal(
                symbol=symbol,
                market=market,
                warnings=item_warnings,
            )

            for warning in item_warnings:
                warnings.append(f"{market}:{symbol} - {warning}")

            stock_items.append(
                DailyReportStockDataItem(
                    symbol=symbol,
                    market=market,
                    name=item.get("name"),
                    market_overview=market_overview,
                    strategy_signal=strategy_signal,
                    warnings=item_warnings,
                )
            )

        return stock_items

    async def _safe_get_market_overview(
        self,
        *,
        symbol: str,
        market: str,
        warnings: list[str],
    ) -> dict[str, Any] | None:
        try:
            overview = await self.market_service.get_overview(
                symbol=symbol,
                market=market,
                include_technical_indicators=True,
                include_data_quality=True,
                include_sync_status=True,
                include_strategy_signal=True,
            )
            return self._dump_model(overview)
        except Exception as exc:
            warnings.append(f"行情概览读取失败：{self._safe_exception_message(exc)}")
            return None

    async def _safe_get_strategy_signal(
        self,
        *,
        symbol: str,
        market: str,
        warnings: list[str],
    ) -> dict[str, Any] | None:
        try:
            signal = await self.strategy_signal_query_service.get_signal(
                symbol=symbol,
                market=market,
            )
            return self._dump_model(signal)
        except Exception as exc:
            warnings.append(f"策略信号读取失败：{self._safe_exception_message(exc)}")
            return None

    async def _load_candidate_result(
        self,
        *,
        user: User,
        watchlist_items: list[dict[str, Any]],
        request: DailyReportGenerateRequest,
        warnings: list[str],
    ) -> dict[str, Any] | None:
        try:
            candidate_request = StockCandidateRequest(
                universe_source="manual",
                symbols=[
                    StockCandidateSymbol(
                        symbol=item["symbol"],
                        market=item["market"],
                    )
                    for item in watchlist_items
                ],
                top_n=request.max_candidate_items,
                include_excluded=False,
                include_score_breakdown=True,
                include_strategy_signal=True,
                include_data_quality=True,
            )
            candidate_result = await self.stock_candidate_query_service.run_stock_candidates(
                user=user,
                request=candidate_request,
            )
            return self._dump_model(candidate_result)
        except Exception as exc:
            warnings.append(f"候选评分读取失败：{self._safe_exception_message(exc)}")
            return None

    async def _load_user_preference(self, *, user: User) -> dict[str, Any] | None:
        try:
            preference = await self.user_preference_service.get_or_create_my_preference(
                user
            )
            return {
                "risk_preference": getattr(preference, "risk_preference", None),
                "timezone": getattr(preference, "timezone", None),
                "notification_enabled": getattr(
                    preference,
                    "notification_enabled",
                    None,
                ),
            }
        except Exception:
            return None

    async def _load_user_profile_context(
        self,
        *,
        user_id: int,
        warnings: list[str],
    ) -> dict[str, Any] | None:
        try:
            return await self.user_memory_query_service.get_profile_context(
                user_id=user_id,
            )
        except Exception as exc:
            warnings.append(f"用户画像读取失败：{self._safe_exception_message(exc)}")
            return None

    async def _load_relevant_memories_context(
        self,
        *,
        user_id: int,
        watchlist_items: list[dict[str, Any]],
        user_profile_context: dict[str, Any] | None,
        warnings: list[str],
    ) -> dict[str, Any] | None:
        query = self._build_relevant_memory_query(
            watchlist_items=watchlist_items,
            user_profile_context=user_profile_context,
        )

        if not query:
            return None

        try:
            response = await self.user_memory_retrieval_service.search_similar_memories(
                user_id=user_id,
                request=UserMemoryRetrievalRequest(
                    query=query,
                    top_k=self.RELEVANT_MEMORY_TOP_K,
                    include_content=False,
                ),
            )
            return self._dump_model(response)
        except Exception as exc:
            warnings.append(f"相似记忆检索失败：{self._safe_exception_message(exc)}")
            return None

    def _build_relevant_memory_query(
        self,
        *,
        watchlist_items: list[dict[str, Any]],
        user_profile_context: dict[str, Any] | None,
    ) -> str:
        symbols = [
            f"{item.get('market')}:{item.get('symbol')}"
            for item in watchlist_items[:10]
            if item.get("symbol") and item.get("market")
        ]

        profile_parts: list[str] = []
        if user_profile_context:
            summary = user_profile_context.get("summary")
            if isinstance(summary, dict):
                risk_preference = summary.get("risk_preference")
                risk_focuses = summary.get("risk_focuses")
                if risk_preference:
                    profile_parts.append(f"风险偏好 {risk_preference}")
                if risk_focuses:
                    profile_parts.append(f"关注风险 {risk_focuses}")

        query_parts = ["每日简报", "自选股", *symbols, *profile_parts]
        return " ".join(str(part) for part in query_parts if part)

    def _serialize_watchlist_item(self, item) -> dict[str, Any]:
        return {
            "id": item.id,
            "symbol": item.symbol,
            "market": item.market,
            "name": item.name,
            "notes": item.notes,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    def _dump_model(self, value) -> dict[str, Any]:
        if value is None:
            return {}

        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")

        if isinstance(value, dict):
            return value

        return {}

    def _limit_warnings(self, warnings: list[str]) -> list[str]:
        return warnings[: self.MAX_WARNING_COUNT]

    def _safe_exception_message(self, exc: Exception) -> str:
        message = str(exc).strip()
        return message[:200] if message else exc.__class__.__name__
