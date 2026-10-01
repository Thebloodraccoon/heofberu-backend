"""Unit tests for MiddlewareConfig: per-stage rate limits and route rules."""

import pytest

from app.middleware.config import MiddlewareConfig
from app.settings import settings


@pytest.mark.unit
class TestGetRateLimitConfig:
    def test_dev_budget(self, monkeypatch):
        monkeypatch.setattr(settings, "STAGE", "dev")
        cfg = MiddlewareConfig.get_rate_limit_config()
        assert cfg["calls"] == 200
        assert cfg["period"] == 60

    def test_staging_budget(self, monkeypatch):
        monkeypatch.setattr(settings, "STAGE", "staging")
        cfg = MiddlewareConfig.get_rate_limit_config()
        assert cfg["calls"] == 100
        assert cfg["period"] == 60

    def test_prod_budget(self, monkeypatch):
        monkeypatch.setattr(settings, "STAGE", "prod")
        cfg = MiddlewareConfig.get_rate_limit_config()
        assert cfg["calls"] == 60
        assert cfg["period"] == 60

    def test_unknown_stage_falls_back_to_prod(self, monkeypatch):
        monkeypatch.setattr(settings, "STAGE", "bogus")
        cfg = MiddlewareConfig.get_rate_limit_config()
        assert cfg["calls"] == 60

    def test_config_carries_rules_and_stage(self, monkeypatch):
        monkeypatch.setattr(settings, "STAGE", "prod")
        cfg = MiddlewareConfig.get_rate_limit_config()
        assert "rules" in cfg
        assert cfg["stage"] == "prod"


@pytest.mark.unit
class TestGetRouteRules:
    def test_auth_login_is_most_strict_and_first(self):
        rules = MiddlewareConfig.get_route_rules()
        assert rules[0]["path"] == "/api/auth/login"
        assert rules[0]["prod"] == 10
        assert rules[0]["dev"] == 30

    def test_every_rule_has_a_distinct_bucket(self):
        buckets = [r["bucket"] for r in MiddlewareConfig.get_route_rules()]
        assert len(buckets) == len(set(buckets))

    def test_auth_register_has_anti_spam_budget(self):
        rules = {r["bucket"]: r for r in MiddlewareConfig.get_route_rules()}
        assert rules["auth-register"]["prod"] == 5
        assert rules["auth-register"]["dev"] == 20

    def test_image_rule_is_a_put_suffix(self):
        rules = {r["bucket"]: r for r in MiddlewareConfig.get_route_rules()}
        assert rules["image"]["method"] == "PUT"
        assert rules["image"]["suffix"] is True
        assert rules["image"]["prod"] == 5

    def test_article_image_upload_has_its_own_post_suffix_bucket(self):
        rules = {r["bucket"]: r for r in MiddlewareConfig.get_route_rules()}
        assert rules["article-image"]["method"] == "POST"
        assert rules["article-image"]["suffix"] is True
        assert rules["article-image"]["path"] == "/images"
        assert rules["article-image"]["prod"] == 20

    def test_search_rules_require_search_param(self):
        rules = {r["bucket"]: r for r in MiddlewareConfig.get_route_rules()}
        for bucket in ("search-spells", "search-feats", "search-features"):
            assert rules[bucket]["search"] is True
            assert rules[bucket]["method"] == "GET"
            assert rules[bucket]["prod"] == 20


@pytest.mark.unit
class TestCorsConfig:
    def test_origins_come_from_cors_origins_not_allowed_hosts(self, monkeypatch):
        monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://app.example.com"], raising=False)
        monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["api.example.com"], raising=False)

        cfg = MiddlewareConfig.get_cors_config()

        assert cfg["allow_origins"] == ["https://app.example.com"]
        assert cfg["allow_credentials"] is True

    def test_wildcard_disables_credentials(self, monkeypatch):
        monkeypatch.setattr(settings, "CORS_ORIGINS", ["*"], raising=False)

        cfg = MiddlewareConfig.get_cors_config()

        assert cfg["allow_origins"] == ["*"]
        assert cfg["allow_credentials"] is False

    def test_no_stale_token_refresh_headers_are_exposed(self, monkeypatch):
        monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://app.example.com"], raising=False)

        exposed = MiddlewareConfig.get_cors_config()["expose_headers"]

        assert exposed == ["X-Process-Time", "X-Request-ID"]


@pytest.mark.unit
class TestTrustedHostConfig:
    @pytest.mark.parametrize("stage", ["prod", "staging"])
    def test_prod_like_stages_use_allowed_hosts_plus_internal_probe_hosts(self, monkeypatch, stage):
        monkeypatch.setattr(settings, "STAGE", stage)
        monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["api.example.com"], raising=False)

        hosts = MiddlewareConfig.get_trusted_host_config()["allowed_hosts"]

        assert hosts == ["api.example.com", "localhost", "127.0.0.1"]

    def test_dev_accepts_any_host(self, monkeypatch):
        monkeypatch.setattr(settings, "STAGE", "dev")
        monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["api.example.com"], raising=False)

        assert MiddlewareConfig.get_trusted_host_config() == {"allowed_hosts": ["*"]}

    def test_trusted_host_middleware_only_in_prod_like_stages(self, monkeypatch):
        for stage, enabled in (("prod", True), ("staging", True), ("dev", False), ("test", False)):
            monkeypatch.setattr(settings, "STAGE", stage)
            assert MiddlewareConfig.should_enable_middleware("trusted_host") is enabled


@pytest.mark.unit
class TestHealthPaths:
    def test_skip_paths_use_the_real_api_prefix(self, monkeypatch):
        monkeypatch.setattr(settings, "STAGE", "prod")

        rate = MiddlewareConfig.get_rate_limit_config()["skip_paths"]
        logs = MiddlewareConfig.get_observability_config()["log_skip_paths"]

        assert "/api/ping" in rate
        assert "/api/ping" in logs
        assert "/ping" not in rate

    def test_slow_requests_are_logged_in_every_stage(self, monkeypatch):
        for stage in ("dev", "staging", "prod"):
            monkeypatch.setattr(settings, "STAGE", stage)
            assert MiddlewareConfig.get_observability_config()["log_slow_requests"] is True
