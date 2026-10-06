"""Unit tests for the security-headers middleware and the config that wires it."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest

from app.middleware.config import MiddlewareConfig
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.settings import settings


def make_client(**kwargs) -> TestClient:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, **kwargs)

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    @app.get("/custom")
    async def custom():
        return JSONResponse({"ok": True}, headers={"X-Frame-Options": "SAMEORIGIN"})

    return TestClient(app)


@pytest.mark.unit
class TestSecurityHeaders:
    def test_adds_the_baseline_headers(self):
        response = make_client().get("/ok")

        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "strict-transport-security" not in response.headers

    def test_hsts_is_opt_in(self):
        response = make_client(hsts=True).get("/ok")

        assert "max-age=" in response.headers["strict-transport-security"]

    def test_existing_headers_are_not_overwritten(self):
        response = make_client().get("/custom")

        assert response.headers["x-frame-options"] == "SAMEORIGIN"

    def test_headers_are_present_on_error_responses(self):
        response = make_client().get("/missing")

        assert response.status_code == 404
        assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.unit
class TestWiring:
    @pytest.mark.parametrize(("stage", "hsts"), [("prod", True), ("staging", True), ("dev", False), ("test", False)])
    def test_hsts_only_in_prod_like_stages(self, monkeypatch, stage, hsts):
        monkeypatch.setattr(settings, "STAGE", stage)

        assert MiddlewareConfig.get_security_headers_config() == {"hsts": hsts}

    def test_middleware_is_enabled_in_every_stage(self, monkeypatch):
        for stage in ("dev", "test", "staging", "prod"):
            monkeypatch.setattr(settings, "STAGE", stage)
            assert MiddlewareConfig.should_enable_middleware("security_headers") is True
