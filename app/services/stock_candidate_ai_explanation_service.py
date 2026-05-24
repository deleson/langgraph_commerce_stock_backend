import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.core.llm import get_chat_model
from app.schemas.stock_candidate import (
    StockCandidateItem,
    StockCandidateResponse,
    StockCandidateScoreBreakdown,
    StockCandidateScoreRuleResult,
)
from app.schemas.stock_candidate_ai_explanation import (
    StockCandidateAIComparisonItem,
    StockCandidateAIExplanationInputSnapshot,
    StockCandidateAIExplanationItem,
    StockCandidateAIExplanationRequest,
    StockCandidateAIExplanationResponse,
    StockCandidateAIResearchPriorityItem,
    StockCandidateAIRiskSummary,
)


logger = logging.getLogger(__name__)


class StockCandidateAIExplanationService:
    """Generate AI explanations for deterministic stock candidate results.

    This service does not score stocks and does not query the database.
    It only trims StockCandidateResponse, calls the LLM, parses the result,
    and falls back to deterministic text when the LLM is unavailable.
    """

    MAX_REASONS = 5
    MAX_RISKS = 5
    MAX_RULES = 5
    MAX_WARNINGS = 5

    DISCLAIMER = (
        "本 AI 候选解释仅基于系统已生成的量化候选评分结果进行中文解释、"
        "候选对比和研究优先级总结，只能作为研究线索，"
        "不构成投资建议，也不承诺未来收益。"
    )

    async def explain_candidates(
        self,
        *,
        request: StockCandidateAIExplanationRequest,
        candidate_result: StockCandidateResponse,
    ) -> StockCandidateAIExplanationResponse:
        """Generate an AI explanation from an existing candidate scoring result."""

        input_snapshot = self._build_input_snapshot(
            request=request,
            candidate_result=candidate_result,
        )

        if candidate_result.status != "available":
            return self._build_unavailable_response(
                request=request,
                candidate_result=candidate_result,
                input_snapshot=input_snapshot,
                unavailable_reason="candidate_scoring_unavailable",
                fallback_reason="候选评分结果不可用，无法继续进行 AI 候选解释。",
            )

        candidates = candidate_result.candidates[: request.max_candidates_to_explain]
        if not candidates:
            return self._build_unavailable_response(
                request=request,
                candidate_result=candidate_result,
                input_snapshot=input_snapshot,
                unavailable_reason="empty_candidates",
                fallback_reason="候选评分结果中没有可解释的候选股票。",
            )

        ai_context = self._build_ai_context(
            request=request,
            candidate_result=candidate_result,
            candidates=candidates,
        )

        try:
            messages = self._build_messages(ai_context)
            llm = get_chat_model()
            llm_response = await llm.ainvoke(messages)
            raw_content = str(llm_response.content).strip()

            return self._parse_ai_response(
                raw_content=raw_content,
                request=request,
                candidate_result=candidate_result,
                input_snapshot=input_snapshot,
            )
        except Exception as exc:
            logger.exception("stock candidate ai explanation failed")

            if request.allow_fallback:
                return self._build_fallback_response(
                    request=request,
                    candidate_result=candidate_result,
                    candidates=candidates,
                    input_snapshot=input_snapshot,
                    fallback_reason=self._safe_exception_message(exc),
                )

            return self._build_unavailable_response(
                request=request,
                candidate_result=candidate_result,
                input_snapshot=input_snapshot,
                unavailable_reason="llm_error",
                fallback_reason=self._safe_exception_message(exc),
            )

    def _build_messages(
        self,
        ai_context: dict[str, Any],
    ) -> list[SystemMessage | HumanMessage]:
        system_prompt = (
            "你是一个中文股票研究助理。"
            "你只能基于用户提供的量化候选评分结果进行解释和对比。"
            "你不能自由推荐股票，不能修改 score、grade、rank，"
            "不能承诺收益，不能说必须买入，不能构成投资建议。"
            "请输出严格 JSON，不要输出 Markdown。"
        )

        human_prompt = (
            "请根据下面的候选评分上下文，生成中文 AI 候选解释。\n"
            "输出 JSON 字段必须包含：summary, candidate_explanations, "
            "comparisons, research_priorities, risk_summary, warnings。\n"
            "candidate_explanations 每项包含：symbol, market, name, rank, score, "
            "grade, explanation, key_strengths, key_risks, research_focus。\n"
            "comparisons 每项包含：symbol, market, compared_with, "
            "relative_strengths, relative_weaknesses, comparison_summary。\n"
            "research_priorities 每项包含：priority_rank, priority_level, symbol, "
            "market, grade, score, reason, suggested_next_steps。\n"
            "risk_summary 包含：overall_risk_level, summary, key_risks, risk_controls。\n\n"
            f"{json.dumps(ai_context, ensure_ascii=False)}"
        )

        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ]

    def _parse_ai_response(
        self,
        *,
        raw_content: str,
        request: StockCandidateAIExplanationRequest,
        candidate_result: StockCandidateResponse,
        input_snapshot: StockCandidateAIExplanationInputSnapshot,
    ) -> StockCandidateAIExplanationResponse:
        payload = self._load_json_content(raw_content)

        response = StockCandidateAIExplanationResponse(
            status="available",
            unavailable_reason=None,
            ai_used=True,
            fallback_reason=None,
            summary=payload.get("summary") or "AI 已完成候选股票解释。",
            candidate_explanations=[
                StockCandidateAIExplanationItem.model_validate(item)
                for item in payload.get("candidate_explanations", [])
            ],
            comparisons=[
                StockCandidateAIComparisonItem.model_validate(item)
                for item in payload.get("comparisons", [])
            ] if request.include_comparison else [],
            research_priorities=[
                StockCandidateAIResearchPriorityItem.model_validate(item)
                for item in payload.get("research_priorities", [])
            ] if request.include_research_priority else [],
            risk_summary=(
                StockCandidateAIRiskSummary.model_validate(payload["risk_summary"])
                if request.include_risk_summary and payload.get("risk_summary")
                else None
            ),
            source_candidate_result=candidate_result,
            input_snapshot=input_snapshot,
            warnings=self._trim_text_list(payload.get("warnings", []), limit=10),
            disclaimer=self.DISCLAIMER,
        )

        if not response.candidate_explanations:
            raise ValueError("AI response candidate_explanations is empty")

        return response

    def _load_json_content(self, raw_content: str) -> dict[str, Any]:
        content = raw_content.strip()

        if content.startswith("```json"):
            content = content.removeprefix("```json").strip()
        if content.startswith("```"):
            content = content.removeprefix("```").strip()
        if content.endswith("```"):
            content = content.removesuffix("```").strip()

        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("AI response is not valid JSON") from exc

        if not isinstance(data, dict):
            raise ValueError("AI response JSON must be an object")

        return data

    def _build_ai_context(
        self,
        *,
        request: StockCandidateAIExplanationRequest,
        candidate_result: StockCandidateResponse,
        candidates: list[StockCandidateItem],
    ) -> dict[str, Any]:
        return {
            "task": "explain_stock_candidates",
            "language": "zh-CN",
            "boundaries": {
                "not_investment_advice": True,
                "do_not_change_score": True,
                "do_not_change_grade": True,
                "do_not_change_rank": True,
                "do_not_recommend_direct_buy": True,
            },
            "explanation_style": request.explanation_style,
            "source_summary": candidate_result.summary,
            "input_snapshot": (
                candidate_result.input_snapshot.model_dump(mode="json")
                if candidate_result.input_snapshot
                else None
            ),
            "candidates": [
                self._build_candidate_context(candidate)
                for candidate in candidates
            ],
            "warnings": self._trim_text_list(
                candidate_result.warnings,
                limit=self.MAX_WARNINGS,
            ),
            "disclaimer": candidate_result.disclaimer,
        }

    def _build_candidate_context(
        self,
        candidate: StockCandidateItem,
    ) -> dict[str, Any]:
        return {
            "symbol": candidate.symbol,
            "market": candidate.market,
            "name": candidate.name,
            "decision": candidate.decision,
            "rank": candidate.rank,
            "score": candidate.score,
            "grade": candidate.grade,
            "reasons": self._trim_text_list(candidate.reasons, limit=self.MAX_REASONS),
            "risks": self._trim_text_list(candidate.risks, limit=self.MAX_RISKS),
            "score_breakdown": self._build_score_breakdown_context(
                candidate.score_breakdown,
            ),
            "data_quality": (
                self._build_data_quality_context(candidate.data_quality)
                if candidate.data_quality
                else None
            ),
            "strategy_signal": (
                self._build_strategy_signal_context(candidate.strategy_signal)
                if candidate.strategy_signal
                else None
            ),
        }

    def _build_score_breakdown_context(
        self,
        breakdown: StockCandidateScoreBreakdown | None,
    ) -> dict[str, Any] | None:
        if breakdown is None:
            return None

        return {
            "formula_version": breakdown.formula_version,
            "base_score": breakdown.base_score,
            "data_quality_score": breakdown.data_quality_score,
            "trend_score": breakdown.trend_score,
            "momentum_score": breakdown.momentum_score,
            "rsi_score": breakdown.rsi_score,
            "macd_score": breakdown.macd_score,
            "volatility_score": breakdown.volatility_score,
            "volume_score": breakdown.volume_score,
            "liquidity_score": breakdown.liquidity_score,
            "strategy_signal_score": breakdown.strategy_signal_score,
            "backtest_performance_score": breakdown.backtest_performance_score,
            "risk_score": breakdown.risk_score,
            "user_preference_score": breakdown.user_preference_score,
            "raw_score": breakdown.raw_score,
            "final_score": breakdown.final_score,
            "top_positive_rules": self._build_rule_results_context(
                breakdown.rule_results,
                positive=True,
            ),
            "top_negative_rules": self._build_rule_results_context(
                breakdown.rule_results,
                positive=False,
            ),
        }

    def _build_rule_results_context(
        self,
        rule_results: list[StockCandidateScoreRuleResult],
        *,
        positive: bool,
    ) -> list[dict[str, Any]]:
        if positive:
            filtered = [item for item in rule_results if item.score_delta > 0]
            sorted_items = sorted(
                filtered,
                key=lambda item: item.score_delta,
                reverse=True,
            )
        else:
            filtered = [item for item in rule_results if item.score_delta < 0]
            sorted_items = sorted(
                filtered,
                key=lambda item: item.score_delta,
            )

        return [
            {
                "dimension": item.dimension,
                "score_delta": item.score_delta,
                "reason": item.reason,
                "warnings": self._trim_text_list(item.warnings, limit=3),
            }
            for item in sorted_items[: self.MAX_RULES]
        ]

    def _build_data_quality_context(self, data_quality: Any) -> dict[str, Any]:
        return {
            "status": data_quality.status,
            "candle_count": data_quality.candle_count,
            "is_empty": data_quality.is_empty,
            "is_enough": data_quality.is_enough,
            "is_stale": data_quality.is_stale,
            "warnings": self._trim_text_list(data_quality.warnings, limit=3),
            "errors": self._trim_text_list(data_quality.errors, limit=3),
        }

    def _build_strategy_signal_context(self, strategy_signal: Any) -> dict[str, Any]:
        return {
            "status": strategy_signal.status,
            "signal": strategy_signal.signal,
            "strength": strategy_signal.strength,
            "score": strategy_signal.score,
            "summary": strategy_signal.summary,
        }

    def _build_input_snapshot(
        self,
        *,
        request: StockCandidateAIExplanationRequest,
        candidate_result: StockCandidateResponse,
    ) -> StockCandidateAIExplanationInputSnapshot:
        candidates = candidate_result.candidates[: request.max_candidates_to_explain]
        formula_versions = sorted(
            {
                candidate.score_breakdown.formula_version
                for candidate in candidates
                if candidate.score_breakdown is not None
            }
        )

        return StockCandidateAIExplanationInputSnapshot(
            universe_source=request.candidate_request.universe_source,
            requested_top_n=request.candidate_request.top_n,
            candidate_count=len(candidate_result.candidates),
            explained_candidate_count=len(candidates),
            explanation_style=request.explanation_style,
            include_comparison=request.include_comparison,
            include_research_priority=request.include_research_priority,
            include_risk_summary=request.include_risk_summary,
            score_formula_versions=formula_versions,
            ai_context_truncated=True,
        )

    def _build_fallback_response(
        self,
        *,
        request: StockCandidateAIExplanationRequest,
        candidate_result: StockCandidateResponse,
        candidates: list[StockCandidateItem],
        input_snapshot: StockCandidateAIExplanationInputSnapshot,
        fallback_reason: str,
    ) -> StockCandidateAIExplanationResponse:
        explanations = [
            self._build_fallback_explanation(candidate)
            for candidate in candidates
        ]

        research_priorities = [
            self._build_fallback_priority(candidate, index=index)
            for index, candidate in enumerate(candidates, start=1)
        ] if request.include_research_priority else []

        return StockCandidateAIExplanationResponse(
            status="fallback",
            unavailable_reason="llm_error",
            ai_used=False,
            fallback_reason=fallback_reason,
            summary=(
                "AI 候选解释暂时不可用，系统已基于确定性候选评分结果生成降级解释。"
            ),
            candidate_explanations=explanations,
            comparisons=[],
            research_priorities=research_priorities,
            risk_summary=(
                self._build_fallback_risk_summary(candidates)
                if request.include_risk_summary
                else None
            ),
            source_candidate_result=candidate_result,
            input_snapshot=input_snapshot,
            warnings=[
                "当前结果为降级解释，未成功使用 LLM 生成。",
                "候选股票评分和解释只作为研究线索，不构成投资建议。",
            ],
            disclaimer=self.DISCLAIMER,
        )

    def _build_fallback_explanation(
        self,
        candidate: StockCandidateItem,
    ) -> StockCandidateAIExplanationItem:
        strengths = self._trim_text_list(candidate.reasons, limit=3)
        risks = self._trim_text_list(candidate.risks, limit=3)

        return StockCandidateAIExplanationItem(
            symbol=candidate.symbol,
            market=candidate.market,
            name=candidate.name,
            rank=candidate.rank,
            score=candidate.score,
            grade=candidate.grade,
            explanation=(
                f"{candidate.symbol} 当前候选评分为 {candidate.score} 分，"
                f"等级为 {candidate.grade}。该解释基于系统确定性评分规则生成，"
                "未使用 AI 扩展分析。"
            ),
            key_strengths=strengths,
            key_risks=risks,
            research_focus=[
                "查看主要加分维度是否稳定。",
                "确认主要风险项是否可以接受。",
                "结合自身风险偏好继续研究。",
            ],
        )

    def _build_fallback_priority(
        self,
        candidate: StockCandidateItem,
        *,
        index: int,
    ) -> StockCandidateAIResearchPriorityItem:
        if candidate.grade == "A":
            priority_level = "high"
        elif candidate.grade == "B":
            priority_level = "medium"
        else:
            priority_level = "low"

        return StockCandidateAIResearchPriorityItem(
            priority_rank=index,
            priority_level=priority_level,
            symbol=candidate.symbol,
            market=candidate.market,
            grade=candidate.grade,
            score=candidate.score,
            reason=(
                f"{candidate.symbol} 当前排名第 {candidate.rank or index}，"
                f"评分 {candidate.score}，等级 {candidate.grade}，"
                "可按评分排序作为研究优先级参考。"
            ),
            suggested_next_steps=[
                "查看评分拆解中的主要加分和扣分项。",
                "结合策略信号和数据质量继续判断。",
            ],
        )

    def _build_fallback_risk_summary(
        self,
        candidates: list[StockCandidateItem],
    ) -> StockCandidateAIRiskSummary:
        risk_items: list[str] = []
        for candidate in candidates:
            risk_items.extend(candidate.risks[:2])

        return StockCandidateAIRiskSummary(
            overall_risk_level="medium",
            summary=(
                "当前风险摘要由确定性候选评分结果生成。候选评分较高不代表未来收益，"
                "仍需要关注市场波动、数据质量、策略信号失效和个人风险承受能力。"
            ),
            key_risks=self._trim_text_list(risk_items, limit=8),
            risk_controls=[
                "不要把候选评分直接等同于买入建议。",
                "不要只看单一分数，应结合风险项和数据质量。",
                "后续如进入交易或模拟盘，应设置资金和风控边界。",
            ],
        )

    def _build_unavailable_response(
        self,
        *,
        request: StockCandidateAIExplanationRequest,
        candidate_result: StockCandidateResponse,
        input_snapshot: StockCandidateAIExplanationInputSnapshot,
        unavailable_reason: str,
        fallback_reason: str,
    ) -> StockCandidateAIExplanationResponse:
        return StockCandidateAIExplanationResponse(
            status="unavailable",
            unavailable_reason=unavailable_reason,
            ai_used=False,
            fallback_reason=fallback_reason,
            summary=fallback_reason,
            candidate_explanations=[],
            comparisons=[],
            research_priorities=[],
            risk_summary=None,
            source_candidate_result=candidate_result,
            input_snapshot=input_snapshot,
            warnings=[
                "AI 候选解释未生成。",
                "候选解释只作为研究线索，不构成投资建议。",
            ],
            disclaimer=self.DISCLAIMER,
        )

    def _trim_text_list(
        self,
        values: list[str],
        *,
        limit: int,
    ) -> list[str]:
        return [
            str(value).strip()
            for value in values[:limit]
            if str(value).strip()
        ]

    def _safe_exception_message(self, exc: Exception) -> str:
        if isinstance(exc, ValidationError):
            return "AI 输出结构不符合候选解释响应格式。"

        message = str(exc).strip()
        if not message:
            return "AI 候选解释调用失败。"

        return message[:300]