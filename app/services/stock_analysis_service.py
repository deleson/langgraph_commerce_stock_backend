from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.graphs.stock_analysis_graph import run_stock_analysis_graph,arun_stock_analysis_graph
from app.models.user import User
from app.schemas.analysis_record import AnalysisRecordCreateRequest
from app.schemas.notification import NotificationCreateRequest
from app.schemas.stock_analysis import (
    StockAnalysisRequest,
    StockAnalysisResponse,
)
from app.schemas.technical_indicator import TechnicalIndicatorResponse
from app.services.technical_indicator_query_service import TechnicalIndicatorQueryService
from app.services.analysis_record_service import (
    AnalysisRecordService,
    AsyncAnalysisRecordService,
)
from app.services.notification_service import (
    AsyncNotificationService,
    NotificationService,
)
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

        final_state = run_stock_analysis_graph(
            {
                "user_id": user.id,
                "symbol": payload.symbol,
                "market": payload.market,
                "analysis_type": payload.analysis_type,
                "risk_preference": preference.risk_preference,
                "metadata": {
                    "llm_provider": "deepseek",
                    "source": "stock_analysis_service",
                },
            }
        )

        market_snapshot = final_state["market_snapshot"]
        indicators = final_state["indicators"]
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
                    "market_snapshot": market_snapshot.model_dump(mode="json"),
                    "indicators": indicators.model_dump(mode="json"),
                    "result": result.model_dump(mode="json"),
                    "metadata": final_state.get("metadata", {}),
                },
                error_message=None,
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
            symbol=record.symbol,
            market=record.market,
            analysis_type=record.analysis_type,
            status=record.status,
            market_snapshot=market_snapshot,
            indicators=indicators,
            result=result,
            created_at=record.created_at,
        )


class AsyncStockAnalysisService:
    """Coordinate async stock analysis graph execution, persistence, and notification."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.analysis_record_service = AsyncAnalysisRecordService(db)
        self.notification_service = AsyncNotificationService(db)
        self.user_preference_service = AsyncUserPreferenceService(db)
        self.technical_indicator_query_service = TechnicalIndicatorQueryService(db)

    async def analyze_stock(
        self,
        *,
        user: User,
        payload: StockAnalysisRequest,
    ) -> StockAnalysisResponse:
        preference = await self.user_preference_service.get_or_create_my_preference(user)

        final_state = await arun_stock_analysis_graph(
            {
                "user_id": user.id,
                "symbol": payload.symbol,
                "market": payload.market,
                "analysis_type": payload.analysis_type,
                "risk_preference": preference.risk_preference,
                "metadata": {
                    "llm_provider": "deepseek",
                    "source": "async_stock_analysis_service",
                },
            }
        )

        market_snapshot = final_state["market_snapshot"]
        indicators = final_state["indicators"]
        result = final_state["result"]
        technical_indicators = await self._load_technical_indicators_context(
            symbol=payload.symbol,
            market=payload.market,
        )

        metadata = {
            **final_state.get("metadata", {}),
            "ai_context": {
                "technical_indicators_available": technical_indicators is not None,
                "technical_indicators_source": technical_indicators.source
                if technical_indicators is not None
                else None,
                "technical_indicators_candle_count": technical_indicators.candle_count
                if technical_indicators is not None
                else 0,
            },
        }


        record = await self.analysis_record_service.create_record(
            user=user,
            payload=AnalysisRecordCreateRequest(
                symbol=payload.symbol,
                market=payload.market,
                analysis_type=payload.analysis_type,
                status="completed",
                summary=result.summary,
                result_snapshot={
                    "market_snapshot": market_snapshot.model_dump(mode="json"),
                    "indicators": indicators.model_dump(mode="json"),
                    "technical_indicators": technical_indicators.model_dump(mode="json")
                    if technical_indicators is not None
                    else None,
                    "result": result.model_dump(mode="json"),
                    "metadata": metadata,
                },
                error_message=None,
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
        final_state["technical_indicators"] = technical_indicators
        final_state["metadata"] = metadata


        return StockAnalysisResponse(
            record_id=record.id,
            symbol=record.symbol,
            market=record.market,
            analysis_type=record.analysis_type,
            status=record.status,
            market_snapshot=market_snapshot,
            indicators=indicators,
            result=result,
            created_at=record.created_at,
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
                limit=80,
                adjust_type="none",
                source=None,
            )
        except Exception:
            return None