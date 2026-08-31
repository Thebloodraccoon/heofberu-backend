"""Async email-sending service (SMTP via aiosmtplib)."""

import logging
from email.message import EmailMessage

import aiosmtplib

from app.settings import settings

logger = logging.getLogger(__name__)

# Hardcoded frontend reset page for now. The backend appends the reset
# token to this base and emails the resulting link; this keeps the backend
# from depending on a runtime-supplied redirect while the frontend domain
# is still being finalized.
RESET_BASE_URL = "https://heofberu-frontend.vercel.app/reset-password"


class EmailService:
    """
    Thin wrapper around ``aiosmtplib`` for sending password-reset emails.

    Sending is best-effort by design: a failed SMTP round-trip logs the
    error but does not propagate, so the password-reset endpoint can reply
    to the caller identically whether or not the account exists (avoiding
    account enumeration).
    """

    async def send_password_reset(self, to_email: str, reset_token: str) -> bool:
        """Send the password-reset email for ``to_email``, linking to the reset page with ``reset_token``."""

        reset_url = f"{RESET_BASE_URL}?token={reset_token}"

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

        await self._send(message, to_email=to_email)
        return True

    async def _send(self, message: EmailMessage, *, to_email: str) -> None:
        """Deliver ``message`` via SMTP (TLS), logging but never raising on failure."""

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
