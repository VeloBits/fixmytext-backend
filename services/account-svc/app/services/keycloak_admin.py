"""Thin Keycloak Admin API client.

Uses the admin-cli client with KEYCLOAK_ADMIN credentials (password grant)
to obtain an admin token. Token is cached for its lifetime to avoid hammering
the token endpoint on every request.
"""

import logging
import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_TOKEN_CACHE: dict = {}  # {"token": str, "expires_at": float}


async def _get_admin_token() -> str:
    """Return a cached admin token, refreshing if expired."""
    now = time.time()
    if _TOKEN_CACHE.get("token") and _TOKEN_CACHE.get("expires_at", 0) > now + 30:
        return _TOKEN_CACHE["token"]

    url = f"{settings.KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url,
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": settings.KEYCLOAK_ADMIN,
                "password": settings.KEYCLOAK_ADMIN_PASSWORD,
            },
        )
        if resp.status_code != 200:
            # Avoid leaking Keycloak response body (may contain sensitive info).
            raise RuntimeError(
                f"Keycloak admin auth failed with status {resp.status_code}"
            )
        data = resp.json()

    _TOKEN_CACHE["token"] = data["access_token"]
    _TOKEN_CACHE["expires_at"] = now + data.get("expires_in", 60)
    return _TOKEN_CACHE["token"]


async def create_keycloak_user(email: str, password: str, display_name: str) -> str:
    """Create a user in Keycloak and return the new user's Keycloak ID.

    Raises:
        ValueError: if email already exists (409)
        RuntimeError: on unexpected Keycloak errors
    """
    token = await _get_admin_token()
    url = f"{settings.KEYCLOAK_URL}/admin/realms/{settings.KEYCLOAK_REALM}/users"

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={
                "username": email,
                "email": email,
                "firstName": display_name,
                "enabled": True,
                "emailVerified": False,
                "credentials": [
                    {
                        "type": "password",
                        "value": password,
                        "temporary": False,
                    }
                ],
            },
        )

    if resp.status_code == 409:
        raise ValueError("An account with this email already exists.")
    if resp.status_code != 201:
        # Log status only — avoid including resp.text which may contain PII.
        raise RuntimeError(
            f"Keycloak user creation failed with status {resp.status_code}"
        )

    # Keycloak returns the user URL in the Location header
    location = resp.headers.get("Location", "")
    keycloak_id = location.rstrip("/").split("/")[-1]
    logger.info("Created Keycloak user id=%s email=%s", keycloak_id, email)
    return keycloak_id


async def send_verification_email(keycloak_user_id: str) -> None:
    """Send Keycloak's built-in email-verification email to the user."""
    token = await _get_admin_token()
    url = (
        f"{settings.KEYCLOAK_URL}/admin/realms/{settings.KEYCLOAK_REALM}"
        f"/users/{keycloak_user_id}/send-verify-email"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.put(
            url,
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code not in (200, 204):
        logger.warning("Failed to send verification email: %s", resp.text)
