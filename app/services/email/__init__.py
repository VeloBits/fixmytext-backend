"""Email sending — provider-agnostic facade.

Auth code should import from ``app.services.email.flows`` only. The backend
selection and low-level sender live here so swapping providers (e.g. adding
Resend/SES later) means adding one file, not touching call sites.
"""

from functools import lru_cache

from app.core.config import settings
from app.services.email.console_backend import ConsoleEmailSender
from app.services.email.sender import EmailMessage, EmailSender
from app.services.email.smtp_backend import SmtpEmailSender


@lru_cache(maxsize=1)
def get_email_sender() -> EmailSender:
    """Return the process-wide email sender instance.

    Selection:
      - EMAIL_BACKEND == "console" → ConsoleEmailSender
      - EMAIL_BACKEND == "smtp"    → SmtpEmailSender
      - EMAIL_BACKEND == "auto"    → smtp if SMTP_HOST is set, else console
    """
    backend = (settings.EMAIL_BACKEND or "auto").lower()
    if backend == "console":
        return ConsoleEmailSender()
    if backend == "smtp":
        return SmtpEmailSender()
    # auto
    if settings.SMTP_HOST:
        return SmtpEmailSender()
    return ConsoleEmailSender()


__all__ = ["EmailMessage", "EmailSender", "get_email_sender"]
