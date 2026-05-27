import json
import logging
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.core.llm import get_chat_model
from app.core.exceptions import BadRequestException
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
    StockCandidateAIExplanationUnavailableReason,
)
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.repositories.ai_usage_repo import AsyncAIUsageRepository
from app.schemas.ai_usage import AIQuotaCheckRequest, AIUsageFeature
from app.services.ai_quota_service import AIQuotaService
from app.services.ai_usage_service import AIUsageService
from app.services.ai_usage_token_service import (
    AIUsageCostEstimate,
    AIUsageTokenEstimate,
    AIUsageTokenService,
)



logger = logging.getLogger(__name__)
CANDIDATE_AI_EXPLANATION_FEATURE: AIUsageFeature = "candidate_ai_explanation"

CANDIDATE_AI_EXPLANATION_ESTIMATED_COMPLETION_TOKENS = 1800

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

    MAX_COMPARISON_ITEMS = 10
    SCORE_DIFF_THRESHOLD = 5

    FORBIDDEN_INVESTMENT_PHRASES = (
        "必须买入",
        "建议买入",
        "推荐买入",
        "可以直接买入",
        "稳赚",
        "保证收益",
        "一定上涨",
        "必涨",
        "无风险",
        "满仓",
        "梭哈",
    )

    DISCLAIMER = (
        "本 AI 候选解释仅基于系统已生成的量化候选评分结果进行中文解释、"
        "候选对比和研究优先级总结，只能作为研究线索，"
        "不构成投资建议，也不承诺未来收益。"
    )
    JSON_OUTPUT_RULES = (
        "你必须只输出一个合法 JSON 对象，不要输出 Markdown，不要输出代码块，"
        "不要在 JSON 前后添加解释文字。所有自然语言内容必须使用简体中文。"
    )

    INVESTMENT_SAFETY_RULES = (
        "禁止使用“必须买入”“稳赚”“保证收益”“一定上涨”“无风险”等表达。"
        "可以使用“可作为研究线索”“需要继续观察”“风险需要重点确认”等谨慎表达。"
        "不得修改输入中的 score、grade、rank。"
    )

    EXPLANATION_QUALITY_RULES = (
        "解释要面向中文普通投资研究用户，避免生硬堆砌字段名。"
        "每只候选要说明：评分来源、相对优势、主要风险、后续研究重点。"
        "不要只重复“评分为多少、等级为多少”，要解释这些分数意味着什么。"
        "如果信息不足，要直接说明信息不足，不要补充外部事实。"
    )

    async def explain_candidates(
        self,
        *,
        request: StockCandidateAIExplanationRequest,
        candidate_result: StockCandidateResponse,
        user_id: int,
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

        messages = self._build_messages(ai_context)

        quota_allowed, quota_reason, estimated_tokens, estimated_cost = (
            await self._check_candidate_ai_quota(
                user_id=user_id,
                messages=messages,
            )
        )

        if not quota_allowed:
            await self._record_candidate_ai_blocked(
                user_id=user_id,
                request=request,
                candidate_result=candidate_result,
                reason=quota_reason or "AI quota is not enough",
                estimated_tokens=estimated_tokens,
                estimated_cost=estimated_cost,
            )

            return self._build_quota_blocked_response(
                request=request,
                candidate_result=candidate_result,
                candidates=candidates,
                input_snapshot=input_snapshot,
                quota_reason=quota_reason or "AI quota is not enough",
            )

        started_at = datetime.now(UTC)
        llm_response = None
        raw_content = ""

        try:
            llm = get_chat_model()
            llm_response = await llm.ainvoke(messages)
            raw_content = str(llm_response.content).strip()
        except Exception as exc:
            logger.exception("stock candidate ai explanation llm call failed")
            await self._record_candidate_ai_failed(
                user_id=user_id,
                request=request,
                candidate_result=candidate_result,
                response=llm_response,
                messages=messages,
                completion_text=raw_content,
                error_message=self._safe_exception_message(exc),
                started_at=started_at,
            )
            return self._build_exception_response(
                request=request,
                candidate_result=candidate_result,
                candidates=candidates,
                input_snapshot=input_snapshot,
                unavailable_reason=self._resolve_llm_error_reason(exc),
                exc=exc,
            )

        try:
            response = self._parse_ai_response(
                raw_content=raw_content,
                request=request,
                candidate_result=candidate_result,
                input_snapshot=input_snapshot,
            )
        except Exception as exc:
            logger.exception("stock candidate ai explanation parse failed")
            await self._record_candidate_ai_failed(
                user_id=user_id,
                request=request,
                candidate_result=candidate_result,
                response=llm_response,
                messages=messages,
                completion_text=raw_content,
                error_message=self._safe_exception_message(exc),
                started_at=started_at,
            )
            return self._build_exception_response(
                request=request,
                candidate_result=candidate_result,
                candidates=candidates,
                input_snapshot=input_snapshot,
                unavailable_reason="llm_parse_error",
                exc=exc,
            )

        await self._record_candidate_ai_success(
            user_id=user_id,
            request=request,
            candidate_result=candidate_result,
            response=llm_response,
            messages=messages,
            completion_text=raw_content,
            started_at=started_at,
        )

        return response

    def _build_messages(
        self,
        ai_context: dict[str, Any],
    ) -> list[SystemMessage | HumanMessage]:
        system_prompt = self._build_system_prompt()
        human_prompt = self._build_human_prompt(ai_context)

        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ]

    def _build_system_prompt(self) -> str:
        return (
            "你是一个中文股票研究助理，负责解释系统已经计算好的量化候选股票结果。\n"
            "你的任务是把候选评分、评分拆解、策略信号、数据质量、风险提示解释得更清楚。\n"
            "你不是投资顾问，不是交易员，不能自由推荐股票，不能绕过量化评分系统。\n"
            f"{self.INVESTMENT_SAFETY_RULES}\n"
            f"{self.EXPLANATION_QUALITY_RULES}\n"
            f"{self.JSON_OUTPUT_RULES}\n"
        )

    def _build_human_prompt(self, ai_context: dict[str, Any]) -> str:
        style = str(ai_context.get("explanation_style") or "balanced")
        return (
            "请根据下面的候选评分上下文，生成 AI 候选解释结果。\n\n"
            "你必须遵守以下要求：\n"
            "1. 只能基于输入中的候选评分结果解释，不能编造新闻、财报、公告或外部信息。\n"
            "2. 不能改变每只股票的 score、grade、rank。\n"
            "3. 不能输出直接买卖指令，只能输出研究线索和风险提醒。\n"
            "4. 如果某只股票评分高，也要说明它仍然存在风险。\n"
            "5. 如果策略信号为 buy，只能解释为规则偏积极，不能写成买入建议。\n"
            "6. 如果数据质量存在 warnings 或 errors，必须在风险中体现。\n"
            "7. 输出必须是严格 JSON，并符合给定字段结构。\n\n"
            "8. 如果 comparison_context 不为空，comparisons 必须基于 comparison_context 中的事实生成。\n"
            "9. 对比候选时要优先比较 score、grade、趋势分、动量分、风险分、策略信号和数据质量，不要编造外部理由。\n\n"
            "10. candidate_explanations.explanation 要用自然中文解释，不要只罗列字段名。\n"
            "11. key_strengths 要写成用户能理解的优势，不要只写 trend_score、macd_score 这类字段名。\n"
            "12. key_risks 要明确风险来源，例如数据质量、波动、策略信号不确定、评分边界。\n"
            "13. research_focus 要写成后续研究动作，例如继续观察趋势、核对数据质量、比较风险偏好。\n"
            "14. research_priorities 是研究顺序，不是买入顺序。\n\n"
            f"{self._build_style_instruction(style)}\n\n"
            f"{self._build_output_format_instruction()}\n\n"
            "候选评分上下文如下：\n"
            f"{json.dumps(ai_context, ensure_ascii=False)}"
        )

    def _build_style_instruction(self, style: str) -> str:
        if style == "concise":
            return (
                "解释风格：简洁。\n"
                "summary 控制在 150 字以内；"
                "每只候选 explanation 控制在 180 字以内；"
                "每个列表字段尽量 2 到 3 条。"
            )

        if style == "detailed":
            return (
                "解释风格：详细。\n"
                "summary 可以更完整；"
                "每只候选 explanation 可以详细解释评分来源、优势、风险和研究重点；"
                "每个列表字段可以 3 到 5 条。"
            )

        return (
            "解释风格：均衡。\n"
            "summary 控制在 300 字以内；"
            "每只候选 explanation 控制在 300 字以内；"
            "每个列表字段建议 3 条左右。"
        )

    def _build_output_format_instruction(self) -> str:
        return (
            "输出 JSON 格式必须如下：\n"
            "{\n"
            '  "summary": "总体中文总结",\n'
            '  "candidate_explanations": [\n'
            "    {\n"
            '      "symbol": "股票代码，必须与输入一致",\n'
            '      "market": "市场，必须与输入一致",\n'
            '      "name": "股票名称，没有则为 null",\n'
            '      "rank": 1,\n'
            '      "score": 90,\n'
            '      "grade": "A",\n'
            '      "explanation": "这只候选的中文解释",\n'
            '      "key_strengths": ["主要优势"],\n'
            '      "key_risks": ["主要风险"],\n'
            '      "research_focus": ["后续研究重点"]\n'
            "    }\n"
            "  ],\n"
            '  "comparisons": [\n'
            "    {\n"
            '      "symbol": "股票代码",\n'
            '      "market": "市场",\n'
            '      "compared_with": ["其他股票代码"],\n'
            '      "relative_strengths": ["相对优势"],\n'
            '      "relative_weaknesses": ["相对劣势"],\n'
            '      "comparison_summary": "候选之间的对比总结"\n'
            "    }\n"
            "  ],\n"
            '  "research_priorities": [\n'
            "    {\n"
            '      "priority_rank": 1,\n'
            '      "priority_level": "high",\n'
            '      "symbol": "股票代码",\n'
            '      "market": "市场",\n'
            '      "grade": "A",\n'
            '      "score": 90,\n'
            '      "reason": "为什么优先研究",\n'
            '      "suggested_next_steps": ["下一步研究动作"]\n'
            "    }\n"
            "  ],\n"
            '  "risk_summary": {\n'
            '    "overall_risk_level": "medium",\n'
            '    "summary": "总体风险总结",\n'
            '    "key_risks": ["关键风险"],\n'
            '    "risk_controls": ["研究过程中的风控提醒"]\n'
            "  },\n"
            '  "warnings": ["必要的风险提示"]\n'
            "}\n"
            "priority_level 和 overall_risk_level 只能使用 high、medium、low。\n"
            "所有 explanation、summary、comparison_summary、reason 都要使用自然中文，"
            "避免只复述字段名或分数。"
        )

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

        self._validate_ai_response_against_source(
            response=response,
            candidate_result=candidate_result,
        )
        self._validate_ai_response_safety(response)

        return response

    def _validate_ai_response_against_source(
        self,
        *,
        response: StockCandidateAIExplanationResponse,
        candidate_result: StockCandidateResponse,
    ) -> None:
        source_map = self._build_source_candidate_map(candidate_result)

        for item in response.candidate_explanations:
            source = source_map.get((item.symbol.upper(), str(item.market).upper()))
            if source is None:
                raise ValueError(
                    f"AI response contains unknown candidate: {item.symbol}/{item.market}"
                )

            self._validate_candidate_identity(
                symbol=item.symbol,
                market=str(item.market),
                score=item.score,
                grade=item.grade,
                rank=item.rank,
                source=source,
            )

        for item in response.research_priorities:
            source = source_map.get((item.symbol.upper(), str(item.market).upper()))
            if source is None:
                raise ValueError(
                    f"AI research priority contains unknown candidate: {item.symbol}/{item.market}"
                )

            self._validate_candidate_identity(
                symbol=item.symbol,
                market=str(item.market),
                score=item.score,
                grade=item.grade,
                rank=None,
                source=source,
            )

        for item in response.comparisons:
            source = source_map.get((item.symbol.upper(), str(item.market).upper()))
            if source is None:
                raise ValueError(
                    f"AI comparison contains unknown candidate: {item.symbol}/{item.market}"
                )

    def _build_source_candidate_map(
        self,
        candidate_result: StockCandidateResponse,
    ) -> dict[tuple[str, str], StockCandidateItem]:
        return {
            (candidate.symbol.upper(), str(candidate.market).upper()): candidate
            for candidate in candidate_result.candidates
        }

    def _validate_candidate_identity(
        self,
        *,
        symbol: str,
        market: str,
        score: int,
        grade: str,
        rank: int | None,
        source: StockCandidateItem,
    ) -> None:
        if score != source.score:
            raise ValueError(
                f"AI response changed score for {symbol}/{market}: {score} != {source.score}"
            )

        if grade != source.grade:
            raise ValueError(
                f"AI response changed grade for {symbol}/{market}: {grade} != {source.grade}"
            )

        if rank is not None and source.rank is not None and rank != source.rank:
            raise ValueError(
                f"AI response changed rank for {symbol}/{market}: {rank} != {source.rank}"
            )

    def _validate_ai_response_safety(
        self,
        response: StockCandidateAIExplanationResponse,
    ) -> None:
        for text in self._iter_ai_response_texts(response):
            forbidden_phrase = self._find_forbidden_phrase(text)
            if forbidden_phrase is not None:
                raise ValueError(
                    f"AI response contains forbidden investment phrase: {forbidden_phrase}"
                )

    def _iter_ai_response_texts(
        self,
        response: StockCandidateAIExplanationResponse,
    ) -> list[str]:
        values: list[str] = [
            response.summary,
            *response.warnings,
        ]

        for item in response.candidate_explanations:
            values.append(item.explanation)
            values.extend(item.key_strengths)
            values.extend(item.key_risks)
            values.extend(item.research_focus)

        for item in response.comparisons:
            values.append(item.comparison_summary)
            values.extend(item.relative_strengths)
            values.extend(item.relative_weaknesses)

        for item in response.research_priorities:
            values.append(item.reason)
            values.extend(item.suggested_next_steps)

        if response.risk_summary is not None:
            values.append(response.risk_summary.summary)
            values.extend(response.risk_summary.key_risks)
            values.extend(response.risk_summary.risk_controls)

        return [
            value
            for value in values
            if isinstance(value, str) and value.strip()
        ]

    def _find_forbidden_phrase(self, text: str) -> str | None:
        normalized = text.strip()
        for phrase in self.FORBIDDEN_INVESTMENT_PHRASES:
            if phrase in normalized:
                return phrase

        return None

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
            "explanation_guidance": self._build_explanation_guidance(request),
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
            "comparison_context": (
                self._build_comparison_context(candidates)
                if request.include_comparison
                else []
            ),
            "warnings": self._trim_text_list(
                candidate_result.warnings,
                limit=self.MAX_WARNINGS,
            ),
            "disclaimer": candidate_result.disclaimer,
        }

    def _build_explanation_guidance(
        self,
        request: StockCandidateAIExplanationRequest,
    ) -> dict[str, Any]:
        return {
            "audience": "中文股票研究用户，新手也需要能看懂。",
            "tone": "谨慎、清楚、像研究助理，不像销售话术。",
            "must_explain": [
                "为什么该候选进入列表",
                "主要分数来自哪些维度",
                "和其他候选相比有什么差异",
                "当前最需要确认的风险是什么",
                "下一步研究可以看什么",
            ],
            "must_avoid": [
                "不要说必须买入",
                "不要承诺收益",
                "不要编造新闻、财报或公告",
                "不要把研究优先级写成买入顺序",
                "不要改变 score、grade、rank",
            ],
            "style": request.explanation_style,
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

    def _build_comparison_context(
        self,
        candidates: list[StockCandidateItem],
    ) -> list[dict[str, Any]]:
        if len(candidates) <= 1:
            return []

        sorted_candidates = sorted(
            candidates,
            key=lambda item: (
                item.rank if item.rank is not None else 999999,
                -item.score,
                item.symbol,
            ),
        )
        best_candidate = sorted_candidates[0]
        result: list[dict[str, Any]] = []

        for index, candidate in enumerate(sorted_candidates, start=1):
            other_candidates = [
                item
                for item in sorted_candidates
                if item.symbol != candidate.symbol or item.market != candidate.market
            ]

            result.append(
                {
                    "symbol": candidate.symbol,
                    "market": candidate.market,
                    "name": candidate.name,
                    "group_rank": index,
                    "score": candidate.score,
                    "grade": candidate.grade,
                    "score_gap_to_best": best_candidate.score - candidate.score,
                    "compared_with": [
                        item.symbol
                        for item in other_candidates[: self.MAX_COMPARISON_ITEMS]
                    ],
                    "dimension_scores": self._build_dimension_score_context(candidate),
                    "strategy_signal": (
                        self._build_strategy_signal_context(candidate.strategy_signal)
                        if candidate.strategy_signal
                        else None
                    ),
                    "data_quality": (
                        self._build_data_quality_context(candidate.data_quality)
                        if candidate.data_quality
                        else None
                    ),
                    "relative_strengths": self._build_relative_strengths(
                        candidate=candidate,
                        peers=other_candidates,
                    ),
                    "relative_weaknesses": self._build_relative_weaknesses(
                        candidate=candidate,
                        peers=other_candidates,
                    ),
                }
            )

            if len(result) >= self.MAX_COMPARISON_ITEMS:
                break

        return result

    def _build_dimension_score_context(
        self,
        candidate: StockCandidateItem,
    ) -> dict[str, int | None]:
        breakdown = candidate.score_breakdown
        if breakdown is None:
            return {
                "trend_score": None,
                "momentum_score": None,
                "rsi_score": None,
                "macd_score": None,
                "volatility_score": None,
                "volume_score": None,
                "liquidity_score": None,
                "strategy_signal_score": None,
                "risk_score": None,
                "user_preference_score": None,
            }

        return {
            "trend_score": breakdown.trend_score,
            "momentum_score": breakdown.momentum_score,
            "rsi_score": breakdown.rsi_score,
            "macd_score": breakdown.macd_score,
            "volatility_score": breakdown.volatility_score,
            "volume_score": breakdown.volume_score,
            "liquidity_score": breakdown.liquidity_score,
            "strategy_signal_score": breakdown.strategy_signal_score,
            "risk_score": breakdown.risk_score,
            "user_preference_score": breakdown.user_preference_score,
        }

    def _build_relative_strengths(
        self,
        *,
        candidate: StockCandidateItem,
        peers: list[StockCandidateItem],
    ) -> list[str]:
        strengths: list[str] = []

        if not peers:
            return self._trim_text_list(candidate.reasons, limit=3)

        best_peer_score = max(peer.score for peer in peers)
        if candidate.score >= best_peer_score + self.SCORE_DIFF_THRESHOLD:
            strengths.append(
                f"综合评分比其他候选高至少 {self.SCORE_DIFF_THRESHOLD} 分。"
            )

        breakdown = candidate.score_breakdown
        if breakdown is not None:
            strengths.extend(
                self._build_dimension_advantages(
                    candidate_breakdown=breakdown,
                    peers=peers,
                )
            )

        if candidate.strategy_signal is not None:
            signal = candidate.strategy_signal.signal
            strength = candidate.strategy_signal.strength
            if signal == "buy":
                strengths.append(f"策略信号为 buy，强度为 {strength}，相对更积极。")
            elif signal == "hold":
                strengths.append("策略信号为 hold，相比弱势信号更偏稳健。")

        if candidate.data_quality is not None and candidate.data_quality.is_enough:
            strengths.append(
                f"数据质量满足要求，K 线数量为 {candidate.data_quality.candle_count}。"
            )

        if not strengths:
            strengths.extend(candidate.reasons)

        return self._trim_text_list(strengths, limit=5)

    def _build_relative_weaknesses(
        self,
        *,
        candidate: StockCandidateItem,
        peers: list[StockCandidateItem],
    ) -> list[str]:
        weaknesses: list[str] = []

        if not peers:
            return self._trim_text_list(candidate.risks, limit=3)

        best_peer_score = max(peer.score for peer in peers)
        if best_peer_score >= candidate.score + self.SCORE_DIFF_THRESHOLD:
            weaknesses.append(
                f"综合评分比最高候选低 {best_peer_score - candidate.score} 分。"
            )

        breakdown = candidate.score_breakdown
        if breakdown is not None:
            weaknesses.extend(
                self._build_dimension_disadvantages(
                    candidate_breakdown=breakdown,
                    peers=peers,
                )
            )

        if candidate.strategy_signal is not None:
            signal = candidate.strategy_signal.signal
            if signal == "sell":
                weaknesses.append("策略信号为 sell，相比其他候选更需要谨慎。")
            elif signal == "observe":
                weaknesses.append("策略信号为 observe，方向确认度相对不足。")

        if candidate.data_quality is not None:
            if candidate.data_quality.is_stale:
                weaknesses.append("数据存在过旧风险，对比时需要降低解释置信度。")
            if not candidate.data_quality.is_enough:
                weaknesses.append("K 线数量不足，数据基础弱于数据充足的候选。")
            if candidate.data_quality.warnings:
                weaknesses.extend(candidate.data_quality.warnings[:2])

        if not weaknesses:
            weaknesses.extend(candidate.risks)

        return self._trim_text_list(weaknesses, limit=5)

    def _build_dimension_advantages(
        self,
        *,
        candidate_breakdown: StockCandidateScoreBreakdown,
        peers: list[StockCandidateItem],
    ) -> list[str]:
        advantages: list[str] = []
        dimension_names = self._get_comparison_dimension_names()

        for field_name, display_name in dimension_names.items():
            candidate_value = getattr(candidate_breakdown, field_name)
            peer_values = [
                getattr(peer.score_breakdown, field_name)
                for peer in peers
                if peer.score_breakdown is not None
            ]
            if not peer_values:
                continue

            peer_best = max(peer_values)
            if candidate_value >= peer_best + self.SCORE_DIFF_THRESHOLD:
                advantages.append(
                    f"{display_name}明显更强，当前为 {candidate_value}，对比候选最高为 {peer_best}。"
                )

        return advantages[:3]

    def _build_dimension_disadvantages(
        self,
        *,
        candidate_breakdown: StockCandidateScoreBreakdown,
        peers: list[StockCandidateItem],
    ) -> list[str]:
        disadvantages: list[str] = []
        dimension_names = self._get_comparison_dimension_names()

        for field_name, display_name in dimension_names.items():
            candidate_value = getattr(candidate_breakdown, field_name)
            peer_values = [
                getattr(peer.score_breakdown, field_name)
                for peer in peers
                if peer.score_breakdown is not None
            ]
            if not peer_values:
                continue

            peer_best = max(peer_values)
            if peer_best >= candidate_value + self.SCORE_DIFF_THRESHOLD:
                disadvantages.append(
                    f"{display_name}弱于对比候选，当前为 {candidate_value}，对比候选最高为 {peer_best}。"
                )

        return disadvantages[:3]

    def _get_comparison_dimension_names(self) -> dict[str, str]:
        return {
            "trend_score": "趋势分",
            "momentum_score": "动量分",
            "rsi_score": "RSI 分",
            "macd_score": "MACD 分",
            "volatility_score": "波动率分",
            "volume_score": "成交量分",
            "liquidity_score": "流动性分",
            "strategy_signal_score": "策略信号分",
            "risk_score": "综合风险分",
            "user_preference_score": "用户偏好分",
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

    async def _check_candidate_ai_quota(
        self,
        *,
        user_id: int,
        messages: list[SystemMessage | HumanMessage],
    ) -> tuple[bool, str | None, AIUsageTokenEstimate, AIUsageCostEstimate]:
        token_service = AIUsageTokenService()
        settings = get_settings()

        prompt_estimate = token_service.estimate_prompt_tokens_from_messages(messages)
        estimated_tokens = AIUsageTokenEstimate(
            prompt_tokens=prompt_estimate.prompt_tokens,
            completion_tokens=CANDIDATE_AI_EXPLANATION_ESTIMATED_COMPLETION_TOKENS,
            total_tokens=(
                prompt_estimate.prompt_tokens
                + CANDIDATE_AI_EXPLANATION_ESTIMATED_COMPLETION_TOKENS
            ),
            token_source="estimated",
        )
        estimated_cost = token_service.estimate_cost(
            model_name=settings.llm_model,
            prompt_tokens=estimated_tokens.prompt_tokens,
            completion_tokens=estimated_tokens.completion_tokens,
        )

        async with AsyncSessionLocal() as db:
            repo = AsyncAIUsageRepository(db)
            quota_service = AIQuotaService(repo)

            result = await quota_service.check_quota(
                AIQuotaCheckRequest(
                    user_id=user_id,
                    feature=CANDIDATE_AI_EXPLANATION_FEATURE,
                    provider="deepseek",
                    model_name=settings.llm_model,
                    estimated_prompt_tokens=estimated_tokens.prompt_tokens,
                    estimated_completion_tokens=estimated_tokens.completion_tokens,
                    estimated_total_tokens=estimated_tokens.total_tokens,
                    estimated_cost=estimated_cost.estimated_cost,
                    currency=estimated_cost.currency,
                )
            )

        return result.allowed, result.reason, estimated_tokens, estimated_cost

    async def _record_candidate_ai_success(
        self,
        *,
        user_id: int,
        request: StockCandidateAIExplanationRequest,
        candidate_result: StockCandidateResponse,
        response: Any,
        messages: list[SystemMessage | HumanMessage],
        completion_text: str,
        started_at: datetime,
    ):
        try:
            async with AsyncSessionLocal() as db:
                repo = AsyncAIUsageRepository(db)
                usage_service = AIUsageService(repo)

                return await usage_service.record_success(
                    user_id=user_id,
                    feature=CANDIDATE_AI_EXPLANATION_FEATURE,
                    model_name=get_settings().llm_model,
                    response=response,
                    prompt_messages=messages,
                    completion_text=completion_text,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    extra=self._build_ai_usage_extra(
                        request=request,
                        candidate_result=candidate_result,
                    ),
                )
        except Exception:
            logger.exception("record stock candidate ai explanation success usage failed")
            return None

    async def _record_candidate_ai_failed(
        self,
        *,
        user_id: int,
        request: StockCandidateAIExplanationRequest,
        candidate_result: StockCandidateResponse,
        response: Any | None,
        messages: list[SystemMessage | HumanMessage],
        completion_text: str,
        error_message: str,
        started_at: datetime,
    ) -> None:
        try:
            async with AsyncSessionLocal() as db:
                repo = AsyncAIUsageRepository(db)
                usage_service = AIUsageService(repo)

                await usage_service.record_failed(
                    user_id=user_id,
                    feature=CANDIDATE_AI_EXPLANATION_FEATURE,
                    model_name=get_settings().llm_model,
                    error_message=error_message,
                    response=response,
                    prompt_messages=messages,
                    completion_text=completion_text,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    extra=self._build_ai_usage_extra(
                        request=request,
                        candidate_result=candidate_result,
                    ),
                )
        except Exception:
            logger.exception("record stock candidate ai explanation failed usage failed")

    async def _record_candidate_ai_blocked(
        self,
        *,
        user_id: int,
        request: StockCandidateAIExplanationRequest,
        candidate_result: StockCandidateResponse,
        reason: str,
        estimated_tokens: AIUsageTokenEstimate,
        estimated_cost: AIUsageCostEstimate,
    ) -> None:
        try:
            async with AsyncSessionLocal() as db:
                repo = AsyncAIUsageRepository(db)
                usage_service = AIUsageService(repo)

                await usage_service.record_blocked(
                    user_id=user_id,
                    feature=CANDIDATE_AI_EXPLANATION_FEATURE,
                    model_name=get_settings().llm_model,
                    reason=reason,
                    estimated_prompt_tokens=estimated_tokens.prompt_tokens,
                    estimated_completion_tokens=estimated_tokens.completion_tokens,
                    estimated_cost=estimated_cost.estimated_cost,
                    extra=self._build_ai_usage_extra(
                        request=request,
                        candidate_result=candidate_result,
                    ),
                )
        except Exception:
            logger.exception("record stock candidate ai explanation blocked usage failed")

    def _build_ai_usage_extra(
        self,
        *,
        request: StockCandidateAIExplanationRequest,
        candidate_result: StockCandidateResponse,
    ) -> dict[str, Any]:
        return {
            "source": "stock_candidate_ai_explanation",
            "universe_source": request.candidate_request.universe_source,
            "requested_top_n": request.candidate_request.top_n,
            "max_candidates_to_explain": request.max_candidates_to_explain,
            "candidate_count": len(candidate_result.candidates),
            "excluded_count": len(candidate_result.excluded),
            "explanation_style": request.explanation_style,
            "include_comparison": request.include_comparison,
            "include_research_priority": request.include_research_priority,
            "include_risk_summary": request.include_risk_summary,
        }

    def _build_quota_blocked_response(
        self,
        *,
        request: StockCandidateAIExplanationRequest,
        candidate_result: StockCandidateResponse,
        candidates: list[StockCandidateItem],
        input_snapshot: StockCandidateAIExplanationInputSnapshot,
        quota_reason: str,
    ) -> StockCandidateAIExplanationResponse:
        fallback_reason = (
            "当前 AI 候选解释额度不足，系统没有继续调用 DeepSeek。"
            f"额度原因：{quota_reason}。"
        )

        if request.allow_fallback:
            return self._build_fallback_response(
                request=request,
                candidate_result=candidate_result,
                candidates=candidates,
                input_snapshot=input_snapshot,
                unavailable_reason="ai_quota_exceeded",
                fallback_reason=fallback_reason,
            )

        return self._build_unavailable_response(
            request=request,
            candidate_result=candidate_result,
            input_snapshot=input_snapshot,
            unavailable_reason="ai_quota_exceeded",
            fallback_reason=fallback_reason,
        )

    def _build_exception_response(
        self,
        *,
        request: StockCandidateAIExplanationRequest,
        candidate_result: StockCandidateResponse,
        candidates: list[StockCandidateItem],
        input_snapshot: StockCandidateAIExplanationInputSnapshot,
        unavailable_reason: StockCandidateAIExplanationUnavailableReason,
        exc: Exception,
    ) -> StockCandidateAIExplanationResponse:
        fallback_reason = self._safe_exception_message(exc)

        if request.allow_fallback:
            return self._build_fallback_response(
                request=request,
                candidate_result=candidate_result,
                candidates=candidates,
                input_snapshot=input_snapshot,
                unavailable_reason=unavailable_reason,
                fallback_reason=fallback_reason,
            )

        return self._build_unavailable_response(
            request=request,
            candidate_result=candidate_result,
            input_snapshot=input_snapshot,
            unavailable_reason=unavailable_reason,
            fallback_reason=fallback_reason,
        )

    def _resolve_llm_error_reason(
        self,
        exc: Exception,
    ) -> StockCandidateAIExplanationUnavailableReason:
        if isinstance(exc, BadRequestException):
            message = str(getattr(exc, "message", exc)).lower()
            if "missing deepseek_api_key" in message or "missing" in message:
                return "llm_unavailable"

        return "llm_error"

    def _build_fallback_response(
        self,
        *,
        request: StockCandidateAIExplanationRequest,
        candidate_result: StockCandidateResponse,
        candidates: list[StockCandidateItem],
        input_snapshot: StockCandidateAIExplanationInputSnapshot,
        unavailable_reason: StockCandidateAIExplanationUnavailableReason,
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
            unavailable_reason=unavailable_reason,
            ai_used=False,
            fallback_reason=fallback_reason,
            summary=(
                "AI 候选解释暂时不可用，系统已基于确定性候选评分结果生成降级解释。"
            ),
            candidate_explanations=explanations,
            comparisons=(
                self._build_fallback_comparisons(candidates)
                if request.include_comparison
                else []
            ),
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

    def _build_candidate_plain_summary(
        self,
        candidate: StockCandidateItem,
    ) -> str:
        signal_text = "策略信号暂不可用"
        if candidate.strategy_signal is not None and candidate.strategy_signal.signal:
            signal_text = (
                f"策略信号为 {candidate.strategy_signal.signal}"
                f"，强度为 {candidate.strategy_signal.strength or '未知'}"
            )

        data_quality_text = "数据质量信息暂不可用"
        if candidate.data_quality is not None:
            if candidate.data_quality.is_enough and not candidate.data_quality.is_stale:
                data_quality_text = (
                    f"数据质量满足基本要求，K 线数量为 {candidate.data_quality.candle_count}"
                )
            elif candidate.data_quality.is_stale:
                data_quality_text = "数据存在过旧风险"
            elif not candidate.data_quality.is_enough:
                data_quality_text = "K 线数量不足，数据基础需要谨慎"

        return (
            f"{candidate.symbol} 当前排名第 {candidate.rank or '-'}，"
            f"评分 {candidate.score}，等级 {candidate.grade}。"
            f"{signal_text}，{data_quality_text}。"
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
                f"{self._build_candidate_plain_summary(candidate)}"
                "该解释基于系统确定性评分规则生成，未使用 AI 扩展分析；"
                "适合作为后续研究线索，而不是直接买卖依据。"
            ),
            key_strengths=strengths,
            key_risks=risks,
            research_focus=self._build_fallback_research_focus(candidate),
        )

    def _build_fallback_research_focus(
        self,
        candidate: StockCandidateItem,
    ) -> list[str]:
        focus = [
            "查看主要加分维度是否具有持续性。",
            "确认主要风险项是否可以接受。",
            "结合自身风险偏好继续研究。",
        ]

        if candidate.strategy_signal is not None:
            focus.append("继续观察策略信号是否保持稳定。")

        if candidate.data_quality is not None:
            focus.append("核对数据质量、K 线数量和是否存在过旧风险。")

        if candidate.score_breakdown is not None:
            focus.append("重点查看趋势、动量、风险和策略信号分的变化。")

        return self._trim_text_list(focus, limit=5)

    def _build_fallback_comparisons(
        self,
        candidates: list[StockCandidateItem],
    ) -> list[StockCandidateAIComparisonItem]:
        if len(candidates) <= 1:
            return []

        sorted_candidates = sorted(
            candidates,
            key=lambda item: (
                item.rank if item.rank is not None else 999999,
                -item.score,
                item.symbol,
            ),
        )
        comparisons: list[StockCandidateAIComparisonItem] = []

        for candidate in sorted_candidates:
            peers = [
                item
                for item in sorted_candidates
                if item.symbol != candidate.symbol or item.market != candidate.market
            ]
            relative_strengths = self._build_relative_strengths(
                candidate=candidate,
                peers=peers,
            )
            relative_weaknesses = self._build_relative_weaknesses(
                candidate=candidate,
                peers=peers,
            )

            comparisons.append(
                StockCandidateAIComparisonItem(
                    symbol=candidate.symbol,
                    market=candidate.market,
                    compared_with=[item.symbol for item in peers],
                    relative_strengths=relative_strengths,
                    relative_weaknesses=relative_weaknesses,
                    comparison_summary=(
                        f"{candidate.symbol} 当前评分 {candidate.score}，等级 {candidate.grade}。"
                        "相对优势和劣势来自候选之间的评分维度、策略信号和数据质量对比；"
                        "该对比用于辅助研究，不构成投资建议。"
                    ),
                )
            )

        return comparisons[: self.MAX_COMPARISON_ITEMS]

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
                f"评分 {candidate.score}，等级 {candidate.grade}。"
                "该优先级来自确定性候选评分排序，表示它更适合优先研究，"
                "不代表应当直接买入。"
            ),
            suggested_next_steps=[
                "查看评分拆解中的主要加分和扣分项。",
                "结合策略信号和数据质量继续判断。",
                "如果后续用于模拟交易，需要先设置资金和风控边界。",
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
                "当前风险摘要由确定性候选评分结果生成。候选评分较高只能说明它在当前规则体系下更值得研究，"
                "不代表未来收益确定。仍需要关注市场波动、数据质量、策略信号失效、"
                "评分公式适用边界和个人风险承受能力。"
            ),
            key_risks=self._trim_text_list(risk_items, limit=8),
            risk_controls=[
                "不要把候选评分直接等同于买入建议。",
                "不要只看单一分数，应同时查看主要加分项、扣分项和数据质量。",
                "如果后续进入回测、模拟交易或真实研究，应先设定资金比例和风控边界。",
            ],
        )

    def _build_unavailable_response(
        self,
        *,
        request: StockCandidateAIExplanationRequest,
        candidate_result: StockCandidateResponse,
        input_snapshot: StockCandidateAIExplanationInputSnapshot,
        unavailable_reason: StockCandidateAIExplanationUnavailableReason,
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

        if isinstance(exc, BadRequestException):
            message = str(getattr(exc, "message", exc)).strip()
            if "missing DEEPSEEK_API_KEY" in message:
                return "DeepSeek API Key 未配置，AI 候选解释暂时不可用。"
            return message[:300] if message else "AI 候选解释请求参数不可用。"

        message = str(exc).strip()
        if not message:
            return "AI 候选解释调用失败。"

        if "AI response is not valid JSON" in message:
            return "AI 输出不是合法 JSON，已使用降级解释。"

        if "AI response candidate_explanations is empty" in message:
            return "AI 输出中缺少候选解释明细，已使用降级解释。"

        if "forbidden investment phrase" in message:
            return "AI 输出包含不符合安全边界的投资表述，已使用降级解释。"

        if "changed score" in message or "changed grade" in message or "changed rank" in message:
            return "AI 输出修改了候选评分、等级或排名，已使用降级解释。"

        return message[:300]