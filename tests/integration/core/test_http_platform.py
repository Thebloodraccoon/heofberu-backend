"""HTTP-level checks of the platform layer: error envelope, security headers, body limit."""

import pytest

from app.settings import settings


@pytest.mark.integration
@pytest.mark.asyncio
class TestErrorEnvelope:
    async def test_request_validation_error_uses_the_envelope_and_never_echoes_input(self, client):
        response = await client.post("/auth/login", json={"password": "TopSecret-123"})

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["type"] == "RequestValidationError"
        assert error["details"]["validation_errors"]
        assert "TopSecret-123" not in response.text
        assert "detail" not in response.json()

    async def test_unknown_route_uses_the_envelope(self, client):
        response = await client.get("/definitely-not-a-route")

        assert response.status_code == 404
        assert response.json()["error"]["status_code"] == 404

    async def test_error_responses_carry_a_request_id(self, client):
        response = await client.get("/definitely-not-a-route")

        assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestSecurityHeaders:
    async def test_ping_has_baseline_security_headers(self, client):
        response = await client.get("/ping")

        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"

    async def test_error_responses_have_security_headers_too(self, client):
        response = await client.get("/definitely-not-a-route")

        assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.integration
@pytest.mark.asyncio
class TestBodyLimit:
    async def test_declared_oversize_body_is_rejected(self, client):
        response = await client.post("/auth/login", content=b"x" * (settings.REQUEST_BODY_MAX_BYTES + 1))

        assert response.status_code == 413

    async def test_chunked_oversize_body_is_rejected(self, client):
        async def body():
            chunk = b"x" * (1024 * 1024)
            for _ in range(settings.REQUEST_BODY_MAX_BYTES // len(chunk) + 2):
                yield chunk

        response = await client.post("/auth/login", content=body(), headers={"Content-Type": "application/json"})

        assert response.status_code == 413
        assert response.json()["error"]["status_code"] == 413


@pytest.mark.integration
@pytest.mark.asyncio
class TestHealthProbeIsNotRateLimited:
    async def test_ping_has_no_rate_limit_headers(self, client):
        response = await client.get("/ping")

        assert response.status_code == 200
        assert "x-ratelimit-limit" not in response.headers
