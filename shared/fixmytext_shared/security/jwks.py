"""RS256 + JWKS JWT adapter.

Active in production — Keycloak issues RS256 tokens; all services verify
them via this module. Fetches the JWKS document from the issuer's
`.well-known` endpoint and caches public keys in-process. On `kid`
cache-miss the limiter forces a refresh once before failing.

``verify()`` is async: the JWKS key fetch (``urllib.request`` inside
``PyJWKClient``) is blocking network I/O. Wrapping it in
``asyncio.to_thread()`` keeps the event loop free for other requests
during the (infrequent) Keycloak round-trip on cache miss.
"""

import asyncio
import logging
from typing import Any

import jwt
from cachetools import TTLCache
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

# In-process JWK cache. Key: jwks_url; value: PyJWKClient.
# 10-minute TTL strikes a balance between (a) avoiding excess JWKS fetches
# and (b) picking up Keycloak's key rotation without manual intervention.
_JWK_CLIENT_CACHE: TTLCache[str, PyJWKClient] = TTLCache(maxsize=8, ttl=600)

# Serialises cache-refresh operations: prevents multiple coroutines from
# simultaneously popping and re-creating the same PyJWKClient on a
# cache-miss (thundering herd on key rotation / cold start).
_JWK_CACHE_LOCK = asyncio.Lock()


def _get_jwk_client(jwks_url: str) -> PyJWKClient:
    """Return a cached PyJWKClient for the given JWKS URL."""
    client = _JWK_CLIENT_CACHE.get(jwks_url)
    if client is None:
        client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=600, timeout=5)
        _JWK_CLIENT_CACHE[jwks_url] = client
    return client


async def verify(
    token: str,
    *,
    jwks_url: str,
    audience: str | None = None,
    issuer: str | None = None,
    require_audience: bool = False,
) -> dict[str, Any]:
    """Decode + validate an RS256 JWT using the issuer's JWKS document.

    When ``audience`` is ``None`` the ``aud`` claim is **not** verified.
    Pass ``require_audience=True`` to forbid that implicit fail-open: with no
    ``audience`` supplied it raises ``ValueError`` instead of accepting tokens
    for any audience. Callers should set this in production (where an empty
    ``KEYCLOAK_AUDIENCE`` is a misconfiguration, not a feature) so audience
    verification can never be silently disabled.

    Raises ``ValueError`` if ``require_audience`` is True but ``audience`` is None.
    Raises ``jwt.PyJWTError`` on signature/audience/issuer mismatch.
    Raises ``jwt.exceptions.PyJWKClientConnectionError`` if JWKS fetch fails on cache miss.
    """
    if audience is None and require_audience:
        raise ValueError(
            "jwks.verify: audience verification is required (require_audience=True) "
            "but no `audience` was provided — refusing to accept tokens for any "
            "audience. Set the audience (e.g. KEYCLOAK_AUDIENCE) or pass "
            "require_audience=False to opt out."
        )

    client = _get_jwk_client(jwks_url)
    try:
        # get_signing_key_from_jwt() may call urllib.request.urlopen() on cache
        # miss — blocking network I/O that must not run on the event loop thread.
        signing_key = await asyncio.to_thread(client.get_signing_key_from_jwt, token)
    except jwt.exceptions.PyJWKClientError:
        # kid not found in cache — drop cached client and retry once.
        # Lock prevents multiple concurrent coroutines from all racing to
        # recreate the client simultaneously (thundering herd on key rotation).
        async with _JWK_CACHE_LOCK:
            _JWK_CLIENT_CACHE.pop(jwks_url, None)
            client = _get_jwk_client(jwks_url)
        signing_key = await asyncio.to_thread(client.get_signing_key_from_jwt, token)

    options: dict[str, Any] = {}
    # Allow 30 s of clock skew between the token issuer (Keycloak) and this
    # service. leeway must be a top-level kwarg (not in options) in PyJWT 2.x.
    decode_kwargs: dict[str, Any] = {
        "key": signing_key.key,
        "algorithms": ["RS256"],
        "leeway": 30,
    }
    if audience is not None:
        decode_kwargs["audience"] = audience
    else:
        # Production safety is enforced by the require_audience=True + ValueError path above.
        # When audience=None is intentional (e.g. backchannel logout tokens whose aud is
        # client_id, not the resource-server audience), this is an explicit opt-out — log at
        # DEBUG to avoid polluting production logs with false-alarm warnings.
        logger.debug("jwks.verify: audience verification skipped (audience=None, require_audience=False)")
        options["verify_aud"] = False
    if issuer is not None:
        decode_kwargs["issuer"] = issuer
    if options:
        decode_kwargs["options"] = options

    return jwt.decode(token, **decode_kwargs)
