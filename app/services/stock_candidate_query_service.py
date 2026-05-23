from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.stock_candidate import (
    StockCandidateInputSnapshot,
    StockCandidateRequest,
    StockCandidateResponse,
    StockCandidateUnavailableReason,
)
from app.services.stock_candidate_data_service import (
    StockCandidateDataItem,
    StockCandidateDataService,
    StockCandidateUniverseItem,
)
from app.services.stock_candidate_scoring_service import StockCandidateScoringService
from app.services.user_preference_service import AsyncUserPreferenceService
from app.services.watchlist_service import AsyncWatchlistService


class StockCandidateQueryService:
    """Orchestrate stock candidate recommendation flow.

    This service does not calculate indicators and does not score directly.
    It connects universe loading, user preference, candidate data loading,
    scoring, ranking, and response assembly.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        watchlist_service: AsyncWatchlistService | None = None,
        preference_service: AsyncUserPreferenceService | None = None,
        data_service: StockCandidateDataService | None = None,
        scoring_service: StockCandidateScoringService | None = None,
    ) -> None:
        self.db = db
        self.watchlist_service = watchlist_service or AsyncWatchlistService(db)
        self.preference_service = preference_service or AsyncUserPreferenceService(db)
        self.data_service = data_service or StockCandidateDataService(db)
        self.scoring_service = scoring_service or StockCandidateScoringService()

    async def run_stock_candidates(
        self,
        *,
        request: StockCandidateRequest,
        user: User,
    ) -> StockCandidateResponse:
        universe = await self._build_universe(
            request=request,
            user=user,
        )

        if not universe:
            return self._build_unavailable_response(
                request=request,
                unavailable_reason="empty_universe",
                summary="当前候选股票池为空，未执行候选评分。",
                requested_symbol_count=0,
                evaluated_symbol_count=0,
                candidate_count=0,
                excluded_count=0,
                warnings=["请手动传入候选股票，或先添加自选股后再使用 watchlist 来源。"],
            )

        data_items = await self.data_service.get_data_for_candidates(
            candidates=universe,
            timeframe=request.timeframe,
            limit=request.limit,
            min_required_candles=request.min_required_candles,
            adjust_type=request.adjust_type,
            source=request.source,
            enforce_data_quality=request.enforce_data_quality,
            stale_after_days=request.data_quality_stale_after_days,
            include_strategy_signal=request.include_strategy_signal,
        )

        preference = await self.preference_service.get_or_create_my_preference(user)
        risk_preference = getattr(preference, "risk_preference", "balanced")

        scored_items = self.scoring_service.score_candidates(
            data_items,
            risk_preference=risk_preference,
            include_score_breakdown=request.include_score_breakdown,
            include_strategy_signal=request.include_strategy_signal,
            include_data_quality=request.include_data_quality,
        )

        candidates, excluded = self.scoring_service.rank_and_filter_candidates(
            scored_items,
            top_n=request.top_n,
        )

        warnings = self._build_warnings(
            request=request,
            universe=universe,
            data_items=data_items,
            candidates=candidates,
            excluded=excluded,
            risk_preference=risk_preference,
        )

        input_snapshot = self._build_input_snapshot(
            request=request,
            requested_symbol_count=len(universe),
            evaluated_symbol_count=len(data_items),
            candidate_count=len(candidates),
            excluded_count=len(excluded),
        )

        if not candidates:
            unavailable_reason = self._resolve_unavailable_reason(data_items)
            return StockCandidateResponse(
                status="unavailable",
                unavailable_reason=unavailable_reason,
                summary=self._build_summary(
                    candidate_count=0,
                    excluded_count=len(excluded),
                    risk_preference=risk_preference,
                    unavailable_reason=unavailable_reason,
                ),
                candidates=[],
                excluded=excluded if request.include_excluded else [],
                input_snapshot=input_snapshot,
                warnings=warnings,
            )

        return StockCandidateResponse(
            status="available",
            unavailable_reason=None,
            summary=self._build_summary(
                candidate_count=len(candidates),
                excluded_count=len(excluded),
                risk_preference=risk_preference,
                unavailable_reason=None,
            ),
            candidates=candidates,
            excluded=excluded if request.include_excluded else [],
            input_snapshot=input_snapshot,
            warnings=warnings,
        )

    async def _build_universe(
        self,
        *,
        request: StockCandidateRequest,
        user: User,
    ) -> list[StockCandidateUniverseItem]:
        if request.universe_source == "manual":
            return [
                StockCandidateUniverseItem(
                    symbol=item.symbol,
                    market=item.market,
                    name=None,
                )
                for item in request.symbols
            ]

        if request.universe_source == "watchlist":
            watchlist_items = await self.watchlist_service.list_my_watchlist(user)
            return [
                StockCandidateUniverseItem(
                    symbol=item.symbol,
                    market=item.market,
                    name=item.name,
                )
                for item in watchlist_items
            ]

        return []

    def _build_input_snapshot(
        self,
        *,
        request: StockCandidateRequest,
        requested_symbol_count: int,
        evaluated_symbol_count: int,
        candidate_count: int,
        excluded_count: int,
    ) -> StockCandidateInputSnapshot:
        return StockCandidateInputSnapshot(
            universe_source=request.universe_source,
            requested_symbol_count=requested_symbol_count,
            evaluated_symbol_count=evaluated_symbol_count,
            candidate_count=candidate_count,
            excluded_count=excluded_count,
            top_n=request.top_n,
            timeframe=request.timeframe,
            limit=request.limit,
            min_required_candles=request.min_required_candles,
            adjust_type=request.adjust_type,
            source=request.source,
            enforce_data_quality=request.enforce_data_quality,
        )

    def _build_unavailable_response(
        self,
        *,
        request: StockCandidateRequest,
        unavailable_reason: StockCandidateUnavailableReason,
        summary: str,
        requested_symbol_count: int,
        evaluated_symbol_count: int,
        candidate_count: int,
        excluded_count: int,
        warnings: list[str],
    ) -> StockCandidateResponse:
        return StockCandidateResponse(
            status="unavailable",
            unavailable_reason=unavailable_reason,
            summary=summary,
            candidates=[],
            excluded=[],
            input_snapshot=self._build_input_snapshot(
                request=request,
                requested_symbol_count=requested_symbol_count,
                evaluated_symbol_count=evaluated_symbol_count,
                candidate_count=candidate_count,
                excluded_count=excluded_count,
            ),
            warnings=warnings,
        )

    def _resolve_unavailable_reason(
        self,
        data_items: list[StockCandidateDataItem],
    ) -> StockCandidateUnavailableReason:
        if not data_items:
            return "empty_universe"

        if all(
            item.data_quality is not None and item.data_quality.is_empty
            for item in data_items
        ):
            return "no_data"

        if all(
            item.data_quality is not None
            and (not item.data_quality.is_enough or item.data_quality.is_stale)
            for item in data_items
        ):
            return "insufficient_data"

        return "no_candidates"

    def _build_summary(
        self,
        *,
        candidate_count: int,
        excluded_count: int,
        risk_preference: str,
        unavailable_reason: StockCandidateUnavailableReason | None,
    ) -> str:
        if unavailable_reason is not None:
            return (
                "阶段六点五候选股票评分已执行，但当前没有股票进入候选优先列表。"
                f"风险偏好：{risk_preference}；"
                f"排除数量：{excluded_count}；"
                f"不可用原因：{unavailable_reason}。"
            )

        return (
            "阶段六点五候选股票评分已完成。"
            f"本次生成候选 {candidate_count} 只，"
            f"排除 {excluded_count} 只，"
            f"已按用户风险偏好 {risk_preference} 进行评分和排序。"
        )

    def _build_warnings(
        self,
        *,
        request: StockCandidateRequest,
        universe: list[StockCandidateUniverseItem],
        data_items: list[StockCandidateDataItem],
        candidates: list,
        excluded: list,
        risk_preference: str,
    ) -> list[str]:
        warnings: list[str] = [
            "候选股票评分只作为研究线索，不构成投资建议，也不承诺未来收益。",
            "阶段六点五第一版使用确定性量化规则，不让 AI 自由推荐股票。",
            f"本次使用的用户风险偏好为 {risk_preference}。",
        ]

        if request.universe_source == "manual":
            warnings.append("当前股票池来源为 manual，仅从请求传入的 symbols 中筛选。")

        if request.universe_source == "watchlist":
            warnings.append("当前股票池来源为 watchlist，仅从当前登录用户自选股中筛选。")

        if not request.include_excluded and excluded:
            warnings.append("本次响应默认不返回 excluded 明细，如需查看排除原因可设置 include_excluded=true。")

        if len(universe) > len(data_items):
            warnings.append("部分候选股票未完成数据读取，请检查数据源或行情同步状态。")

        if not candidates:
            warnings.append("当前没有股票进入候选优先列表，建议检查数据质量、股票池范围或评分条件。")

        return self._limit_text_list(warnings, limit=30)

    def _limit_text_list(
        self,
        values: list[str],
        *,
        limit: int,
    ) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for value in values:
            text = str(value).strip()
            if not text or text in seen:
                continue

            seen.add(text)
            result.append(text[:300])

            if len(result) >= limit:
                break

        return result