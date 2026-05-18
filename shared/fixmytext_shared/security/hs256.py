"""HS256 JWT adapter. Active during the strangler-fig transition to Keycloak."""

from typing import Any

import jwt


def verify(token: str, secret: str) -> dict[str, Any]:
    """Decode + validate an HS256 JWT.

    Raises ``jwt.PyJWTError`` on invalid signature, expired token, or
    malformed payload. Caller is responsible for further claim checks
    (``type``, ``sub`` shape, etc.).
    """
    return jwt.decode(token, secret, algorithms=["HS256"])
