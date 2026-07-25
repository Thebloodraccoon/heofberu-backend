from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import uvicorn

from app.features.auth.endpoints import router as auth_router
from app.features.characters.endpoints import router as character_router
from app.features.ping.endpoints import router as ping_router
from app.features.races.endpoints import router as race_router
from app.features.spells.endpoints import router as spell_router
from app.features.users.endpoints import router as user_router
from app.middleware import (
    LoggingMiddleware,
    MiddlewareConfig,
    RateLimitMiddleware,
    RequestIDMiddleware,
    TimingMiddleware,
)
from app.middleware.error_handler import setup_error_handlers
from app.settings import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Schema management is handled exclusively by Alembic migrations, run as a
    separate deploy step (`alembic upgrade head`) before the app starts.
    The app never creates or alters tables itself.
    """
    logger.info("Starting up Heofberu Backend API...")
    yield
    logger.info("Shutting down Heofberu Backend API...")


def setup_middleware(app: FastAPI) -> None:
    """Setup application middleware in the correct order."""
    cors_config = MiddlewareConfig.get_cors_config()
    app.add_middleware(CORSMiddleware, **cors_config)

    if MiddlewareConfig.should_enable_middleware("trusted_host"):
        trusted_host_config = MiddlewareConfig.get_trusted_host_config()
        app.add_middleware(TrustedHostMiddleware, **trusted_host_config)

    if MiddlewareConfig.should_enable_middleware("gzip"):
        gzip_config = MiddlewareConfig.get_gzip_config()
        app.add_middleware(GZipMiddleware, **gzip_config)

    if MiddlewareConfig.should_enable_middleware("rate_limit"):
        rate_limit_config = MiddlewareConfig.get_rate_limit_config()
        app.add_middleware(RateLimitMiddleware, **rate_limit_config)

    if MiddlewareConfig.should_enable_middleware("request_id"):
        app.add_middleware(RequestIDMiddleware)

    if MiddlewareConfig.should_enable_middleware("logging"):
        logging_config = MiddlewareConfig.get_logging_config()
        app.add_middleware(LoggingMiddleware, **logging_config)

    if MiddlewareConfig.should_enable_middleware("timing"):
        timing_config = MiddlewareConfig.get_timing_config()
        app.add_middleware(TimingMiddleware, **timing_config)


def setup_routers(app: FastAPI) -> None:
    """Setup API routes with proper versioning."""
    api_prefix = "/api"

    app.include_router(ping_router, prefix=f"{api_prefix}/ping", tags=["Health Check"])
    app.include_router(auth_router, prefix=f"{api_prefix}/auth", tags=["Auth"])
    app.include_router(user_router, prefix=f"{api_prefix}/users", tags=["Users"])
    app.include_router(race_router, prefix=f"{api_prefix}/races", tags=["Races"])
    app.include_router(spell_router, prefix=f"{api_prefix}/spells", tags=["Spells"])
    app.include_router(character_router, prefix=f"{api_prefix}/characters", tags=["Characters"])


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Heofberu Backend API - A D&D world management system",
    lifespan=lifespan,
    docs_url="/docs" if settings.STAGE != "prod" else None,
    redoc_url="/redoc" if settings.STAGE != "prod" else None,
    openapi_url="/openapi.json" if settings.STAGE != "prod" else None,
    separate_input_output_schemas=True,
)

setup_middleware(app)
setup_error_handlers(app)
setup_routers(app)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=8000,
        reload=settings.STAGE == "local",
        workers=1 if settings.STAGE == "local" else 4,
        access_log=settings.STAGE != "prod",
        log_level="info" if settings.STAGE != "prod" else "warning",
    )
