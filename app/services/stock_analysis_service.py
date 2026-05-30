import logging
from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.exceptions import NotFoundException
from app.core.llm import get_chat_model

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.graphs.stock_analysis_graph import (
    arun_stock_analysis_graph,
    run_stock_analysis_graph,
)
from app.models.user import User
from app.schemas.analysis_record import AnalysisRecordCreateRequest
from app.schemas.notification import NotificationCreateRequest
from app.schemas.stock_analysis import (
    StockAnalysisContextSnapshot,
    StockAnalysisFollowUpRequest,
    StockAnalysisFollowUpResponse,
    StockAnalysisQualityContext,
    StockAnalysisRequest,
    StockAnalysisResponse,
)
from app.schemas.technical_indicator import TechnicalIndicatorResponse
from app.services.analysis_record_service import (
    AnalysisRecordService,
    AsyncAnalysisRecordService,
)
from app.services.market_data_quality_report_service import MarketDataQualityReportService
from app.services.notification_service import (
    AsyncNotificationService,
    NotificationService,
)
from app.services.technical_indicator_query_service import TechnicalIndicatorQueryService
from app.services.user_preference_service import (
    AsyncUserPreferenceService,
    UserPreferenceService,
)
from app.services.analysis_conversation_service import AnalysisConversationService
from app.services.user_memory_extraction_service import UserMemoryExtractionService
from app.schemas.strategy_signal import StrategySignalResponse
from app.services.strategy_signal_query_service import StrategySignalQueryService
from app.services.user_memory_query_service import UserMemoryQueryService

logger = logging.getLogger(__name__)

class StockAnalysisService:
    """Coordinate stock analysis graph execution, persistence, and notification."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.analysis_record_service = AnalysisRecordService(db)
        self.notification_service = NotificationService(db)
        self.user_preference_service = UserPreferenceService(db)

    def analyze_stock(
        self,
        *,
        user: User,
        payload: StockAnalysisRequest,
    ) -> StockAnalysisResponse:
        preference = self.user_preference_service.get_or_create_my_preference(user)
        thread_id = self._resolve_thread_id(
            user_id=user.id,
            payload=payload,
        )

        final_state = run_stock_analysis_graph(
            {
                "thread_id": thread_id,
                "user_id": user.id,
                "symbol": payload.symbol,
                "market": payload.market,
                "analysis_type": payload.analysis_type,
                "risk_preference": preference.risk_preference,
                "metadata": {
                    "llm_provider": "deepseek",
                    "source": "stock_analysis_service",
                },
            },
            thread_id=thread_id,
        )

        market_snapshot = final_state.get("market_snapshot")
        indicators = final_state.get("indicators")
        result = final_state["result"]

        record = self.analysis_record_service.create_record(
            user=user,
            payload=AnalysisRecordCreateRequest(
                symbol=payload.symbol,
                market=payload.market,
                analysis_type=payload.analysis_type,
                status="completed",
                analysis_thread_id=thread_id,
                summary=result.summary,
                result_snapshot={
                    "thread_id": thread_id,
                    "graph_route": final_state.get("graph_route"),
                    "quality_context": self._dump_optional_model(final_state.get("quality_context")),
                    "market_snapshot": self._dump_optional_model(market_snapshot),
                    "indicators": self._dump_optional_model(indicators),
                    "technical_indicators": self._dump_optional_model(
                        final_state.get("technical_indicators")
                    ),
                    "result": result.model_dump(mode="json"),
                    "metadata": final_state.get("metadata", {}),
                },
                error_message=final_state.get("error_message"),
            ),
        )

        notification = self.notification_service.create_notification(
            user=user,
            payload=NotificationCreateRequest(
                title=f"{payload.symbol} 分析已完成",
                content=result.summary,
                notification_type="analysis_completed",
                related_record_id=record.id,
            ),
        )

        final_state["record_id"] = record.id
        final_state["notification_id"] = notification.id

        return StockAnalysisResponse(
            record_id=record.id,
            thread_id=thread_id,
            symbol=record.symbol,
            market=record.market,
            analysis_type=record.analysis_type,
            status=record.status,
            graph_route=final_state.get("graph_route"),
            quality_context=final_state.get("quality_context"),
            market_snapshot=market_snapshot,
            indicators=indicators,
            result=result,
            created_at=record.created_at,
        )

    def _resolve_thread_id(
        self,
        *,
        user_id: int,
        payload: StockAnalysisRequest,
    ) -> str:
        return payload.thread_id or f"stock-analysis-{user_id}-{uuid4().hex}"

    def _dump_optional_model(self, value):
        if value is None:
            return None

        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")

        return value


class AsyncStockAnalysisService:
    """Coordinate async stock analysis graph execution, persistence, and notification."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.analysis_record_service = AsyncAnalysisRecordService(db)
        self.notification_service = AsyncNotificationService(db)
        self.user_preference_service = AsyncUserPreferenceService(db)
        self.quality_report_service = MarketDataQualityReportService(db)
        self.technical_indicator_query_service = TechnicalIndicatorQueryService(db)
        self.strategy_signal_query_service = StrategySignalQueryService(db)
        self.conversation_service = AnalysisConversationService(db)
        self.memory_extraction_service = UserMemoryExtractionService(db)
        self.user_memory_query_service = UserMemoryQueryService(db)

    async def analyze_stock(
        self,
        *,
        user: User,
        payload: StockAnalysisRequest,
    ) -> StockAnalysisResponse:
        preference = await self.user_preference_service.get_or_create_my_preference(user)
        thread_id = self._resolve_thread_id(
            user_id=user.id,
            payload=payload,
        )

        quality_context = await self._load_quality_context(
            symbol=payload.symbol,
            market=payload.market,
        )
        technical_indicators = await self._load_technical_indicators_context(
            symbol=payload.symbol,
            market=payload.market,
        )
        strategy_signal = await self._load_strategy_signal_context(
            symbol=payload.symbol,
            market=payload.market,
        )
        user_profile_context = await self._load_user_profile_context(
            user_id=user.id,
        )

        initial_state = {
            "thread_id": thread_id,
            "user_id": user.id,
            "symbol": payload.symbol,
            "market": payload.market,
            "analysis_type": payload.analysis_type,
            "risk_preference": preference.risk_preference,
            "quality_context": quality_context,
            "technical_indicators": technical_indicators,
            "strategy_signal": strategy_signal,
            "user_profile_context": user_profile_context,
            "metadata": {
                "llm_provider": "deepseek",
                "source": "async_stock_analysis_service",
            },
        }

        final_state = await arun_stock_analysis_graph(
            initial_state,
            thread_id=thread_id,
        )

        result = final_state["result"]
        market_snapshot = final_state.get("market_snapshot")
        indicators = final_state.get("indicators")
        technical_indicators = final_state.get("technical_indicators")
        quality_context = final_state.get("quality_context")
        metadata = self._build_metadata(final_state)
        strategy_signal = final_state.get("strategy_signal")

        context_snapshot = self._build_context_snapshot(
            user=user,
            payload=payload,
            thread_id=thread_id,
            final_state=final_state,
            metadata=metadata,
        )
        final_state["context_snapshot"] = context_snapshot

        record = await self.analysis_record_service.create_record(
            user=user,
            payload=AnalysisRecordCreateRequest(
                symbol=payload.symbol,
                market=payload.market,
                analysis_type=payload.analysis_type,
                status="completed",
                analysis_thread_id=thread_id,
                summary=result.summary,
                result_snapshot={
                    "thread_id": thread_id,
                    "graph_route": final_state.get("graph_route"),
                    "quality_context": self._dump_optional_model(quality_context),
                    "context_snapshot": context_snapshot.model_dump(mode="json"),
                    "market_snapshot": self._dump_optional_model(market_snapshot),
                    "indicators": self._dump_optional_model(indicators),
                    "technical_indicators": self._dump_optional_model(technical_indicators),
                    "strategy_signal": self._dump_optional_model(strategy_signal),
                    "result": result.model_dump(mode="json"),
                    "metadata": metadata,
                },
                error_message=final_state.get("error_message"),
            ),
        )

        await self._extract_memory_from_analysis_record(
            user=user,
            record=record,
        )

        notification = await self.notification_service.create_notification(
            user=user,
            payload=NotificationCreateRequest(
                title=f"{payload.symbol} 分析已完成",
                content=result.summary,
                notification_type="analysis_completed",
                related_record_id=record.id,
            ),
        )

        final_state["record_id"] = record.id
        final_state["notification_id"] = notification.id

        return StockAnalysisResponse(
            record_id=record.id,
            thread_id=thread_id,
            symbol=record.symbol,
            market=record.market,
            analysis_type=record.analysis_type,
            status=record.status,
            graph_route=final_state.get("graph_route"),
            quality_context=quality_context,
            market_snapshot=market_snapshot,
            indicators=indicators,
            result=result,
            created_at=record.created_at,
        )

    async def follow_up_stock_analysis(
        self,
        *,
        user: User,
        payload: StockAnalysisFollowUpRequest,
    ) -> StockAnalysisFollowUpResponse:
        record = await self.analysis_record_service.analysis_record_repo.get_latest_by_thread_id_for_user(
            thread_id=payload.thread_id,
            user_id=user.id,
        )

        if record is None:
            raise NotFoundException(
                message="stock analysis thread not found",
                details=[
                    {
                        "field": "thread_id",
                        "reason": "analysis thread does not exist or does not belong to current user",
                    }
                ],
            )

        conversation_context = await self.conversation_service.get_context(
            user_id=user.id,
            analysis_thread_id=payload.thread_id,
            limit=10,
        )

        await self.conversation_service.save_user_message(
            user_id=user.id,
            analysis_record_id=record.id,
            analysis_thread_id=payload.thread_id,
            content=payload.message,
            source="normal_follow_up",
            message_type="normal_follow_up",
            payload={
                "referenced_symbol": record.symbol,
                "referenced_market": record.market,
            },
        )

        result_snapshot = record.result_snapshot or {}
        context_snapshot = result_snapshot.get("context_snapshot") or {}
        result = result_snapshot.get("result") or {}

        messages = self._build_follow_up_messages(
            record_symbol=record.symbol,
            record_market=record.market,
            user_message=payload.message,
            result=result,
            context_snapshot=context_snapshot,
            result_snapshot=result_snapshot,

            conversation_context=conversation_context.model_dump(mode="json"),

        )

        fallback_used = False

        try:
            llm = get_chat_model()
            response = await llm.ainvoke(messages)
            answer = str(response.content).strip()
        except Exception as exc:
            fallback_used = True
            logger.exception("stock analysis follow-up llm call failed")
            answer = self._build_follow_up_fallback_answer(
                symbol=record.symbol,
                market=record.market,
                reason=self._safe_exception_message(exc),
            )

        await self.conversation_service.save_assistant_message(
            user_id=user.id,
            analysis_record_id=record.id,
            analysis_thread_id=payload.thread_id,
            content=answer,
            source="normal_follow_up",
            message_type="normal_follow_up",
            payload={
                "referenced_symbol": record.symbol,
                "referenced_market": record.market,
                "fallback": fallback_used,
            },
        )

        return StockAnalysisFollowUpResponse(
            thread_id=payload.thread_id,
            answer=answer,
            referenced_analysis_record_id=record.id,
            referenced_symbol=record.symbol,
            referenced_market=record.market,
            created_at=datetime.now(UTC),
        )

    async def _load_quality_context(
        self,
        *,
        symbol: str,
        market: str,
    ) -> StockAnalysisQualityContext:
        data_quality = await self.quality_report_service.get_quality_report(
            symbol=symbol,
            market=market,
            timeframe="1d",
            limit=120,
            adjust_type="none",
            source=None,
            min_required=35,
            stale_after_days=None,
        )

        return StockAnalysisQualityContext(
            data_quality=data_quality,
            warnings=data_quality.warnings,
            errors=data_quality.errors,
        )

    async def _load_technical_indicators_context(
        self,
        *,
        symbol: str,
        market: str,
    ) -> TechnicalIndicatorResponse | None:
        try:
            return await self.technical_indicator_query_service.get_summary(
                symbol=symbol,
                market=market,
                timeframe="1d",
                limit=120,
                adjust_type="none",
                source=None,
            )
        except Exception:
            return None

    async def _load_strategy_signal_context(
        self,
        *,
        symbol: str,
        market: str,
    ) -> StrategySignalResponse | None:
        try:
            return await self.strategy_signal_query_service.get_signal(
                symbol=symbol,
                market=market,
                timeframe="1d",
                limit=120,
                adjust_type="none",
                source=None,
                include_detail=True,
                min_required=35,
                stale_after_days=None,
            )
        except Exception:
            logger.exception("load strategy signal context failed")
            return None

    async def _load_user_profile_context(
        self,
        *,
        user_id: int,
    ) -> dict | None:
        try:
            return await self.user_memory_query_service.get_profile_context(
                user_id=user_id,
                create_if_missing=True,
            )
        except Exception:
            logger.exception(
                "load user profile context failed",
                extra={"user_id": user_id},
            )
            return None

    def _resolve_thread_id(
        self,
        *,
        user_id: int,
        payload: StockAnalysisRequest,
    ) -> str:
        return payload.thread_id or f"stock-analysis-{user_id}-{uuid4().hex}"

    async def _extract_memory_from_analysis_record(
        self,
        *,
        user: User,
        record,
    ) -> None:
        try:
            await self.memory_extraction_service.extract_from_analysis_record(
                user_id=user.id,
                record_id=record.id,
                analysis_thread_id=record.analysis_thread_id,
                symbol=record.symbol,
                market=record.market,
                analysis_type=record.analysis_type,
                result_snapshot=record.result_snapshot,
                summary=record.summary,
            )
        except Exception:
            logger.exception(
                "failed to extract user memory from analysis record",
                extra={
                    "user_id": user.id,
                    "record_id": record.id,
                    "analysis_thread_id": record.analysis_thread_id,
                    "symbol": record.symbol,
                    "market": record.market,
                },
            )

    def _build_metadata(
            self,
            final_state: dict,
    ) -> dict:
        technical_indicators = final_state.get("technical_indicators")
        strategy_signal = final_state.get("strategy_signal")
        user_profile_context = final_state.get("user_profile_context")

        return {
            **final_state.get("metadata", {}),
            "ai_context": {
                "graph_route": final_state.get("graph_route"),
                "technical_indicators_available": technical_indicators is not None,
                "technical_indicators_source": technical_indicators.source
                if technical_indicators is not None
                else None,
                "technical_indicators_candle_count": technical_indicators.candle_count
                if technical_indicators is not None
                else 0,
                "strategy_signal_available": strategy_signal is not None,
                "strategy_signal_status": strategy_signal.status
                if strategy_signal is not None
                else None,
                "strategy_signal": strategy_signal.signal
                if strategy_signal is not None
                else None,
                "strategy_signal_score": strategy_signal.score
                if strategy_signal is not None
                else None,
                "quality_context_available": final_state.get("quality_context") is not None,
                "user_profile_context_available": user_profile_context is not None,
                "user_profile_status": user_profile_context.get("status")
                if isinstance(user_profile_context, dict)
                else None,
                "user_profile_version": user_profile_context.get("profile_version")
                if isinstance(user_profile_context, dict)
                else None,
            },
        }

    def _build_context_snapshot(
        self,
        *,
        user: User,
        payload: StockAnalysisRequest,
        thread_id: str,
        final_state: dict,
        metadata: dict,
    ) -> StockAnalysisContextSnapshot:
        return StockAnalysisContextSnapshot(
            thread_id=thread_id,
            user_id=user.id,
            symbol=payload.symbol,
            market=payload.market,
            analysis_type=payload.analysis_type,
            risk_preference=final_state.get("risk_preference", "balanced"),
            graph_route=final_state.get("graph_route"),
            quality_context=final_state.get("quality_context"),
            market_snapshot=final_state.get("market_snapshot"),
            indicators=final_state.get("indicators"),
            technical_indicators=final_state.get("technical_indicators"),
            strategy_signal=final_state.get("strategy_signal"),
            user_profile_context=final_state.get("user_profile_context"),
            result=final_state.get("result"),
            metadata=metadata,
            created_at=datetime.now(UTC),
        )

    def _build_follow_up_messages(
            self,
            *,
            record_symbol: str,
            record_market: str,
            user_message: str,
            result: dict,
            context_snapshot: dict,
            result_snapshot: dict,
            conversation_context: dict,
    ) -> list[SystemMessage | HumanMessage]:
        system_prompt = """
你是一个谨慎、客观的中文股票分析助手，正在回答用户对“上一次股票分析结果”的追问。

重要规则：
1. 只能基于系统提供的历史分析上下文回答。
2. 不要编造实时行情、新闻、财报或外部事实。
3. 不要承诺收益。
4. 不要给出“必须买入 / 必须卖出”的确定性指令。
5. 如果上下文不足，要明确说明“当前上下文不足以判断”。
6. 回答必须使用简体中文。
7. 回答要适合普通用户理解，但保持专业和谨慎。
""".strip()

        human_prompt = f"""
用户正在追问上一份股票分析。

股票：
symbol={record_symbol}
market={record_market}

用户追问：
{user_message}

最近几轮会话上下文：
{conversation_context}

上一次 AI 分析 result：
{result}

上一次分析 context_snapshot：
{context_snapshot}

完整 result_snapshot：
{result_snapshot}

请基于以上上下文，用简体中文回答用户追问。
""".strip()

        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ]

    def _build_follow_up_fallback_answer(
            self,
            *,
            symbol: str,
            market: str,
            reason: str,
    ) -> str:
        return (
            f"当前暂时无法生成 {market}:{symbol} 的追问回答。"
            "系统已找到上一份分析记录，但 AI 追问生成过程出现异常。"
            "你可以稍后重试，或先查看原始分析结果、行情数据、技术指标和数据质量报告。"
            f"内部原因摘要：{reason}"
        )

    def _safe_exception_message(self, exc: Exception) -> str:
        message = str(exc).strip()
        if not message:
            message = exc.__class__.__name__

        return f"{exc.__class__.__name__}: {message[:300]}"

    def _dump_optional_model(self, value):
        if value is None:
            return None

        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")

        return value
