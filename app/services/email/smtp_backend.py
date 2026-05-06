"""SMTP backend — async sending via ``aiosmtplib``.

Works with any dev-friendly SMTP target: Mailtrap Sandbox, Mailpit, Ethereal,
or a local relay. Credentials come from settings; nothing here is provider-
specific.

All exceptions are caught and logged. A dead mail server must not break the
signup or password-reset flows that call into this backend.
"""

import logging
from email.message import EmailMessage as MimeMessage

import aiosmtplib

from app.core.config import settings
from app.services.email.sender import EmailMessage

logger = logging.getLogger(__name__)


def _build_mime(message: EmailMessage, sender: str) -> MimeMessage:
    mime = MimeMessage()
    mime["From"] = sender
    mime["To"] = message.to
    mime["Subject"] = message.subject
    mime.set_content(message.text)
    mime.add_alternative(message.html, subtype="html")
    return mime


class SmtpEmailSender:
    async def send(self, message: EmailMessage) -> None:
        sender = settings.EMAIL_FROM
        mime = _build_mime(message, sender)
        try:
            await aiosmtplib.send(
                mime,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USERNAME or None,
                password=settings.SMTP_PASSWORD or None,
                start_tls=settings.SMTP_USE_TLS,
                timeout=settings.SMTP_TIMEOUT_SECONDS,
            )
        except Exception:
            # Mail delivery failures are logged but never surfaced — the
            # caller (signup, forgot-password) would otherwise fail for
            # every user whenever the SMTP host is down.
            logger.exception(
                "SMTP send failed host=%s to=%s subject=%s",
                settings.SMTP_HOST,
                message.to,
                message.subject,
            )
            return
        logger.info("SMTP EMAIL sent to=%s subject=%s", message.to, message.subject)
