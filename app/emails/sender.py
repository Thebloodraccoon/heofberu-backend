from email.message import EmailMessage

import aiosmtplib

from app.settings import settings


async def send_email_async(email_to: str, subject: str, body: str):
    message = EmailMessage()
    message["From"] = settings.MAIL_FROM
    message["To"] = email_to
    message["Subject"] = subject

    message.set_content(body, subtype="html")

    if settings.MAIL_SUPPRESS_SEND:
        return

    await aiosmtplib.send(
        message,
        hostname=settings.MAIL_SERVER,
        port=settings.MAIL_PORT,
        username=settings.MAIL_USERNAME,
        password=settings.MAIL_PASSWORD,
        start_tls=settings.MAIL_START_TLS,
        use_tls=settings.MAIL_USE_TLS,
    )
