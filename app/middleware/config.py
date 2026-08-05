"""Per-stage configuration for the custom and built-in middlewares."""

from typing import Any

from app.settings import settings


class MiddlewareConfig:
    """Configuration class for middleware components."""

    @staticmethod
    def get_timing_config() -> dict[str, Any]:
        """Get configuration for TimingMiddleware."""
        return {
            "log_slow_requests": settings.STAGE != "prod",
            "slow_threshold": 1.0 if settings.STAGE == "prod" else 0.5,
        }

    @staticmethod
    def get_logging_config() -> dict[str, Any]:
        """Get configuration for LoggingMiddleware."""
        return {
            "log_requests": settings.STAGE != "prod",
            "log_responses": settings.STAGE != "prod",
            "skip_paths": ["/ping", "/health", "/docs", "/openapi.json", "/redoc"],
        }

    @staticmethod
    def get_rate_limit_config() -> dict[str, Any]:
        """Get configuration for RateLimitMiddleware."""
        config = {
            "local": {"calls": 1000, "period": 60},
            "prod": {"calls": 50, "period": 60},
        }
        return config.get(settings.STAGE, config["prod"])

    @staticmethod
    def get_cors_config() -> dict[str, Any]:
        """Get configuration for CORS middleware."""
        return {
            "allow_origins": settings.ALLOWED_HOSTS,
            "allow_credentials": True,
            "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH"],
            "allow_headers": ["*"],
            "expose_headers": [
                "X-Process-Time",
                "X-Request-ID",
                "X-New-Access-Token",
                "X-Token-Refreshed",
            ],
        }

    @staticmethod
    def get_gzip_config() -> dict[str, Any]:
        """Get configuration for GZipMiddleware (built-in FastAPI)."""
        return {
            "minimum_size": 500,
        }

    @staticmethod
    def get_trusted_host_config() -> dict[str, Any]:
        """Get configuration for TrustedHostMiddleware."""
        allowed_hosts = settings.ALLOWED_HOSTS if settings.STAGE == "prod" else ["*"]

        return {
            "allowed_hosts": allowed_hosts,
        }

    @staticmethod
    def should_enable_middleware(middleware_name: str) -> bool:
        """Determine if a middleware should be enabled based on environment."""
        middleware_settings = {
            "timing": True,
            "logging": settings.STAGE != "prod",
            "rate_limit": settings.STAGE == "prod",
            "security": settings.STAGE == "prod",
            "request_id": True,
            "token_refresh": True,
            "gzip": True,
            "trusted_host": settings.STAGE == "prod",
            "https_redirect": settings.STAGE == "prod",
        }

        return middleware_settings.get(middleware_name, True)
