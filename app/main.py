"""
Application entrypoint: FastAPI app assembly, middleware, and lifespan.

Builds the ``app`` instance (docs only outside prod), registers middleware
and global error handlers, mounts the feature routers, and provides a
``__main__`` uvicorn launcher. Schema management is left to Alembic.
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import uvicorn

from app.middleware import (
    LoggingMiddleware,
    MiddlewareConfig,
    RateLimitMiddleware,
    RequestIDMiddleware,
    TimingMiddleware,
)
from app.middleware.error_handler import setup_error_handlers
from app.router import api_router
from app.settings import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Schema management is handled exclusively by Alembic migrations, run as a
    separate deploy step (`alembic upgrade head`) before the app starts.
    The app never creates or alters tables itself.
    """
    logger.info("Starting up Heofberu Backend API...")
    yield
    logger.info("Shutting down Heofberu Backend API...")
    await settings.engine.dispose()


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
app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=8000,
        reload=settings.STAGE == "dev",
        workers=1 if settings.STAGE == "dev" else 4,
        access_log=settings.STAGE != "prod",
        log_level="info" if settings.STAGE != "prod" else "warning",
    )
