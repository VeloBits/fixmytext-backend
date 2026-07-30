"""Optional JWT auth for text-svc.

text-svc accepts requests with or without a Keycloak JWT. When a valid token is
present we extract the user identity so the entitlement gate treats the caller as
an authenticated user; otherwise (no token, invalid token, or no JWKS configured)
the caller is handled as an anonymous visitor. An invalid token is never an error
here - it simply downgrades to the visitor quota.
"""

import logging
from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fixmytext_shared.config.validation import is_production_like
from fixmytext_shared.security.jwt import verify_jwt_raw
from jwt.exceptions import PyJWKClientConnectionError
from jwt.exceptions import PyJWTError as JWTError

from app.core.config import settings

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

_REQUIRE_AUDIENCE = is_production_like(settings.ENVIRONMENT)


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
        payload = await verify_jwt_raw(
            credentials.credentials,
            algorithm="RS256",
            jwks_url=settings.KEYCLOAK_JWKS_URL,
            audience=settings.KEYCLOAK_AUDIENCE or None,
            issuer=settings.KEYCLOAK_ISSUER or None,
            require_audience=_REQUIRE_AUDIENCE,
        )
    except PyJWKClientConnectionError as exc:
        logger.warning(
            "text-svc: JWKS fetch failed - treating request as anonymous: %s", exc
        )
        return None
    except (JWTError, ValueError):
        logger.debug("text-svc: invalid token - treating request as anonymous")
        return None

    sub = payload.get("sub")
    if not sub:
        return None
    return OptionalUser(
        id=sub,
        email=payload.get("email", ""),
        is_email_verified=bool(payload.get("email_verified", False)),
    )
