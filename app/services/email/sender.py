"""Core email types — protocol + message shape used by every backend."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmailMessage:
    """Outbound email payload. Always carry both HTML and plaintext variants."""

    to: str
    subject: str
    html: str
    text: str


class EmailSender(Protocol):
    """Anything that can deliver an ``EmailMessage``.

    Implementations must never raise — failures should be caught and logged.
    Auth flows run sending inline with user-visible actions (signup, etc.),
    and a down mail provider must not break those.
    """

    async def send(self, message: EmailMessage) -> None: ...
