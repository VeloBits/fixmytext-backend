"""High-level email flows used by auth endpoints.

Each flow builds a URL from ``settings.FRONTEND_URL``, renders the template,
delegates to the configured sender, and swallows sender exceptions. Auth
code should only import from this module — it stays stable across backend
changes.
"""

import logging

from app.core.config import settings
from app.db.models import User
from app.services.email import get_email_sender
from app.services.email.sender import EmailMessage
from app.services.email.templates import password_reset_email, verification_email

logger = logging.getLogger(__name__)


def _verify_url(raw_token: str) -> str:
    return f"{settings.FRONTEND_URL}/verify-email?token={raw_token}"


def _reset_url(raw_token: str) -> str:
    return f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"


async def send_verification_email(user: User, raw_token: str) -> None:
    subject, html_body, text_body = verification_email(
        user.display_name, _verify_url(raw_token)
    )
    try:
        await get_email_sender().send(
            EmailMessage(to=user.email, subject=subject, html=html_body, text=text_body)
        )
    except Exception:
        # Belt-and-suspenders — backends already swallow, but a crash in a
        # template render or lookup should not break signup either.
        logger.exception("send_verification_email failed user=%s", user.id)


async def send_password_reset_email(user: User, raw_token: str) -> None:
    subject, html_body, text_body = password_reset_email(
        user.display_name, _reset_url(raw_token)
    )
    try:
        await get_email_sender().send(
            EmailMessage(to=user.email, subject=subject, html=html_body, text=text_body)
        )
    except Exception:
        logger.exception("send_password_reset_email failed user=%s", user.id)
