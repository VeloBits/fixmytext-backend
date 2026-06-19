"""Thin Keycloak Admin API client.

Uses the admin-cli client with KEYCLOAK_ADMIN credentials (password grant)
to obtain an admin token. Token is cached for its lifetime to avoid hammering
the token endpoint on every request.
"""

import asyncio
import logging
import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_TOKEN_CACHE: dict[str, str | float] = {}  # {"token": str, "expires_at": float}
_TOKEN_LOCK = asyncio.Lock()


async def _get_admin_token() -> str:
    """Return a cached admin token, refreshing if expired.

    Uses double-checked locking so the lock is NOT held during the HTTP
    round-trip — prevents up to timeout=10 s of head-of-line blocking when
    the cache misses under concurrent registration load.
    """
    now = time.time()
    async with _TOKEN_LOCK:
        if _TOKEN_CACHE.get("token") and _TOKEN_CACHE.get("expires_at", 0) > now + 30:
            return _TOKEN_CACHE["token"]

    # Fetch outside the lock — concurrent coroutines may all fetch here, but
    # only one will write (second lock below).
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
    token_value = data.get("access_token")
    if not token_value:
        raise RuntimeError("Keycloak admin auth succeeded but response contains no access_token")
    now = time.time()  # recalculate after HTTP round-trip
    async with _TOKEN_LOCK:
        # Double-check: another coroutine may have refreshed while we fetched.
        if not (_TOKEN_CACHE.get("token") and _TOKEN_CACHE.get("expires_at", 0) > now + 30):
            _TOKEN_CACHE["token"] = token_value
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

    # Keycloak returns the new user URL in the Location header; the last
    # path segment is the UUID. An absent or malformed header means silent data corruption.
    location = resp.headers.get("Location", "")
    keycloak_id = location.rstrip("/").split("/")[-1]
    if not keycloak_id:
        raise RuntimeError(
            "Keycloak returned 201 but no Location header — cannot extract user ID"
        )
    try:
        import uuid as _uuid
        _uuid.UUID(keycloak_id)
    except ValueError:
        raise RuntimeError(
            f"Keycloak returned 201 but Location header contains invalid UUID: {keycloak_id!r}"
        )
    # Sanitize email before logging — user-provided value; strip \r\n to prevent log injection.
    safe_email = email.replace("\r", "").replace("\n", "")
    logger.info("Created Keycloak user id=%s", keycloak_id)
    return keycloak_id


async def send_verification_email(keycloak_user_id: str) -> None:
    """Send Keycloak's built-in email-verification email to the user."""
    token = await _get_admin_token()
    url = (
        f"{settings.KEYCLOAK_URL}/admin/realms/{settings.KEYCLOAK_REALM}"
        f"/users/{keycloak_user_id}/send-verify-email"
    )
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.put(
            url,
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code not in (200, 204):
        logger.warning("Failed to send verification email: HTTP %s", resp.status_code)
