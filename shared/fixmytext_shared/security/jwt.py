"""JWT verification dispatcher.

`verify_jwt()` reads the algorithm from the kwarg or the `JWT_ALGORITHM`
env var (default ``HS256``) and routes to the appropriate adapter.
Only the HS256 path is exercised today; the JWKS adapter exists for code
locality but is gated behind the ``JWT_ALGORITHM=RS256`` env flip.

Both ``verify_jwt`` and ``verify_jwt_raw`` are **async** because the RS256
path (``jwks.verify``) performs blocking network I/O on JWKS cache miss and
must run off the event-loop thread via ``asyncio.to_thread``. The HS256 path
is synchronous CPU work that runs inline without yielding.
"""

import os
from typing import Any, Literal

from fixmytext_shared.security import hs256, jwks
from fixmytext_shared.security.claims import ClaimSchema


async def verify_jwt(
    token: str,
    *,
    algorithm: Literal["HS256", "RS256"] | None = None,
    secret: str | None = None,
    jwks_url: str | None = None,
    audience: str | None = None,
    issuer: str | None = None,
    require_audience: bool = False,
) -> ClaimSchema:
    """Verify a JWT and return a typed ClaimSchema.

    Algorithm resolution order:
      1. ``algorithm`` kwarg if provided
      2. ``JWT_ALGORITHM`` env var
      3. Default ``HS256``

    For ``HS256``: requires ``secret``. Raises ``ValueError`` if missing.
    For ``RS256``: requires ``jwks_url``. Optionally ``audience`` and
    ``issuer`` for additional validation.

    ``require_audience`` (RS256 only) forbids the implicit "no audience =>
    skip ``aud`` verification" fail-open: when True and ``audience`` is None,
    a ``ValueError`` is raised instead of accepting any-audience tokens.
    Callers should enable it in production so audience verification cannot be
    silently disabled by an empty audience setting.

    Raises ``jwt.PyJWTError`` (or subclasses) on invalid signature,
    expired tokens, or claim mismatches.
    """
    algo = algorithm or os.getenv("JWT_ALGORITHM", "HS256").upper()

    if algo == "HS256":
        if not secret:
            raise ValueError("verify_jwt: HS256 requires `secret`")
        payload = hs256.verify(token, secret)
    elif algo == "RS256":
        if not jwks_url:
            raise ValueError("verify_jwt: RS256 requires `jwks_url`")
        payload = await jwks.verify(
            token,
            jwks_url=jwks_url,
            audience=audience,
            issuer=issuer,
            require_audience=require_audience,
        )
    else:
        raise ValueError(f"verify_jwt: unsupported algorithm: {algo!r}")

    return ClaimSchema.from_payload(payload)


# Re-export raw payload helper for callers that prefer dict access
async def verify_jwt_raw(
    token: str,
    *,
    algorithm: Literal["HS256", "RS256"] | None = None,
    secret: str | None = None,
    jwks_url: str | None = None,
    audience: str | None = None,
    issuer: str | None = None,
    require_audience: bool = False,
) -> dict[str, Any]:
    """Same as verify_jwt but returns the raw payload dict."""
    claims = await verify_jwt(
        token,
        algorithm=algorithm,
        secret=secret,
        jwks_url=jwks_url,
        audience=audience,
        issuer=issuer,
        require_audience=require_audience,
    )
    return claims.to_dict()
