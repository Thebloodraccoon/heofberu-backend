"""Shared helpers used by the middleware modules."""

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Get client IP address considering proxy headers."""

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    return request.client.host if request.client else "unknown"
