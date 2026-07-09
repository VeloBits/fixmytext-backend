"""Thin Keycloak Admin API client.

Obtains an admin token using either:
  1. Dedicated service account (preferred): client_credentials grant in the
     product realm when KEYCLOAK_SERVICE_ACCOUNT_ID + _SECRET are set.
     The service account is created by bootstrap.sh with the manage-users role.
  2. Master-realm admin-cli (fallback): password grant using KEYCLOAK_ADMIN +
     KEYCLOAK_ADMIN_PASSWORD. Used when the service account is not yet set up.

Token is cached for its lifetime to avoid hammering the token endpoint.
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
    # Fast path: skip lock acquisition when the token is still fresh (common case).
    if _TOKEN_CACHE.get("token") and _TOKEN_CACHE.get("expires_at", 0) > now + 30:
        return _TOKEN_CACHE["token"]
    async with _TOKEN_LOCK:
        if _TOKEN_CACHE.get("token") and _TOKEN_CACHE.get("expires_at", 0) > now + 30:
            return _TOKEN_CACHE["token"]

    # Fetch outside the lock — concurrent coroutines may all fetch here, but
    # only one will write (second lock below).
    if (
        settings.KEYCLOAK_SERVICE_ACCOUNT_ID
        and settings.KEYCLOAK_SERVICE_ACCOUNT_SECRET
    ):
        # Preferred: dedicated service account with minimal permissions.
        url = f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/token"
        token_data: dict = {
            "grant_type": "client_credentials",
            "client_id": settings.KEYCLOAK_SERVICE_ACCOUNT_ID,
            "client_secret": settings.KEYCLOAK_SERVICE_ACCOUNT_SECRET,
        }
    else:
        # Fallback: master-realm admin-cli (used before bootstrap creates the SA).
        url = f"{settings.KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
        token_data = {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": settings.KEYCLOAK_ADMIN,
            "password": settings.KEYCLOAK_ADMIN_PASSWORD,
        }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, data=token_data)
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Keycloak admin auth failed: network error — {exc}"
        ) from exc
    if resp.status_code != 200:
        # Avoid leaking Keycloak response body (may contain sensitive info).
        raise RuntimeError(f"Keycloak admin auth failed with status {resp.status_code}")
    data = resp.json()
    token_value = data.get("access_token")
    if not token_value:
        raise RuntimeError(
            "Keycloak admin auth succeeded but response contains no access_token"
        )
    now = time.time()  # recalculate after HTTP round-trip
    async with _TOKEN_LOCK:
        # Double-check: another coroutine may have refreshed while we fetched.
        if not (
            _TOKEN_CACHE.get("token") and _TOKEN_CACHE.get("expires_at", 0) > now + 30
        ):
            _TOKEN_CACHE["token"] = token_value
            _TOKEN_CACHE["expires_at"] = now + data.get("expires_in", 60)
    return _TOKEN_CACHE["token"]


async def send_verification_email(keycloak_user_id: str) -> None:
    """Send Keycloak's built-in email-verification email to the user.

    Passes client_id + redirect_uri so Keycloak generates a verification link
    that redirects back to the frontend app instead of the default account
    console. Without these, Keycloak falls back to the account client which
    may not have the frontend URL in its allowed redirect URIs.
    """
    token = await _get_admin_token()
    url = (
        f"{settings.KEYCLOAK_URL}/admin/realms/{settings.KEYCLOAK_REALM}"
        f"/users/{keycloak_user_id}/send-verify-email"
    )
    params: dict[str, str] = {}
    if settings.KEYCLOAK_CLIENT_ID:
        params["client_id"] = settings.KEYCLOAK_CLIENT_ID
    if settings.FRONTEND_URL:
        params["redirect_uri"] = settings.FRONTEND_URL
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.put(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params or None,
        )
    if resp.status_code not in (200, 204):
        logger.warning("Failed to send verification email: HTTP %s", resp.status_code)
