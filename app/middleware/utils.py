"""Shared helpers used by the middleware modules."""

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """
    Get the real client IP address.

    Under a trusted reverse proxy (nginx, Cloudflare, etc.) the ASGI
    server already resolves ``request.client.host`` to the actual
    client IP from the TCP connection, so proxy-originated headers
    like ``X-Forwarded-For`` and ``X-Real-IP`` are *not* trusted
    here — they can be trivially spoofed by any client.
    """

    return request.client.host if request.client else "unknown"
