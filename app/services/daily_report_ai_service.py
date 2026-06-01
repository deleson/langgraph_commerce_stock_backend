from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.core.llm import get_chat_model
from app.schemas.daily_report import (
    DailyReportAIStatus,
    DailyReportCreate,
    DailyReportSection,
    DailyReportStatus,
)


@dataclass(slots=True)
class DailyReportAIResult:
    report: DailyReportCreate
    messages: list[BaseMessage]
    raw_content: str = ""
    response: Any | None = None
    ai_status: DailyReportAIStatus = DailyReportAIStatus.NOT_USED
    error_message: str | None = None


class DailyReportAIService:
    """Generate an AI-polished daily report from deterministic report data.

    This service does not collect market data, does not check quota,
    and does not write database rows. It only calls the LLM and returns
    an updated DailyReportCreate object.
    """

    MAX_SECTION_COUNT = 10
    MAX_STOCK_SNAPSHOT_COUNT = 30
    MAX_WARNING_COUNT = 10

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

    JSON_OUTPUT_RULES = (
        "你必须只输出一个合法 JSON 对象，不要输出 Markdown，不要输出代码块，"
        "不要在 JSON 前后添加解释文字。所有自然语言内容必须使用简体中文。"
    )

    INVESTMENT_SAFETY_RULES = (
        "你不能输出买入、卖出、满仓、稳赚、保证收益、一定上涨等直接投资建议或收益承诺。"
        "你只能说研究线索、观察重点、风险提示、需要进一步确认。"
        "你不能修改输入中的股票、价格、策略信号、候选评分、等级、用户画像和相似记忆事实。"
    )

    OUTPUT_FORMAT = {
        "summary": "一段每日简报总摘要，最多 800 字",
        "section_summaries": {
            "overview": "今日概览摘要",
            "market_movement": "行情变化摘要",
            "technical_status": "技术状态摘要",
            "strategy_signal": "策略信号摘要",
            "candidate_priority": "候选研究优先级摘要",
            "risk_warning": "风险提示摘要",
            "personalized_note": "个性化提示摘要",
        },
        "warnings": ["AI 认为需要额外强调的风险提示，最多 5 条"],
    }

    async def enhance_report(
        self,
        report: DailyReportCreate,
    ) -> DailyReportAIResult:
        if report.status == DailyReportStatus.FAILED:
            return DailyReportAIResult(
                report=report,
                messages=[],
                ai_status=DailyReportAIStatus.NOT_USED,
                error_message="failed deterministic report should not call ai",
            )

        ai_context = self._build_ai_context(report)
        messages = self._build_messages(ai_context)

        try:
            llm = get_chat_model()
            response = await llm.ainvoke(messages)
            raw_content = str(response.content).strip()

            payload = self._parse_ai_content(raw_content)
            self._validate_ai_payload(payload)

            enhanced_report = self._apply_ai_payload(
                report=report,
                payload=payload,
            )

            return DailyReportAIResult(
                report=enhanced_report,
                messages=messages,
                raw_content=raw_content,
                response=response,
                ai_status=DailyReportAIStatus.SUCCESS,
            )
        except json.JSONDecodeError as exc:
            return self._build_fallback_result(
                report=report,
                messages=messages,
                raw_content=locals().get("raw_content", ""),
                response=locals().get("response", None),
                ai_status=DailyReportAIStatus.PARSE_ERROR,
                error_message=self._safe_exception_message(exc),
            )
        except Exception as exc:
            return self._build_fallback_result(
                report=report,
                messages=messages,
                raw_content=locals().get("raw_content", ""),
                response=locals().get("response", None),
                ai_status=DailyReportAIStatus.LLM_ERROR,
                error_message=self._safe_exception_message(exc),
            )

    def _build_ai_context(
        self,
        report: DailyReportCreate,
    ) -> dict[str, Any]:
        return {
            "report_date": report.report_date.isoformat(),
            "deterministic_summary": report.summary,
            "sections": [
                {
                    "section_type": section.section_type,
                    "title": section.title,
                    "summary": section.summary,
                    "items": section.items[:10],
                    "warnings": section.warnings[:5],
                }
                for section in report.sections[: self.MAX_SECTION_COUNT]
            ],
            "stock_snapshots": [
                snapshot.model_dump(mode="json")
                for snapshot in report.stock_snapshots[: self.MAX_STOCK_SNAPSHOT_COUNT]
            ],
            "input_snapshot": (
                report.input_snapshot.model_dump(mode="json")
                if report.input_snapshot is not None
                else None
            ),
            "candidate_snapshot": self._trim_snapshot(report.candidate_snapshot),
            "strategy_signal_snapshot": self._trim_snapshot(
                report.strategy_signal_snapshot
            ),
            "profile_snapshot": self._trim_snapshot(report.profile_snapshot),
            "memory_snapshot": self._trim_snapshot(report.memory_snapshot),
            "warnings": report.warnings[: self.MAX_WARNING_COUNT],
            "disclaimer": report.disclaimer,
            "output_format": self.OUTPUT_FORMAT,
        }

    def _build_messages(
        self,
        ai_context: dict[str, Any],
    ) -> list[BaseMessage]:
        return [
            SystemMessage(content=self._build_system_prompt()),
            HumanMessage(content=self._build_human_prompt(ai_context)),
        ]

    def _build_system_prompt(self) -> str:
        return (
            "你是一个中文股票研究日报助手，负责把系统已经生成的确定性每日简报润色成更自然的中文日报。\n"
            "你的输入全部来自系统结构化数据，包括行情摘要、技术指标、策略信号、候选评分、用户画像和相似记忆。\n"
            "你不能编造外部新闻，不能补充输入中不存在的事实，不能修改任何分数、信号、价格和等级。\n"
            f"{self.INVESTMENT_SAFETY_RULES}\n"
            f"{self.JSON_OUTPUT_RULES}\n"
        )

    def _build_human_prompt(
        self,
        ai_context: dict[str, Any],
    ) -> str:
        return (
            "请根据下面的确定性每日简报上下文，生成 AI 润色后的每日简报 JSON。\n"
            "要求：\n"
            "1. summary 要像中文日报摘要，清楚说明整体情况、研究重点和风险。\n"
            "2. section_summaries 只能改写各板块摘要，不能修改板块 items 中的事实。\n"
            "3. warnings 只补充风险表达，不要输出买卖建议。\n"
            "4. 必须保留不构成投资建议的边界。\n\n"
            f"上下文 JSON：\n{json.dumps(ai_context, ensure_ascii=False)}"
        )

    def _parse_ai_content(
        self,
        raw_content: str,
    ) -> dict[str, Any]:
        content = raw_content.strip()

        if content.startswith("```"):
            content = content.strip("`").strip()
            if content.lower().startswith("json"):
                content = content[4:].strip()

        loaded = json.loads(content)
        if not isinstance(loaded, dict):
            raise ValueError("AI daily report response must be a JSON object")

        return loaded

    def _validate_ai_payload(
        self,
        payload: dict[str, Any],
    ) -> None:
        summary = payload.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("AI daily report summary is required")

        section_summaries = payload.get("section_summaries")
        if section_summaries is not None and not isinstance(section_summaries, dict):
            raise ValueError("section_summaries must be an object")

        warnings = payload.get("warnings")
        if warnings is not None and not isinstance(warnings, list):
            raise ValueError("warnings must be a list")

        forbidden = self._find_forbidden_phrase(payload)
        if forbidden is not None:
            raise ValueError(f"AI daily report contains forbidden phrase: {forbidden}")

    def _apply_ai_payload(
        self,
        *,
        report: DailyReportCreate,
        payload: dict[str, Any],
    ) -> DailyReportCreate:
        section_summaries = payload.get("section_summaries") or {}
        warnings = self._normalize_text_list(payload.get("warnings") or [], limit=5)

        return report.model_copy(
            update={
                "summary": str(payload["summary"]).strip()[:4000],
                "sections": self._apply_section_summaries(
                    sections=report.sections,
                    section_summaries=section_summaries,
                ),
                "warnings": self._merge_warnings(report.warnings, warnings),
                "ai_used": True,
                "ai_status": DailyReportAIStatus.SUCCESS,
                "status": DailyReportStatus.GENERATED,
                "disclaimer": report.disclaimer,
            }
        )

    def _apply_section_summaries(
        self,
        *,
        sections: list[DailyReportSection],
        section_summaries: dict[str, Any],
    ) -> list[DailyReportSection]:
        updated_sections: list[DailyReportSection] = []

        for section in sections:
            section_key = str(section.section_type)
            ai_summary = section_summaries.get(section_key)

            if isinstance(ai_summary, str) and ai_summary.strip():
                updated_sections.append(
                    section.model_copy(
                        update={"summary": ai_summary.strip()[:2000]}
                    )
                )
            else:
                updated_sections.append(section)

        return updated_sections

    def _build_fallback_result(
        self,
        *,
        report: DailyReportCreate,
        messages: list[BaseMessage],
        raw_content: str,
        response: Any | None,
        ai_status: DailyReportAIStatus,
        error_message: str,
    ) -> DailyReportAIResult:
        fallback_report = report.model_copy(
            update={
                "status": (
                    DailyReportStatus.FALLBACK
                    if report.status == DailyReportStatus.GENERATED
                    else report.status
                ),
                "ai_used": False,
                "ai_status": ai_status,
                "warnings": self._merge_warnings(
                    report.warnings,
                    [f"AI 每日简报生成失败，已降级使用确定性简报：{error_message}"],
                ),
            }
        )

        return DailyReportAIResult(
            report=fallback_report,
            messages=messages,
            raw_content=raw_content,
            response=response,
            ai_status=ai_status,
            error_message=error_message,
        )

    def _trim_snapshot(
        self,
        payload: dict[str, Any],
        *,
        max_items: int = 10,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}

        trimmed: dict[str, Any] = {}

        for key, value in payload.items():
            if isinstance(value, list):
                trimmed[key] = value[:max_items]
            else:
                trimmed[key] = value

        return trimmed

    def _merge_warnings(
        self,
        original: list[str],
        extra: list[str],
    ) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()

        for item in [*original, *extra]:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)

        return merged[: self.MAX_WARNING_COUNT]

    def _normalize_text_list(
        self,
        values: list[Any],
        *,
        limit: int,
    ) -> list[str]:
        results: list[str] = []

        for value in values:
            text = str(value).strip()
            if not text:
                continue
            results.append(text[:300])

            if len(results) >= limit:
                break

        return results

    def _find_forbidden_phrase(
        self,
        payload: dict[str, Any],
    ) -> str | None:
        text = json.dumps(payload, ensure_ascii=False)

        for phrase in self.FORBIDDEN_INVESTMENT_PHRASES:
            if phrase in text:
                return phrase

        return None

    def _safe_exception_message(
        self,
        exc: Exception,
    ) -> str:
        message = str(exc).strip()
        return message[:300] if message else exc.__class__.__name__