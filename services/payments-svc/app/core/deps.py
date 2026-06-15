"""FastAPI dependencies for the payments service.

``get_current_user`` verifies the Bearer JWT via JWKS then looks up (or
JIT-provisions) the corresponding User row so downstream handlers receive
a fully-populated ORM object.
"""

import hmac
import uuid

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fixmytext_shared.security.jwt import verify_jwt_raw
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)


async def verify_internal_secret(
    x_internal_secret: str = Header(default=""),
) -> None:
    """Guard internal service-to-service endpoints with a shared secret.

    Fails closed: if ``INTERNAL_SHARED_SECRET`` is unset, every internal call is
    denied so a missing secret cannot silently expose the entitlement gate.
    """
    expected = settings.INTERNAL_SHARED_SECRET
    if not expected or not hmac.compare_digest(x_internal_secret, expected):
        raise HTTPException(status_code=401, detail="invalid internal credentials")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Verify JWT and return the authenticated User ORM object.

    Performs JIT provisioning: if the Keycloak subject has no matching row
    in the DB yet, a minimal User record is created and flushed (not
    committed) so callers can extend it within the same transaction.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = verify_jwt_raw(
            credentials.credentials,
            algorithm="RS256",
            jwks_url=settings.KEYCLOAK_JWKS_URL,
            audience=settings.KEYCLOAK_AUDIENCE or None,
            issuer=settings.KEYCLOAK_ISSUER or None,
        )
        keycloak_id = uuid.UUID(payload.get("sub"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token expired or invalid") from exc

    user = await db.scalar(select(User).where(User.keycloak_id == keycloak_id))

    if user is None:
        # JIT provisioning — create minimal user row
        email = payload.get("email", "")
        user = User(
            keycloak_id=keycloak_id,
            email=email,
            display_name=payload.get("preferred_username") or email,
            hashed_password=None,
            is_email_verified=bool(payload.get("email_verified", False)),
        )
        db.add(user)
        await db.flush()
    elif not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user
