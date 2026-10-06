"""
Baseline security response headers (pure ASGI middleware).

This is an API, so the set is small: no MIME sniffing, no framing, no referrer
leakage, and (over TLS-terminating proxies, in prod-like stages) HSTS.
Headers already present on a response are never overwritten.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_BASE_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
)

_HSTS_HEADER = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")


class SecurityHeadersMiddleware:
    """Add the baseline security headers to every HTTP response."""

    def __init__(self, app: ASGIApp, hsts: bool = False):
        self.app = app
        self.headers = _BASE_HEADERS + ((_HSTS_HEADER,) if hsts else ())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", ()))
                present = {name.lower() for name, _ in headers}
                headers.extend(header for header in self.headers if header[0] not in present)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
