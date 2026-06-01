from fastapi import APIRouter

from app.api.routers.analysis_records import router as analysis_records_router
from app.api.routers.auth import router as auth_router
from app.api.routers.devices import router as devices_router
from app.api.routers.health import router as health_router
from app.api.routers.market import router as market_router
from app.api.routers.notifications import router as notifications_router
from app.api.routers.preferences import router as preferences_router
from app.api.routers.stock_analysis import router as stock_analysis_router
from app.api.routers.users import router as users_router
from app.api.routers.watchlist import router as watchlist_router
from app.api.routers.market_sync import router as market_sync_router
from app.api.routers.technical_indicators import router as technical_indicators_router
from app.api.routers.market_data_quality import router as market_data_quality_router
from app.api.routers.analysis_conversations import router as analysis_conversations_router
from app.api.routers.strategy_signals import router as strategy_signals_router
from app.api.routers.backtests import router as backtests_router
from app.api.routers.portfolio_backtests import router as portfolio_backtests_router
from app.api.routers.stock_candidates import router as stock_candidates_router
from app.api.routers.stock_candidate_ai_explanations import (
    router as stock_candidate_ai_explanations_router,
)
from app.api.routers.ai_usage import router as ai_usage_router
from app.api.routers.background_tasks import router as background_tasks_router
from app.api.routers.user_memories import router as user_memories_router
from app.api.routers.user_memory_retrieval import (
    router as user_memory_retrieval_router,
)
from app.api.routers.daily_reports import router as daily_reports_router

from app.core.config import get_settings

settings = get_settings()
api_router = APIRouter(prefix=settings.api_v1_prefix)

api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(watchlist_router)
api_router.include_router(preferences_router)
api_router.include_router(analysis_records_router)
api_router.include_router(notifications_router)
api_router.include_router(devices_router)
api_router.include_router(stock_analysis_router)
api_router.include_router(market_router)
api_router.include_router(market_sync_router)
api_router.include_router(technical_indicators_router)
api_router.include_router(strategy_signals_router)
api_router.include_router(backtests_router)
api_router.include_router(market_data_quality_router)
api_router.include_router(analysis_conversations_router)
api_router.include_router(portfolio_backtests_router)
api_router.include_router(stock_candidates_router)
api_router.include_router(stock_candidate_ai_explanations_router)
api_router.include_router(ai_usage_router)
api_router.include_router(background_tasks_router)
api_router.include_router(user_memories_router)
api_router.include_router(user_memory_retrieval_router)
api_router.include_router(daily_reports_router)