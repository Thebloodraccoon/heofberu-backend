"""Shared helpers used by the middleware modules."""

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """
    Get the real client IP address.

    ``X-Forwarded-For`` / ``X-Real-IP`` are never read here (any client can
    spoof them). Behind a reverse proxy, uvicorn rewrites
    ``request.client.host`` from ``X-Forwarded-For`` itself, but only for
    proxies listed in ``FORWARDED_ALLOW_IPS`` (see ``app.main.uvicorn_options``);
    without that setting every client appears with the proxy's IP.
    """

    return request.client.host if request.client else "unknown"
