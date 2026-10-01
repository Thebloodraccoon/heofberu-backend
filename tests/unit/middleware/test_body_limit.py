"""Unit tests for the request body-size guard (declared and chunked bodies)."""

import json

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel
import pytest

from app.middleware.body_limit import PayloadTooLargeError, RequestBodyLimitMiddleware
from app.middleware.error_handler import setup_error_handlers


class Recorder:
    """Collects ASGI messages sent by the middleware and replays a scripted request body."""

    def __init__(self, chunks: list[bytes]):
        self.sent: list[dict] = []
        self._chunks = list(chunks)

    async def receive(self):
        if self._chunks:
            chunk = self._chunks.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": bool(self._chunks)}
        return {"type": "http.disconnect"}

    async def send(self, message):
        self.sent.append(message)


def scope(content_length: int | None = None, extra_headers: list | None = None) -> dict:
    headers = list(extra_headers or [])
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))
    return {"type": "http", "method": "POST", "path": "/", "headers": headers}


async def read_body(receive) -> bytes:
    body = b""
    while True:
        message = await receive()
        body += message.get("body", b"")
        if not message.get("more_body"):
            return body


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeclaredLength:
    async def test_allows_body_at_the_limit(self):
        reached = []

        async def app(scope, receive, send):
            reached.append(await read_body(receive))

        recorder = Recorder([b"x" * 1024])
        await RequestBodyLimitMiddleware(app, max_bytes=1024)(scope(1024), recorder.receive, recorder.send)

        assert reached == [b"x" * 1024]

    async def test_rejects_declared_oversize_without_reading_the_body(self):
        async def app(scope, receive, send):
            raise AssertionError("must not be reached")

        recorder = Recorder([b"x"])
        await RequestBodyLimitMiddleware(app, max_bytes=1024)(scope(2048), recorder.receive, recorder.send)

        start, body = recorder.sent
        assert start["status"] == 413
        assert json.loads(body["body"])["error"]["type"] == "payload_too_large"

    async def test_invalid_content_length_is_ignored_then_counted(self):
        async def app(scope, receive, send):
            await read_body(receive)

        recorder = Recorder([b"x" * 10])
        await RequestBodyLimitMiddleware(app, max_bytes=1024)(
            scope(extra_headers=[(b"content-length", b"abc")]), recorder.receive, recorder.send
        )

    async def test_non_http_scopes_pass_through(self):
        called = []

        async def app(scope, receive, send):
            called.append(scope["type"])

        await RequestBodyLimitMiddleware(app, max_bytes=1)({"type": "lifespan"}, None, None)

        assert called == ["lifespan"]


@pytest.mark.unit
@pytest.mark.asyncio
class TestChunkedBodies:
    async def test_chunked_body_over_the_limit_fails_while_reading(self):
        async def app(scope, receive, send):
            await read_body(receive)

        recorder = Recorder([b"x" * 600, b"x" * 600])

        with pytest.raises(PayloadTooLargeError):
            await RequestBodyLimitMiddleware(app, max_bytes=1000)(scope(), recorder.receive, recorder.send)

    async def test_understated_content_length_is_still_enforced(self):
        async def app(scope, receive, send):
            await read_body(receive)

        recorder = Recorder([b"x" * 2000])

        with pytest.raises(PayloadTooLargeError):
            await RequestBodyLimitMiddleware(app, max_bytes=1000)(scope(10), recorder.receive, recorder.send)

    async def test_chunked_body_within_the_limit_is_passed_through_intact(self):
        seen = []

        async def app(scope, receive, send):
            seen.append(await read_body(receive))

        recorder = Recorder([b"a" * 400, b"b" * 400])
        await RequestBodyLimitMiddleware(app, max_bytes=1000)(scope(), recorder.receive, recorder.send)

        assert seen == [b"a" * 400 + b"b" * 400]


@pytest.mark.unit
class TestInsideTheFullStack:
    def test_endpoint_reading_an_oversized_stream_gets_a_413_envelope(self):
        app = FastAPI()
        app.add_middleware(RequestBodyLimitMiddleware, max_bytes=100)
        setup_error_handlers(app)

        @app.post("/upload")
        async def upload(request: Request):
            return {"size": len(await request.body())}

        client = TestClient(app)

        def chunks():
            yield b"x" * 80
            yield b"x" * 80

        response = client.post("/upload", content=chunks())

        assert response.status_code == 413
        assert response.json()["error"]["type"] == "PayloadTooLargeError"

        assert client.post("/upload", content=b"x" * 50).json() == {"size": 50}

    def test_json_body_parsing_does_not_mask_the_413_as_a_400(self):
        """FastAPI converts arbitrary body-read errors into 400; the limit error must pass through."""

        class Payload(BaseModel):
            text: str

        app = FastAPI()
        app.add_middleware(RequestBodyLimitMiddleware, max_bytes=100)
        setup_error_handlers(app)

        @app.post("/json")
        async def receive_json(payload: Payload):
            return {"ok": True}

        def chunks():
            yield b'{"text": "' + b"x" * 80
            yield b"x" * 80 + b'"}'

        response = TestClient(app).post("/json", content=chunks(), headers={"Content-Type": "application/json"})

        assert response.status_code == 413
        assert response.json()["error"]["type"] == "PayloadTooLargeError"
