from __future__ import annotations

"""每日简报确定性生成服务。

本文件不调用 LLM，只根据 DailyReportDataContext 中已经收集好的数据，
生成日报 summary、sections、股票快照、风险提示和免责声明。

这里生成的是“确定性日报骨架”，AI 润色只能在这个结果上改写表达，
不能修改价格、信号、评分和风险事实。
"""

from decimal import Decimal
from typing import Any

from app.schemas.daily_report import (
    DailyReportAIStatus,
    DailyReportCreate,
    DailyReportSection,
    DailyReportSectionType,
    DailyReportStatus,
    DailyReportStockSnapshot,
    DailyReportUnavailableReason,
)
from app.services.daily_report_data_service import (
    DailyReportDataContext,
    DailyReportStockDataItem,
)


class DailyReportService:
    """根据日报上下文生成确定性日报内容。"""

    DISCLAIMER = (
        "本每日简报仅基于历史行情、技术指标、策略信号和用户自选股生成，"
        "只作为研究参考，不构成投资建议，也不承诺未来收益。"
    )

    MAX_SECTION_WARNING_COUNT = 10
    MAX_REPORT_WARNING_COUNT = 30

    def build_deterministic_report(
        self,
        context: DailyReportDataContext,
    ) -> DailyReportCreate:
        """生成不依赖 AI 的日报结果。

        这一步是日报的事实来源：状态、风险、股票快照和候选评分都来自后端确定性数据。
        后续即使用 AI，也只能润色这个 payload，而不是重新创造日报事实。
        """

        stock_snapshots = self._build_stock_snapshots(context)
        sections = self._build_sections(
            context=context,
            stock_snapshots=stock_snapshots,
        )

        status = self._resolve_status(context=context)
        unavailable_reason = self._resolve_unavailable_reason(
            context=context,
            status=status,
        )

        summary = self._build_summary(
            context=context,
            status=status,
            unavailable_reason=unavailable_reason,
            stock_snapshots=stock_snapshots,
        )

        return DailyReportCreate(
            user_id=context.user_id,
            report_date=context.report_date,
            status=status,
            source=context.input_snapshot.source,
            summary=summary,
            sections=sections,
            stock_snapshots=stock_snapshots,
            input_snapshot=context.input_snapshot,
            market_snapshot=self._build_market_snapshot(context),
            technical_snapshot=self._build_technical_snapshot(context),
            strategy_signal_snapshot=self._build_strategy_signal_snapshot(context),
            candidate_snapshot=self._build_candidate_snapshot(context),
            profile_snapshot=self._build_profile_snapshot(context),
            memory_snapshot=self._build_memory_snapshot(context),
            ai_used=False,
            ai_status=DailyReportAIStatus.NOT_USED,
            unavailable_reason=unavailable_reason,
            warnings=self._build_report_warnings(context),
            disclaimer=self.DISCLAIMER,
        )

    def _resolve_status(
        self,
        *,
        context: DailyReportDataContext,
    ) -> DailyReportStatus:
        if not context.watchlist_items:
            return DailyReportStatus.FAILED

        has_any_market_data = any(
            bool(item.market_overview)
            for item in context.stock_items
        )
        has_any_strategy_signal = any(
            bool(item.strategy_signal)
            for item in context.stock_items
        )
        has_candidate_data = bool(context.candidate_result)

        if not has_any_market_data and not has_any_strategy_signal and not has_candidate_data:
            return DailyReportStatus.FAILED

        return DailyReportStatus.GENERATED

    def _resolve_unavailable_reason(
        self,
        *,
        context: DailyReportDataContext,
        status: DailyReportStatus,
    ) -> DailyReportUnavailableReason | None:
        if status != DailyReportStatus.FAILED:
            return None

        if not context.watchlist_items:
            return DailyReportUnavailableReason.EMPTY_WATCHLIST

        return DailyReportUnavailableReason.NO_DATA

    def _build_summary(
        self,
        *,
        context: DailyReportDataContext,
        status: DailyReportStatus,
        unavailable_reason: DailyReportUnavailableReason | None,
        stock_snapshots: list[DailyReportStockSnapshot],
    ) -> str:
        if unavailable_reason == DailyReportUnavailableReason.EMPTY_WATCHLIST:
            return "当前用户没有自选股，暂时无法生成每日简报。"

        if unavailable_reason == DailyReportUnavailableReason.NO_DATA:
            return "当前自选股缺少可用行情或策略数据，暂时只能生成空简报。"

        signal_counts = self._count_strategy_signals(stock_snapshots)
        candidate_count = len(self._get_candidate_items(context))

        return (
            f"{context.report_date} 每日简报已生成。"
            f"本次纳入 {len(context.stock_items)} 只自选股，"
            f"其中候选评分返回 {candidate_count} 只候选。"
            f"策略信号分布：buy={signal_counts.get('buy', 0)}，"
            f"sell={signal_counts.get('sell', 0)}，"
            f"hold={signal_counts.get('hold', 0)}，"
            f"observe={signal_counts.get('observe', 0)}。"
            "本简报仅作为研究参考，不构成投资建议。"
        )

    def _build_sections(
        self,
        *,
        context: DailyReportDataContext,
        stock_snapshots: list[DailyReportStockSnapshot],
    ) -> list[DailyReportSection]:
        return [
            self._build_overview_section(context, stock_snapshots),
            self._build_market_movement_section(context),
            self._build_technical_status_section(context),
            self._build_strategy_signal_section(context, stock_snapshots),
            self._build_candidate_priority_section(context),
            self._build_risk_warning_section(context),
            self._build_personalized_note_section(context),
        ]

    def _build_overview_section(
        self,
        context: DailyReportDataContext,
        stock_snapshots: list[DailyReportStockSnapshot],
    ) -> DailyReportSection:
        available_count = sum(
            1
            for item in context.stock_items
            if item.market_overview or item.strategy_signal
        )

        return DailyReportSection(
            section_type=DailyReportSectionType.OVERVIEW,
            title="今日概览",
            summary=(
                f"本次简报读取自选股 {context.input_snapshot.watchlist_count} 只，"
                f"纳入 {context.input_snapshot.included_stock_count} 只，"
                f"其中 {available_count} 只存在可用行情或策略数据。"
            ),
            items=[
                {
                    "watchlist_count": context.input_snapshot.watchlist_count,
                    "included_stock_count": context.input_snapshot.included_stock_count,
                    "available_stock_count": available_count,
                    "warning_count": len(context.warnings),
                }
            ],
            warnings=self._limit_texts(context.warnings),
        )

    def _build_market_movement_section(
        self,
        context: DailyReportDataContext,
    ) -> DailyReportSection:
        items: list[dict[str, Any]] = []

        for stock in context.stock_items:
            quote = self._get_nested_value(stock.market_overview, "quote") or {}
            indicators = self._get_nested_value(stock.market_overview, "indicators") or {}

            items.append(
                {
                    "symbol": stock.symbol,
                    "market": stock.market,
                    "name": stock.name,
                    "latest_price": quote.get("latest_price"),
                    "price_change": quote.get("price_change"),
                    "price_change_percent": quote.get("price_change_percent")
                    or indicators.get("price_change_percent"),
                    "volume": quote.get("volume"),
                    "source": quote.get("source"),
                }
            )

        return DailyReportSection(
            section_type=DailyReportSectionType.MARKET_MOVEMENT,
            title="自选股行情变化",
            summary="本板块汇总自选股最新价格、涨跌幅和成交量变化。",
            items=items,
            warnings=[],
        )

    def _build_technical_status_section(
        self,
        context: DailyReportDataContext,
    ) -> DailyReportSection:
        items: list[dict[str, Any]] = []

        for stock in context.stock_items:
            indicators = self._get_nested_value(stock.market_overview, "indicators") or {}
            technical = self._get_nested_value(
                stock.market_overview,
                "technical_indicators",
            ) or {}

            items.append(
                {
                    "symbol": stock.symbol,
                    "market": stock.market,
                    "trend": indicators.get("trend")
                    or self._get_nested_value(technical, "moving_average", "trend"),
                    "volatility_level": indicators.get("volatility_level"),
                    "rsi_status": self._get_nested_value(technical, "rsi", "status"),
                    "macd_signal": self._get_nested_value(technical, "macd", "signal"),
                    "momentum_direction": self._get_nested_value(
                        technical,
                        "momentum",
                        "direction",
                    ),
                    "volume_status": self._get_nested_value(
                        technical,
                        "volume_factor",
                        "status",
                    ),
                }
            )

        return DailyReportSection(
            section_type=DailyReportSectionType.TECHNICAL_STATUS,
            title="技术状态",
            summary="本板块汇总趋势、RSI、MACD、动量和成交量状态。",
            items=items,
            warnings=[],
        )

    def _build_strategy_signal_section(
        self,
        context: DailyReportDataContext,
        stock_snapshots: list[DailyReportStockSnapshot],
    ) -> DailyReportSection:
        signal_counts = self._count_strategy_signals(stock_snapshots)
        items: list[dict[str, Any]] = []

        for stock in context.stock_items:
            signal = stock.strategy_signal or {}
            items.append(
                {
                    "symbol": stock.symbol,
                    "market": stock.market,
                    "status": signal.get("status"),
                    "signal": signal.get("signal"),
                    "strength": signal.get("strength"),
                    "score": signal.get("score"),
                    "summary": signal.get("summary"),
                }
            )

        return DailyReportSection(
            section_type=DailyReportSectionType.STRATEGY_SIGNAL,
            title="策略信号摘要",
            summary=(
                "策略信号分布："
                f"buy={signal_counts.get('buy', 0)}，"
                f"sell={signal_counts.get('sell', 0)}，"
                f"hold={signal_counts.get('hold', 0)}，"
                f"observe={signal_counts.get('observe', 0)}。"
            ),
            items=items,
            warnings=[],
        )

    def _build_candidate_priority_section(
        self,
        context: DailyReportDataContext,
    ) -> DailyReportSection:
        candidates = self._get_candidate_items(context)
        items = [
            {
                "symbol": item.get("symbol"),
                "market": item.get("market"),
                "name": item.get("name"),
                "rank": item.get("rank"),
                "score": item.get("score"),
                "grade": item.get("grade"),
                "reasons": self._limit_texts(item.get("reasons") or [], limit=3),
                "risks": self._limit_texts(item.get("risks") or [], limit=3),
            }
            for item in candidates
        ]

        if not candidates:
            summary = "本次没有生成候选评分结果。"
        else:
            summary = f"本次候选评分返回 {len(candidates)} 只研究候选，排序仅表示研究优先级。"

        return DailyReportSection(
            section_type=DailyReportSectionType.CANDIDATE_PRIORITY,
            title="候选研究优先级",
            summary=summary,
            items=items,
            warnings=self._limit_texts(
                self._get_nested_value(context.candidate_result, "warnings") or [],
            ),
        )

    def _build_risk_warning_section(
        self,
        context: DailyReportDataContext,
    ) -> DailyReportSection:
        items: list[dict[str, Any]] = []
        warnings: list[str] = list(context.warnings)

        for stock in context.stock_items:
            data_quality = self._get_nested_value(stock.market_overview, "data_quality") or {}
            strategy_signal = stock.strategy_signal or {}
            signal_risks = strategy_signal.get("risks") or []

            if data_quality:
                items.append(
                    {
                        "symbol": stock.symbol,
                        "market": stock.market,
                        "data_quality_status": data_quality.get("status"),
                        "is_empty": data_quality.get("is_empty"),
                        "is_enough": data_quality.get("is_enough"),
                        "is_stale": data_quality.get("is_stale"),
                        "warnings": self._limit_texts(
                            data_quality.get("warnings") or [],
                            limit=3,
                        ),
                        "errors": self._limit_texts(
                            data_quality.get("errors") or [],
                            limit=3,
                        ),
                    }
                )

            for risk in signal_risks[:3]:
                warnings.append(f"{stock.market}:{stock.symbol} - {risk}")

        return DailyReportSection(
            section_type=DailyReportSectionType.RISK_WARNING,
            title="风险提示",
            summary="本板块汇总数据质量、策略信号和个股读取过程中的风险提示。",
            items=items,
            warnings=self._limit_texts(warnings, limit=self.MAX_SECTION_WARNING_COUNT),
        )

    def _build_personalized_note_section(
        self,
        context: DailyReportDataContext,
    ) -> DailyReportSection:
        profile_summary = self._get_nested_value(
            context.user_profile_context,
            "summary",
        ) or {}
        memories = self._get_nested_value(
            context.relevant_memories_context,
            "items",
        ) or []

        items = [
            {
                "type": "user_preference",
                "risk_preference": self._get_nested_value(
                    context.user_preference,
                    "risk_preference",
                ),
            },
            {
                "type": "user_profile",
                "summary": profile_summary,
            },
            {
                "type": "relevant_memories",
                "count": len(memories),
                "items": [
                    {
                        "memory_id": item.get("memory_id"),
                        "title": item.get("title"),
                        "summary": item.get("summary"),
                        "similarity_score": item.get("similarity_score"),
                    }
                    for item in memories[:5]
                    if isinstance(item, dict)
                ],
            },
        ]

        return DailyReportSection(
            section_type=DailyReportSectionType.PERSONALIZED_NOTE,
            title="个性化提示",
            summary="本板块根据用户偏好、用户画像和相似记忆辅助调整解释重点。",
            items=items,
            warnings=[
                "个性化上下文只用于调整解释重点，不作为买卖依据。"
            ],
        )

    def _build_stock_snapshots(
        self,
        context: DailyReportDataContext,
    ) -> list[DailyReportStockSnapshot]:
        candidate_map = self._build_candidate_map(context)
        snapshots: list[DailyReportStockSnapshot] = []

        for stock in context.stock_items:
            overview = stock.market_overview or {}
            quote = self._get_nested_value(overview, "quote") or {}
            indicators = self._get_nested_value(overview, "indicators") or {}
            technical = self._get_nested_value(overview, "technical_indicators") or {}
            data_quality = self._get_nested_value(overview, "data_quality") or {}
            strategy_signal = stock.strategy_signal or {}
            candidate = candidate_map.get((stock.market, stock.symbol), {})

            snapshots.append(
                DailyReportStockSnapshot(
                    symbol=stock.symbol,
                    market=stock.market,
                    name=stock.name or quote.get("name"),
                    latest_price=self._to_decimal_or_none(quote.get("latest_price")),
                    change_percent=quote.get("price_change_percent")
                    or indicators.get("price_change_percent"),
                    volume_ratio=self._get_nested_value(
                        technical,
                        "volume_factor",
                        "volume_ratio",
                    ),
                    data_quality_status=data_quality.get("status"),
                    strategy_signal=strategy_signal.get("signal"),
                    strategy_strength=strategy_signal.get("strength"),
                    candidate_score=candidate.get("score"),
                    candidate_grade=candidate.get("grade"),
                )
            )

        return snapshots

    def _build_market_snapshot(
        self,
        context: DailyReportDataContext,
    ) -> dict[str, Any]:
        return {
            "stocks": [
                {
                    "symbol": item.symbol,
                    "market": item.market,
                    "quote": self._get_nested_value(item.market_overview, "quote") or {},
                    "indicators": self._get_nested_value(item.market_overview, "indicators") or {},
                }
                for item in context.stock_items
            ]
        }

    def _build_technical_snapshot(
        self,
        context: DailyReportDataContext,
    ) -> dict[str, Any]:
        return {
            "stocks": [
                {
                    "symbol": item.symbol,
                    "market": item.market,
                    "technical_indicators": self._get_nested_value(
                        item.market_overview,
                        "technical_indicators",
                    ) or {},
                }
                for item in context.stock_items
            ]
        }

    def _build_strategy_signal_snapshot(
        self,
        context: DailyReportDataContext,
    ) -> dict[str, Any]:
        signals = [
            {
                "symbol": item.symbol,
                "market": item.market,
                "strategy_signal": item.strategy_signal or {},
            }
            for item in context.stock_items
        ]

        return {
            "signals": signals,
            "counts": self._count_strategy_signals_from_items(context.stock_items),
        }

    def _build_candidate_snapshot(
        self,
        context: DailyReportDataContext,
    ) -> dict[str, Any]:
        if not context.candidate_result:
            return {}

        return {
            "status": context.candidate_result.get("status"),
            "summary": context.candidate_result.get("summary"),
            "candidates": self._get_candidate_items(context),
            "warnings": context.candidate_result.get("warnings") or [],
            "disclaimer": context.candidate_result.get("disclaimer"),
        }

    def _build_profile_snapshot(
        self,
        context: DailyReportDataContext,
    ) -> dict[str, Any]:
        return context.user_profile_context or {}

    def _build_memory_snapshot(
        self,
        context: DailyReportDataContext,
    ) -> dict[str, Any]:
        return context.relevant_memories_context or {}

    def _build_report_warnings(
        self,
        context: DailyReportDataContext,
    ) -> list[str]:
        warnings = list(context.warnings)
        warnings.append("每日简报只作为研究参考，不构成投资建议。")
        return self._limit_texts(warnings, limit=self.MAX_REPORT_WARNING_COUNT)

    def _build_candidate_map(
        self,
        context: DailyReportDataContext,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        candidate_map: dict[tuple[str, str], dict[str, Any]] = {}

        for item in self._get_candidate_items(context):
            market = item.get("market")
            symbol = item.get("symbol")
            if market and symbol:
                candidate_map[(str(market), str(symbol))] = item

        return candidate_map

    def _get_candidate_items(
        self,
        context: DailyReportDataContext,
    ) -> list[dict[str, Any]]:
        if not context.candidate_result:
            return []

        candidates = context.candidate_result.get("candidates") or []
        return [
            item
            for item in candidates
            if isinstance(item, dict)
        ]

    def _count_strategy_signals(
        self,
        stock_snapshots: list[DailyReportStockSnapshot],
    ) -> dict[str, int]:
        counts = {
            "buy": 0,
            "sell": 0,
            "hold": 0,
            "observe": 0,
            "unknown": 0,
        }

        for snapshot in stock_snapshots:
            signal = snapshot.strategy_signal or "unknown"
            counts[signal] = counts.get(signal, 0) + 1

        return counts

    def _count_strategy_signals_from_items(
        self,
        stock_items: list[DailyReportStockDataItem],
    ) -> dict[str, int]:
        counts = {
            "buy": 0,
            "sell": 0,
            "hold": 0,
            "observe": 0,
            "unknown": 0,
        }

        for item in stock_items:
            signal = self._get_nested_value(item.strategy_signal, "signal") or "unknown"
            counts[signal] = counts.get(signal, 0) + 1

        return counts

    def _get_nested_value(
        self,
        payload: dict[str, Any] | None,
        *keys: str,
    ):
        current = payload

        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)

        return current

    def _to_decimal_or_none(self, value) -> Decimal | None:
        if value is None:
            return None

        try:
            return Decimal(str(value))
        except Exception:
            return None

    def _limit_texts(
        self,
        values: list[Any],
        *,
        limit: int = 10,
    ) -> list[str]:
        texts: list[str] = []

        for value in values:
            text = str(value).strip()
            if not text:
                continue
            texts.append(text[:300])

            if len(texts) >= limit:
                break

        return texts
