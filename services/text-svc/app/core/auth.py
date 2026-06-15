"""Optional JWT auth for text-svc.

text-svc accepts requests with or without a Keycloak JWT. When a valid token is
present we extract the user identity so the entitlement gate treats the caller as
an authenticated user; otherwise (no token, invalid token, or no JWKS configured)
the caller is handled as an anonymous visitor. An invalid token is never an error
here — it simply downgrades to the visitor quota.
"""

import logging
from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWTError as JWTError

from app.core.config import settings

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class OptionalUser:
    """Identity extracted from a verified Keycloak JWT (no DB lookup)."""

    id: str  # Keycloak sub
    email: str
    is_email_verified: bool


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> OptionalUser | None:
    """Return an OptionalUser when a valid JWT is present, else None (visitor)."""
    if not credentials or not settings.KEYCLOAK_JWKS_URL:
        return None
    try:
        from fixmytext_shared.security.jwt import verify_jwt_raw

        payload = verify_jwt_raw(
            credentials.credentials,
            algorithm="RS256",
            jwks_url=settings.KEYCLOAK_JWKS_URL,
            audience=settings.KEYCLOAK_AUDIENCE or None,
            issuer=settings.KEYCLOAK_ISSUER or None,
        )
    except (JWTError, ValueError):
        logger.debug("text-svc: invalid token — treating request as anonymous")
        return None

    sub = payload.get("sub")
    if not sub:
        return None
    return OptionalUser(
        id=sub,
        email=payload.get("email", ""),
        is_email_verified=bool(payload.get("email_verified", False)),
    )
