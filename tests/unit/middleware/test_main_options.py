"""Unit tests for the app assembly in ``app.main``: uvicorn options and the middleware stack order."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import pytest

pytest.importorskip("sqlalchemy_utils", reason="app.main imports the full model graph")

from app.main import setup_middleware, uvicorn_options  # noqa: E402
from app.middleware import RequestBodyLimitMiddleware, SecurityHeadersMiddleware  # noqa: E402
from app.settings import settings  # noqa: E402


@pytest.mark.unit
class TestUvicornOptions:
    def test_proxy_headers_are_trusted_only_for_configured_proxies(self, monkeypatch):
        monkeypatch.setattr(settings, "FORWARDED_ALLOW_IPS", "10.0.0.0/8", raising=False)

        options = uvicorn_options()

        assert options["proxy_headers"] is True
        assert options["forwarded_allow_ips"] == "10.0.0.0/8"

    def test_prod_uses_the_configured_worker_count(self, monkeypatch):
        monkeypatch.setattr(settings, "STAGE", "prod")
        monkeypatch.setattr(settings, "WEB_CONCURRENCY", 3, raising=False)

        options = uvicorn_options()

        assert options["workers"] == 3
        assert options["reload"] is False
        assert options["access_log"] is False

    def test_dev_runs_one_reloading_worker(self, monkeypatch):
        monkeypatch.setattr(settings, "STAGE", "dev")

        options = uvicorn_options()

        assert options["workers"] == 1
        assert options["reload"] is True


@pytest.mark.unit
class TestMiddlewareStack:
    def build(self, monkeypatch, stage):
        monkeypatch.setattr(settings, "STAGE", stage)
        monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://app.example.com"], raising=False)
        monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["api.example.com"], raising=False)
        app = FastAPI()
        setup_middleware(app)
        return [entry.cls for entry in app.user_middleware]

    def test_cors_is_outermost_and_security_headers_sit_just_below_it(self, monkeypatch):
        stack = self.build(monkeypatch, "prod")

        assert stack[0] is CORSMiddleware
        assert stack[1] is SecurityHeadersMiddleware

    def test_body_limit_is_innermost(self, monkeypatch):
        assert self.build(monkeypatch, "prod")[-1] is RequestBodyLimitMiddleware

    def test_trusted_host_only_in_prod_like_stages(self, monkeypatch):
        assert TrustedHostMiddleware in self.build(monkeypatch, "prod")
        assert TrustedHostMiddleware not in self.build(monkeypatch, "dev")
