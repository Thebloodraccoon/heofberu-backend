"""
Request body-size guard (pure ASGI middleware).

Rejects requests whose body exceeds ``settings.REQUEST_BODY_MAX_BYTES`` with a
413 in the standard error envelope:

* a declared ``Content-Length`` over the limit is rejected before anything is read;
* every other body (chunked transfer, missing or understated ``Content-Length``)
  is counted as the application reads it, and the read fails with
  :class:`PayloadTooLargeError` as soon as the limit is crossed.

Binary uploads (catalog images) additionally enforce ``IMAGE_UPLOAD_MAX_BYTES``
on the actual bytes in the storage service.
"""

import json

from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import AppError
from app.settings import settings


class PayloadTooLargeError(AppError, StarletteHTTPException):
    """
    Raised (413) while reading a request body that exceeds the configured limit.

    Also an ``HTTPException`` on purpose: FastAPI turns any other exception raised while
    parsing a request body into a 400, but re-raises ``HTTPException`` untouched. Handler
    lookup follows the MRO, so the ``AppError`` envelope handler still serves it.
    """

    def __init__(self, max_bytes: int):
        self.message = _message(max_bytes)
        self.details = None
        StarletteHTTPException.__init__(self, status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=self.message)


def _message(max_bytes: int) -> str:
    if max_bytes >= 1024 * 1024:
        return f"Request body exceeds the {max_bytes // (1024 * 1024)} MB limit."
    return f"Request body exceeds the {max_bytes} byte limit."


class RequestBodyLimitMiddleware:
    """Reject over-limit request bodies, whether declared (``Content-Length``) or streamed (chunked)."""

    def __init__(self, app: ASGIApp, max_bytes: int | None = None):
        self.app = app
        self.max_bytes = max_bytes if max_bytes is not None else settings.REQUEST_BODY_MAX_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _declared_length(scope)
        if declared is not None and declared > self.max_bytes:
            await self._reject(send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise PayloadTooLargeError(self.max_bytes)
            return message

        await self.app(scope, limited_receive, send)

    async def _reject(self, send: Send) -> None:
        body = json.dumps(
            {
                "error": {
                    "type": "payload_too_large",
                    "message": _message(self.max_bytes),
                    "status_code": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                }
            }
        ).encode()

        await send(
            {
                "type": "http.response.start",
                "status": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", ()):
        if name == b"content-length":
            text = value.decode("latin-1").strip()
            return int(text) if text.isdigit() else None

    return None
