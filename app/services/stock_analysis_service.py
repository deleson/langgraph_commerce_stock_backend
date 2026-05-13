from datetime import UTC, datetime
from uuid import uuid4

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

        initial_state = {
            "thread_id": thread_id,
            "user_id": user.id,
            "symbol": payload.symbol,
            "market": payload.market,
            "analysis_type": payload.analysis_type,
            "risk_preference": preference.risk_preference,
            "quality_context": quality_context,
            "technical_indicators": technical_indicators,
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
                summary=result.summary,
                result_snapshot={
                    "thread_id": thread_id,
                    "graph_route": final_state.get("graph_route"),
                    "quality_context": self._dump_optional_model(quality_context),
                    "context_snapshot": context_snapshot.model_dump(mode="json"),
                    "market_snapshot": self._dump_optional_model(market_snapshot),
                    "indicators": self._dump_optional_model(indicators),
                    "technical_indicators": self._dump_optional_model(technical_indicators),
                    "result": result.model_dump(mode="json"),
                    "metadata": metadata,
                },
                error_message=final_state.get("error_message"),
            ),
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

    def _resolve_thread_id(
        self,
        *,
        user_id: int,
        payload: StockAnalysisRequest,
    ) -> str:
        return payload.thread_id or f"stock-analysis-{user_id}-{uuid4().hex}"

    def _build_metadata(
        self,
        final_state: dict,
    ) -> dict:
        technical_indicators = final_state.get("technical_indicators")

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
                "quality_context_available": final_state.get("quality_context") is not None,
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
            result=final_state.get("result"),
            metadata=metadata,
            created_at=datetime.now(UTC),
        )

    def _dump_optional_model(self, value):
        if value is None:
            return None

        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")

        return value