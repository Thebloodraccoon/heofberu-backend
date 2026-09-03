"""Unit tests for the request body-size guard middleware."""

from types import SimpleNamespace

import pytest
from fastapi import Request, Response
from starlette import status
from starlette.datastructures import Headers

from app.middleware.body_limit import RequestBodyLimitMiddleware


def make_request(content_length=None):
    headers = {}
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    return SimpleNamespace(headers=Headers(headers))


async def call_next(req):
    return Response("ok")


@pytest.mark.unit
@pytest.mark.asyncio
class TestRequestBodyLimit:
    async def test_allows_body_at_or_below_limit(self):
        mw = RequestBodyLimitMiddleware(app=SimpleNamespace(), max_bytes=1024)
        resp = await mw.dispatch(make_request(content_length=1024), call_next)
        assert resp.status_code == status.HTTP_200_OK

    async def test_rejects_body_over_limit_with_413(self):
        mw = RequestBodyLimitMiddleware(app=SimpleNamespace(), max_bytes=1024)
        resp = await mw.dispatch(make_request(content_length=2048), call_next)
        assert resp.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        assert '"type":"payload_too_large"' in resp.body.decode()

    async def test_ignores_chunked_body_without_content_length(self):
        mw = RequestBodyLimitMiddleware(app=SimpleNamespace(), max_bytes=1024)
        resp = await mw.dispatch(make_request(content_length=None), call_next)
        assert resp.status_code == status.HTTP_200_OK

    async def test_ignores_invalid_content_length_value(self):
        mw = RequestBodyLimitMiddleware(app=SimpleNamespace(), max_bytes=1024)
        resp = await mw.dispatch(make_request(content_length=-5), call_next)
        assert resp.status_code == status.HTTP_200_OK
