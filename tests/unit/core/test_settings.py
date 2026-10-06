"""Unit tests for settings validation: JWT secret, CORS/hosts, pool budget, explicit STAGE."""

from pydantic import ValidationError
import pytest

from app.settings._common import as_async_database_url, make_engine
from app.settings.config import AppSettings
from app.settings.stage import resolve_stage

GOOD_SECRET = "s" * 48


def build(**overrides) -> AppSettings:
    """Build settings from explicit values only (ignores any ``.env`` file)."""

    values = {
        "STAGE": "prod",
        "ADMIN_LOGIN": "admin@example.com",
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_KEY": "key",
        "DATABASE_URL": "postgresql://u:p@db/x",
        "REDIS_URL": "redis://redis/0",
        "AUTH_REDIS_URL": "redis://auth-redis/0",
        "JWT_SECRET_KEY": GOOD_SECRET,
        "CORS_ORIGINS": "https://app.example.com",
        "ALLOWED_HOSTS": "api.example.com",
        "DB_POOL_SIZE": None,
        "DB_MAX_OVERFLOW": None,
        "WEB_CONCURRENCY": None,
        "DB_MAX_CONNECTIONS": 100,
    }
    values.update(overrides)
    return AppSettings(_env_file=None, **values)


@pytest.mark.unit
class TestJwtSecret:
    @pytest.mark.parametrize("stage", ["prod", "staging"])
    @pytest.mark.parametrize("secret", ["secret", "SECRET", "your_jwt_secret_key", "changeme", ""])
    def test_placeholder_secret_is_rejected_in_prod_like_stages(self, stage, secret):
        with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
            build(STAGE=stage, JWT_SECRET_KEY=secret)

    def test_the_default_secret_is_rejected_when_unset(self, monkeypatch):
        """Pydantic does not validate defaults; the model validator must still catch the placeholder."""

        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

        with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
            AppSettings(
                _env_file=None,
                STAGE="prod",
                ADMIN_LOGIN="a",
                SUPABASE_URL="u",
                SUPABASE_KEY="k",
                DATABASE_URL="d",
                REDIS_URL="r",
                CORS_ORIGINS="https://a.example.com",
                ALLOWED_HOSTS="a.example.com",
            )

    def test_short_secret_is_rejected_in_prod(self):
        with pytest.raises(ValidationError, match="at least 32"):
            build(JWT_SECRET_KEY="x" * 31)

    def test_good_secret_is_accepted(self):
        assert build().JWT_SECRET_KEY == GOOD_SECRET

    @pytest.mark.parametrize("stage", ["dev", "test"])
    def test_placeholder_is_fine_in_dev_and_test(self, stage):
        assert build(STAGE=stage, JWT_SECRET_KEY="secret").JWT_SECRET_KEY == "secret"


@pytest.mark.unit
class TestCorsAndHosts:
    def test_lists_are_parsed_from_comma_separated_text(self):
        settings = build(
            CORS_ORIGINS=" https://a.example.com, https://b.example.com/ ", ALLOWED_HOSTS="a.example.com,b.example.com"
        )

        assert settings.CORS_ORIGINS == ["https://a.example.com", "https://b.example.com"]
        assert settings.ALLOWED_HOSTS == ["a.example.com", "b.example.com"]

    def test_json_array_is_accepted(self):
        assert build(ALLOWED_HOSTS='["a.example.com"]').ALLOWED_HOSTS == ["a.example.com"]

    @pytest.mark.parametrize(
        "value", ["", "*", "https://a.example.com,*", "app.example.com", "https://a.example.com/path"]
    )
    def test_invalid_cors_origins_fail_in_prod(self, value):
        with pytest.raises(ValidationError, match="CORS_ORIGINS"):
            build(CORS_ORIGINS=value)

    @pytest.mark.parametrize("value", ["", "*", "https://api.example.com", "api.example.com/x"])
    def test_invalid_allowed_hosts_fail_in_prod(self, value):
        with pytest.raises(ValidationError, match="ALLOWED_HOSTS"):
            build(ALLOWED_HOSTS=value)

    def test_staging_is_validated_like_prod(self):
        with pytest.raises(ValidationError, match="ALLOWED_HOSTS"):
            build(STAGE="staging", ALLOWED_HOSTS="")

    @pytest.mark.parametrize("stage", ["dev", "test"])
    def test_dev_and_test_default_to_wildcards(self, stage):
        settings = build(STAGE=stage, CORS_ORIGINS="", ALLOWED_HOSTS="")

        assert settings.CORS_ORIGINS == ["*"]
        assert settings.ALLOWED_HOSTS == ["*"]

    def test_cors_and_hosts_are_independent(self):
        settings = build()

        assert settings.CORS_ORIGINS == ["https://app.example.com"]
        assert settings.ALLOWED_HOSTS == ["api.example.com"]


@pytest.mark.unit
class TestPoolBudget:
    def test_prod_defaults_fit_postgres_max_connections(self):
        settings = build()

        assert settings.WEB_CONCURRENCY * (settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW) <= 90

    def test_oversized_pool_is_rejected_in_prod(self):
        with pytest.raises(ValidationError, match="connection budget"):
            build(DB_POOL_SIZE=20, DB_MAX_OVERFLOW=40, WEB_CONCURRENCY=4)

    def test_budget_scales_with_db_max_connections(self):
        settings = build(DB_POOL_SIZE=20, DB_MAX_OVERFLOW=40, WEB_CONCURRENCY=4, DB_MAX_CONNECTIONS=300)

        assert settings.DB_POOL_SIZE == 20

    def test_dev_is_not_budget_checked(self):
        assert build(STAGE="dev", DB_POOL_SIZE=50, DB_MAX_OVERFLOW=50, WEB_CONCURRENCY=8).DB_POOL_SIZE == 50

    def test_stage_defaults_are_applied(self):
        assert build(STAGE="dev").WEB_CONCURRENCY == 1
        assert build(STAGE="prod").WEB_CONCURRENCY == 4


@pytest.mark.unit
class TestStageResolution:
    def test_defaults_to_dev_locally(self):
        assert resolve_stage({}) == "dev"

    def test_explicit_stage_is_lowercased(self):
        assert resolve_stage({"STAGE": "PROD"}) == "prod"

    def test_missing_stage_fails_when_explicit_stage_is_required(self):
        with pytest.raises(RuntimeError, match="STAGE is not set"):
            resolve_stage({"REQUIRE_EXPLICIT_STAGE": "true"})

    def test_present_stage_satisfies_the_requirement(self):
        assert resolve_stage({"REQUIRE_EXPLICIT_STAGE": "1", "STAGE": "staging"}) == "staging"

    def test_unknown_stage_is_rejected(self):
        with pytest.raises(ValueError, match="Invalid STAGE"):
            resolve_stage({"STAGE": "qa"})


@pytest.mark.unit
class TestDatabaseUrlAndEngine:
    def test_plain_url_gets_the_asyncpg_driver(self):
        assert as_async_database_url("postgres://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"

    def test_sslmode_is_translated_and_channel_binding_dropped(self):
        url = as_async_database_url("postgresql://u:p@h/db?sslmode=require&channel_binding=require")

        assert url == "postgresql+asyncpg://u:p@h/db?ssl=require"

    def test_asyncpg_url_is_kept(self):
        assert as_async_database_url("postgresql+asyncpg://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"

    def test_make_engine_applies_pool_and_timeout_options(self):
        engine = make_engine(
            "postgresql://u:p@h/db", pool_size=3, max_overflow=2, hide_parameters=True, command_timeout=45
        )

        assert engine.pool.size() == 3
        assert engine.pool._max_overflow == 2
        assert engine.sync_engine.hide_parameters is True


@pytest.mark.unit
class TestAuthRedis:
    @pytest.mark.parametrize("stage", ["prod", "staging"])
    @pytest.mark.parametrize("url", ["", "redis://redis/0"])
    def test_prod_like_stages_need_a_distinct_auth_redis(self, stage, url):
        with pytest.raises(ValidationError, match="AUTH_REDIS_URL"):
            build(STAGE=stage, AUTH_REDIS_URL=url)

    def test_dev_may_share_the_cache_redis(self):
        assert build(STAGE="dev", AUTH_REDIS_URL="").AUTH_REDIS_URL == ""


@pytest.mark.unit
class TestSmtpHint:
    def test_missing_smtp_in_prod_logs_a_warning(self, caplog):
        with caplog.at_level("WARNING"):
            build(SMTP_HOST="", SMTP_FROM="")

        assert "password-reset emails will not be delivered" in caplog.text

    def test_configured_smtp_is_silent(self, caplog):
        with caplog.at_level("WARNING"):
            build(SMTP_HOST="smtp.example.com", SMTP_FROM="no-reply@example.com")

        assert "password-reset" not in caplog.text


@pytest.mark.unit
class TestEnvironmentParsing:
    def test_comma_separated_environment_values_are_parsed(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "https://a.example.com, https://b.example.com/")
        monkeypatch.setenv("ALLOWED_HOSTS", "api.example.com,admin.example.com")
        monkeypatch.setenv("JWT_SECRET_KEY", GOOD_SECRET)

        settings = AppSettings(
            _env_file=None,
            STAGE="prod",
            ADMIN_LOGIN="a",
            SUPABASE_URL="u",
            SUPABASE_KEY="k",
            DATABASE_URL="d",
            REDIS_URL="r",
            AUTH_REDIS_URL="a",
        )

        assert settings.CORS_ORIGINS == ["https://a.example.com", "https://b.example.com"]
        assert settings.ALLOWED_HOSTS == ["api.example.com", "admin.example.com"]
