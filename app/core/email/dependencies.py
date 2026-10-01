"""FastAPI dependency provider for the shared email-sending service."""

from typing import Annotated

from fastapi import Depends

from app.core.email.service import EmailService


def get_email_service() -> EmailService:
    """Provide the SMTP-backed email service."""

    return EmailService()


EmailServiceDep = Annotated[EmailService, Depends(get_email_service)]
