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
        """Get configuration for RateLimitMiddleware.

        The static per-stage call budget is the *default* limit every
        request falls under. Endpoint-specific rules (``get_route_rules``)
        lower the effective budget for auth/image/search and count against
        their own buckets. ``staging`` mirrors ``prod`` but intentionally
        stays below the strictest throughput caps.
        """
        configs = {
            "dev": {"calls": 200, "period": 60},
            "staging": {"calls": 100, "period": 60},
            "prod": {"calls": 60, "period": 60},
        }
        config = configs.get(settings.STAGE, configs["prod"])
        return {
            **config,
            "rules": MiddlewareConfig.get_route_rules(),
            "stage": settings.STAGE,
        }

    @staticmethod
    def get_route_rules() -> list[dict[str, Any]]:
        """Endpoint-specific rate limit rules, most-specific-first.

        Each rule carries stage-specific ``calls`` budgets and a distinct
        ``bucket`` so its traffic does not consume the caller's general
        API budget. Rules match by path:

        - ``path`` (default): request path ``startswith`` this value.
        - ``suffix`` (True): request path ``endswith`` this value
          (used for the shared ``/image`` upload suffix).
        - ``method``: optional HTTP method filter.
        - ``search`` (True): only when the request carries a ``search``
          query parameter (the debounced catalog search lists).

        Unmatched requests fall back to the default per-stage budget.
        """
        return [
            # Auth — brute-force / anti-spam / anti-abuse budgets.
            {"path": "/api/auth/login", "method": "POST", "bucket": "auth-login", "prod": 10, "staging": 10, "dev": 30},
            {"path": "/api/auth/register", "method": "POST", "bucket": "auth-register", "prod": 5, "staging": 5, "dev": 20},
            {"path": "/api/auth/forgot-password", "method": "POST", "bucket": "auth-forgot", "prod": 3, "staging": 3, "dev": 10},
            {"path": "/api/auth/reset-password", "method": "POST", "bucket": "auth-reset", "prod": 5, "staging": 5, "dev": 10},
            {"path": "/api/auth/refresh", "method": "POST", "bucket": "auth-refresh", "prod": 20, "staging": 20, "dev": 60},
            # Catalog image uploads — long-running, heavy body.
            {"path": "/image", "method": "PUT", "suffix": True, "bucket": "image", "prod": 5, "staging": 5, "dev": 20},
            # Debounced catalog search lists.
            {"path": "/api/spells", "method": "GET", "search": True, "bucket": "search-spells", "prod": 20, "staging": 20, "dev": 60},
            {"path": "/api/feats", "method": "GET", "search": True, "bucket": "search-feats", "prod": 20, "staging": 20, "dev": 60},
            {"path": "/api/features", "method": "GET", "search": True, "bucket": "search-features", "prod": 20, "staging": 20, "dev": 60},
        ]

    @staticmethod
    def get_cors_config() -> dict[str, Any]:
        """Get configuration for CORS middleware.

        ``allow_credentials`` is disabled when the origin list contains a
        wildcard (``*``) because Starlette / the ASGI spec reject the
        combination of ``Access-Control-Allow-Origin: *`` together with
        ``Access-Control-Allow-Credentials: true``.
        """
        origins = settings.ALLOWED_HOSTS
        has_wildcard = len(origins) == 1 and origins[0] == "*"
        return {
            "allow_origins": origins,
            "allow_credentials": not has_wildcard,
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
    def get_body_limit_config() -> dict[str, Any]:
        """Get configuration for RequestBodyLimitMiddleware."""
        return {
            "max_bytes": settings.REQUEST_BODY_MAX_BYTES,
        }

    @staticmethod
    def get_trusted_host_config() -> dict[str, Any]:
        """Get configuration for TrustedHostMiddleware."""
        allowed_hosts = settings.ALLOWED_HOSTS if settings.STAGE in ("prod", "staging") else ["*"]

        return {
            "allowed_hosts": allowed_hosts,
        }

    @staticmethod
    def should_enable_middleware(middleware_name: str) -> bool:
        """Determine if a middleware should be enabled based on environment."""
        middleware_settings = {
            "timing": True,
            "logging": settings.STAGE != "prod",
            "rate_limit": settings.STAGE in ("prod", "staging", "dev"),
            "body_limit": True,
            "security": settings.STAGE in ("prod", "staging"),
            "request_id": True,
            "token_refresh": True,
            "gzip": True,
            "trusted_host": settings.STAGE in ("prod", "staging"),
            "https_redirect": settings.STAGE in ("prod", "staging"),
        }

        return middleware_settings.get(middleware_name, True)
