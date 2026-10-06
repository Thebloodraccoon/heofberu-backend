"""Unit tests for the SMTP password-reset mailer (no network)."""

from unittest.mock import AsyncMock

import pytest

from app.core.email.service import EmailService
from app.settings import settings


@pytest.mark.unit
@pytest.mark.asyncio
class TestSendPasswordReset:
    async def test_link_uses_the_configured_frontend_url_and_quotes_the_token(self, monkeypatch):
        monkeypatch.setattr(settings, "FRONTEND_RESET_URL", "https://app.example.com/reset", raising=False)
        sent = AsyncMock()
        monkeypatch.setattr("app.core.email.service.aiosmtplib.send", sent)

        result = await EmailService().send_password_reset("user@example.com", "a b&c")

        assert result is True
        message = sent.await_args.args[0]
        assert "https://app.example.com/reset?token=a%20b%26c" in message.get_content()
        assert message["To"] == "user@example.com"

    async def test_smtp_failure_is_reported_as_false_not_raised(self, monkeypatch):
        monkeypatch.setattr("app.core.email.service.aiosmtplib.send", AsyncMock(side_effect=OSError("smtp down")))

        assert await EmailService().send_password_reset("user@example.com", "token") is False
