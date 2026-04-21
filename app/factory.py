from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging,get_logger
from app.core.middleware import register_middlewares



def create_application() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.app_log_level)
    logger = get_logger("app.factory")

    @asynccontextmanager
    async def lifespan(app:FastAPI):
        lifecycle_logger= get_logger("app.lifecycle")
        lifecycle_logger.info(
            "Application startup | env=%s | debug=%s",
            settings.app_env,
            settings.app_debug,
        )
        yield
        lifecycle_logger.info("Application shutdown")

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
        lifespan=lifespan
    )

    register_exception_handlers(application)
    register_middlewares(application)
    application.include_router(api_router)

    logger.info("Application configured successfully")
    return application

