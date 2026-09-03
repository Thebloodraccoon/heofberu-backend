"""Unit tests for RequestIDMiddleware UUID validation."""

import uuid
from collections.abc import Callable
from types import SimpleNamespace

import pytest
from fastapi import Request, Response
from starlette import status
from starlette.datastructures import Headers

from app.middleware.request_id import RequestIDMiddleware, _UUID_RE


def _make_request(headers=None):
    return SimpleNamespace(
        url=SimpleNamespace(path="/api/test"),
        headers=Headers(headers or {}),
        state=SimpleNamespace(),
    )


async def _call_next(req):
    return Response("ok")


@pytest.mark.unit
class TestUUIDRegex:
    def test_valid_uuid_lower(self):
        assert _UUID_RE.match("550e8400-e29b-41d4-a716-446655440000")

    def test_valid_uuid_upper(self):
        assert _UUID_RE.match("550E8400-E29B-41D4-A716-446655440000")

    def test_valid_uuid_mixed(self):
        assert _UUID_RE.match("550e8400-E29b-41D4-a716-446655440000")

    def test_rejects_empty(self):
        assert not _UUID_RE.match("")

    def test_rejects_too_short(self):
        assert not _UUID_RE.match("550e8400-e29b-41d4-a716")

    def test_rejects_non_uuid_string(self):
        assert not _UUID_RE.match("not-a-uuid")

    def test_rejects_injection_attempt(self):
        assert not _UUID_RE.match("'; DROP TABLE users; --")


@pytest.mark.unit
@pytest.mark.asyncio
class TestRequestIDMiddleware:
    async def test_generates_uuid_when_no_header(self):
        middleware = RequestIDMiddleware(app=SimpleNamespace())
        request = _make_request()
        response = await middleware.dispatch(request, _call_next)

        raw_id = request.state.request_id
        assert _UUID_RE.match(raw_id)
        assert response.headers["X-Request-ID"] == raw_id

    async def test_accepts_valid_uuid_header(self):
        valid = "550e8400-e29b-41d4-a716-446655440000"
        middleware = RequestIDMiddleware(app=SimpleNamespace())
        request = _make_request(headers={"X-Request-ID": valid})
        response = await middleware.dispatch(request, _call_next)

        assert request.state.request_id == valid
        assert response.headers["X-Request-ID"] == valid

    async def test_rejects_invalid_header_and_generates_new(self):
        middleware = RequestIDMiddleware(app=SimpleNamespace())
        request = _make_request(headers={"X-Request-ID": "not-a-uuid"})
        response = await middleware.dispatch(request, _call_next)

        generated = request.state.request_id
        assert _UUID_RE.match(generated)
        assert generated != "not-a-uuid"
        assert response.headers["X-Request-ID"] == generated

    async def test_rejects_injection_attempt(self):
        middleware = RequestIDMiddleware(app=SimpleNamespace())
        request = _make_request(headers={"X-Request-ID": "'; DROP TABLE users; --"})
        response = await middleware.dispatch(request, _call_next)

        assert _UUID_RE.match(request.state.request_id)

    async def test_custom_header_name(self):
        middleware = RequestIDMiddleware(app=SimpleNamespace(), header_name="X-Correlation-ID")
        valid = str(uuid.uuid4())
        request = _make_request(headers={"X-Correlation-ID": valid})
        response = await middleware.dispatch(request, _call_next)

        assert request.state.request_id == valid
        assert response.headers["X-Correlation-ID"] == valid
