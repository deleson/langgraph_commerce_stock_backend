from fastapi import APIRouter

from app.api.routers.auth import router as auth_router
from app.api.routers.health import router as health_router
from app.api.routers.preferences import router as preferences_router
from app.api.routers.users import router as users_router
from app.api.routers.watchlist import router as watchlist_router
from app.core.config import get_settings

settings = get_settings()
api_router = APIRouter(prefix=settings.api_v1_prefix)


api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(watchlist_router)
api_router.include_router(preferences_router)