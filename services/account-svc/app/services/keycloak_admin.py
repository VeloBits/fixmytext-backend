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
import uuid

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


async def _lookup_keycloak_user_by_email(email: str, token: str) -> str | None:
    """Return the Keycloak user ID for *email*, or None if not found / on error.

    Used as a fallback when ``create_keycloak_user`` receives 201 but the
    Location header is absent or malformed — prevents orphaning the user in
    Keycloak when the header parse fails.
    """
    url = f"{settings.KEYCLOAK_URL}/admin/realms/{settings.KEYCLOAK_REALM}/users"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params={"email": email, "exact": "true"},
            )
    except httpx.HTTPError as exc:
        logger.warning("Email-based user lookup failed (network): %s", exc)
        return None
    if resp.status_code != 200:
        logger.warning("Email-based user lookup returned HTTP %s", resp.status_code)
        return None
    users = resp.json()
    if not users:
        return None
    user_id: str = users[0].get("id", "")
    try:
        uuid.UUID(user_id)
        return user_id
    except (ValueError, TypeError):
        return None


async def create_keycloak_user(email: str, password: str, display_name: str) -> str:
    """Create a user in Keycloak and return the new user's Keycloak ID.

    Raises:
        ValueError: if email already exists (409)
        RuntimeError: on unexpected Keycloak errors (including network failures)
    """
    token = await _get_admin_token()
    url = f"{settings.KEYCLOAK_URL}/admin/realms/{settings.KEYCLOAK_REALM}/users"

    try:
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
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Keycloak user creation failed: network error — {exc}"
        ) from exc

    if resp.status_code == 409:
        raise ValueError("An account with this email already exists.")
    if resp.status_code != 201:
        # Log status only — avoid including resp.text which may contain PII.
        raise RuntimeError(
            f"Keycloak user creation failed with status {resp.status_code}"
        )

    # Keycloak returns the new user URL in the Location header; the last
    # path segment is the UUID. Fall back to an email lookup when the header is
    # absent or malformed so we don't orphan the just-created Keycloak account.
    location = resp.headers.get("Location", "")
    keycloak_id = location.rstrip("/").split("/")[-1]
    id_valid = False
    if keycloak_id:
        try:
            uuid.UUID(keycloak_id)
            id_valid = True
        except ValueError:
            logger.warning(
                "Keycloak returned 201 but Location header contains invalid UUID %r "
                "— falling back to email lookup",
                keycloak_id,
            )
    if not id_valid:
        if not keycloak_id:
            logger.warning(
                "Keycloak returned 201 but Location header is absent — falling back to email lookup"
            )
        keycloak_id = await _lookup_keycloak_user_by_email(email, token) or ""
    if not keycloak_id:
        raise RuntimeError(
            "Keycloak returned 201 but user ID could not be recovered via Location header or email lookup"
        )
    logger.info("Created Keycloak user id=%s", keycloak_id)
    return keycloak_id


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
