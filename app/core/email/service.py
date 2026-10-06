"""Async email-sending service (SMTP via aiosmtplib)."""

from email.message import EmailMessage
import logging
from urllib.parse import quote

import aiosmtplib

from app.settings import settings

logger = logging.getLogger(__name__)


class EmailService:
    """
    Thin wrapper around ``aiosmtplib`` for sending password-reset emails.

    Sending is best-effort by design: a failed SMTP round-trip logs the
    error but does not propagate, so the password-reset endpoint can reply
    to the caller identically whether or not the account exists (avoiding
    account enumeration).
    """

    async def send_password_reset(self, to_email: str, reset_token: str) -> bool:
        """
        Send the password-reset email for ``to_email``, linking to ``FRONTEND_RESET_URL`` with ``reset_token``.

        Returns whether the SMTP delivery succeeded (failures are logged, never raised).
        """

        reset_url = f"{settings.FRONTEND_RESET_URL}?token={quote(reset_token, safe='')}"

        message = EmailMessage()
        message["Subject"] = "Восстановление пароля — Heofberu"
        message["From"] = settings.SMTP_FROM
        message["To"] = to_email
        message.set_content(
            "Здравствуйте!\n\n"
            "Вы запросили восстановление пароля для своей учётной записи Heofberu. "
            "Перейдите по ссылке ниже, чтобы задать новый пароль "
            "(ссылка действует 15 минут):\n\n"
            f"{reset_url}\n\n"
            "Если вы не запрашивали восстановление пароля, просто проигнорируйте это письмо.\n"
        )

        return await self._send(message, to_email=to_email)

    async def _send(self, message: EmailMessage, *, to_email: str) -> bool:
        """Deliver ``message`` via SMTP (TLS); logs and returns ``False`` instead of raising on failure."""

        try:
            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER or None,
                password=settings.SMTP_PASSWORD or None,
                use_tls=settings.SMTP_USE_TLS,
                start_tls=settings.SMTP_STARTTLS,
                timeout=15,
            )
        except Exception:  # noqa: BLE001 - SMTP failures are logged, not surfaced
            logger.exception("Failed to send email to %s", to_email)
            return False

        return True
