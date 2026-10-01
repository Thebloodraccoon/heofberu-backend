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
    MiddlewareConfig,
    ObservabilityMiddleware,
    RateLimitMiddleware,
    RequestBodyLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.middleware.error_handler import setup_error_handlers
from app.router import api_router
from app.settings import settings

# Without a root handler Python only prints WARNING+ from ``app.*`` loggers.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

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
    close_redis = getattr(settings.get_redis, "close", None)
    if close_redis is not None:
        await close_redis()
    await settings.engine.dispose()


def setup_middleware(app: FastAPI) -> None:
    """
    Setup application middleware in the correct order.

    Middleware is executed last-added-first (Starlette inverts the order), so
    CORSMiddleware must be added *last* to wrap every other middleware —
    including ``RequestBodyLimitMiddleware`` — and guarantee that error
    responses (e.g. 413) carry the proper ``Access-Control-*`` headers.
    ``SecurityHeadersMiddleware`` sits right below it so every response,
    errors included, carries the security headers.
    """
    if MiddlewareConfig.should_enable_middleware("body_limit"):
        body_limit_config = MiddlewareConfig.get_body_limit_config()
        app.add_middleware(RequestBodyLimitMiddleware, **body_limit_config)

    if MiddlewareConfig.should_enable_middleware("trusted_host"):
        trusted_host_config = MiddlewareConfig.get_trusted_host_config()
        app.add_middleware(TrustedHostMiddleware, **trusted_host_config)

    if MiddlewareConfig.should_enable_middleware("gzip"):
        gzip_config = MiddlewareConfig.get_gzip_config()
        app.add_middleware(GZipMiddleware, **gzip_config)

    if MiddlewareConfig.should_enable_middleware("rate_limit"):
        rate_limit_config = MiddlewareConfig.get_rate_limit_config()
        app.add_middleware(RateLimitMiddleware, **rate_limit_config)

    if MiddlewareConfig.should_enable_middleware("observability"):
        observability_config = MiddlewareConfig.get_observability_config()
        app.add_middleware(ObservabilityMiddleware, **observability_config)

    if MiddlewareConfig.should_enable_middleware("security_headers"):
        app.add_middleware(SecurityHeadersMiddleware, **MiddlewareConfig.get_security_headers_config())

    cors_config = MiddlewareConfig.get_cors_config()
    app.add_middleware(CORSMiddleware, **cors_config)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Heofberu Backend API - A D&D world management system",
    lifespan=lifespan,
    docs_url="/docs" if settings.STAGE not in ("prod", "staging") else None,
    redoc_url="/redoc" if settings.STAGE not in ("prod", "staging") else None,
    openapi_url="/openapi.json" if settings.STAGE not in ("prod", "staging") else None,
    separate_input_output_schemas=True,
)

setup_middleware(app)
setup_error_handlers(app)
app.include_router(api_router)


def uvicorn_options() -> dict:
    """
    Keyword arguments for ``uvicorn.run``.

    ``forwarded_allow_ips`` (``FORWARDED_ALLOW_IPS``) lists the reverse proxies whose
    ``X-Forwarded-For`` uvicorn trusts; the rate limiter reads ``request.client.host``
    and so only sees real client IPs when the proxy is listed there.
    """

    is_dev = settings.STAGE == "dev"
    return {
        "host": settings.HOST,
        "port": 8000,
        "reload": is_dev,
        "workers": 1 if is_dev else settings.WEB_CONCURRENCY,
        "access_log": settings.STAGE != "prod",
        "log_level": "info" if settings.STAGE != "prod" else "warning",
        "proxy_headers": True,
        "forwarded_allow_ips": settings.FORWARDED_ALLOW_IPS,
    }


if __name__ == "__main__":
    uvicorn.run("app.main:app", **uvicorn_options())
