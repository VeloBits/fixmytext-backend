"""JWT verification dispatcher.

`verify_jwt()` reads the algorithm from the kwarg or the `JWT_ALGORITHM`
env var (default ``HS256``) and routes to the appropriate adapter.
Only the HS256 path is exercised today; the JWKS adapter exists for code
locality but is gated behind the ``JWT_ALGORITHM=RS256`` env flip.
"""

import os
from typing import Any, Literal

from fixmytext_shared.security import hs256, jwks
from fixmytext_shared.security.claims import ClaimSchema


def verify_jwt(
    token: str,
    *,
    algorithm: Literal["HS256", "RS256"] | None = None,
    secret: str | None = None,
    jwks_url: str | None = None,
    audience: str | None = None,
    issuer: str | None = None,
) -> ClaimSchema:
    """Verify a JWT and return a typed ClaimSchema.

    Algorithm resolution order:
      1. ``algorithm`` kwarg if provided
      2. ``JWT_ALGORITHM`` env var
      3. Default ``HS256``

    For ``HS256``: requires ``secret``. Raises ``ValueError`` if missing.
    For ``RS256``: requires ``jwks_url``. Optionally ``audience`` and
    ``issuer`` for additional validation.

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
        payload = jwks.verify(
            token, jwks_url=jwks_url, audience=audience, issuer=issuer
        )
    else:
        raise ValueError(f"verify_jwt: unsupported algorithm: {algo!r}")

    return ClaimSchema.from_payload(payload)


# Re-export raw payload helper for callers that prefer dict access
def verify_jwt_raw(
    token: str,
    *,
    algorithm: Literal["HS256", "RS256"] | None = None,
    secret: str | None = None,
    jwks_url: str | None = None,
    audience: str | None = None,
    issuer: str | None = None,
) -> dict[str, Any]:
    """Same as verify_jwt but returns the raw payload dict."""
    claims = verify_jwt(
        token,
        algorithm=algorithm,
        secret=secret,
        jwks_url=jwks_url,
        audience=audience,
        issuer=issuer,
    )
    return claims.to_dict()
