"""Default dev backend — logs the message instead of sending.

Preserves today's "grep the backend logs for the verification URL" workflow.
Selected when no SMTP host is configured.
"""

import logging
import re

from app.services.email.sender import EmailMessage

logger = logging.getLogger(__name__)

# Pull the first http(s) URL out of the plaintext body so the log line
# surfaces the actionable link even when the body is long.
_URL_RE = re.compile(r"https?://\S+")


class ConsoleEmailSender:
    async def send(self, message: EmailMessage) -> None:
        match = _URL_RE.search(message.text)
        link = match.group(0) if match else "(no link in body)"
        logger.info(
            "CONSOLE EMAIL to=%s subject=%s link=%s",
            message.to,
            message.subject,
            link,
        )
