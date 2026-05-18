"""Standard error envelopes used by services that opt in."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Single error item — machine-readable code + human-readable message."""

    code: str
    message: str
    field: str | None = None


class HTTPErrorEnvelope(BaseModel):
    """Top-level error envelope. Wraps one or more ``ErrorResponse`` items."""

    errors: list[ErrorResponse]
    request_id: str | None = None
