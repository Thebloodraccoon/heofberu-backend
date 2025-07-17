import aiosmtplib
from email.message import EmailMessage

from app.mail.settings import mail_settings


async def send_email_async(email_to: str, subject: str, body: str):
    message = EmailMessage()
    message["From"] = mail_settings.MAIL_FROM
    message["To"] = email_to
    message["Subject"] = subject
    message.set_content(body)

    await aiosmtplib.send(
        message,
        hostname=mail_settings.MAIL_SERVER,
        port=mail_settings.MAIL_PORT,
        username=mail_settings.MAIL_USERNAME,
        password=mail_settings.MAIL_PASSWORD,
        start_tls=True,
    )
