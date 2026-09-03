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

    def test_search_rules_require_search_param(self):
        rules = {r["bucket"]: r for r in MiddlewareConfig.get_route_rules()}
        for bucket in ("search-spells", "search-feats", "search-features"):
            assert rules[bucket]["search"] is True
            assert rules[bucket]["method"] == "GET"
            assert rules[bucket]["prod"] == 20
