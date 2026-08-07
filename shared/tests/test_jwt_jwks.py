"""JWKS + RS256 adapter tests using an in-test RSA keypair.

PyJWKClient fetches the JWKS via urllib (not httpx), so we patch its
`fetch_data` method to return the test JWKS dict directly. No network.
"""

import base64
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from fixmytext_shared.security import verify_jwt
from fixmytext_shared.security.claims import ClaimSchema
from fixmytext_shared.security.jwks import _JWK_CLIENT_CACHE
from fixmytext_shared.security.jwt import verify_jwt_raw

JWKS_URL = "http://test-keycloak:8080/realms/test/protocol/openid-connect/certs"
ISSUER = "http://test-keycloak:8080/realms/test"
AUDIENCE = "fixmytext-backend"
KID = "test-kid-1"


def _generate_keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return private_pem.decode(), public


def _int_to_b64url(n: int) -> str:
    byte_length = (n.bit_length() + 7) // 8
    return (
        base64.urlsafe_b64encode(n.to_bytes(byte_length, "big")).rstrip(b"=").decode()
    )


def _jwks_for(public_key, *, kid: str = KID) -> dict:
    numbers = public_key.public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "kid": kid,
                "n": _int_to_b64url(numbers.n),
                "e": _int_to_b64url(numbers.e),
            }
        ]
    }


def _make_token(private_pem: str, payload: dict, *, kid: str = KID) -> str:
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": kid})


def _base_payload() -> dict:
    now = datetime.now(UTC)
    return {
        "sub": "kc-user-1",
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "iat": int(now.timestamp()),
        "iss": ISSUER,
        "aud": AUDIENCE,
        "email": "a@b.com",
        "email_verified": True,
        "realm_access": {"roles": ["user"]},
    }


@pytest.fixture(autouse=True)
def _clear_jwk_cache():
    """Make sure cached PyJWKClient instances don't leak between tests."""
    _JWK_CLIENT_CACHE.clear()
    yield
    _JWK_CLIENT_CACHE.clear()


@pytest.fixture
def patched_jwk_fetch(monkeypatch):
    """Patch PyJWKClient.fetch_data to return a test JWKS dict.

    Returns (private_pem, public_key) so individual tests can sign tokens.
    """
    private_pem, public = _generate_keypair()
    jwks_dict = _jwks_for(public)

    def _fake_fetch(self):
        return jwks_dict

    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", _fake_fetch)
    return private_pem, public


class TestVerifyJwtJWKS:
    async def test_roundtrip_rs256(self, patched_jwk_fetch):
        private_pem, _ = patched_jwk_fetch
        token = _make_token(private_pem, _base_payload())
        claims = await verify_jwt(
            token,
            algorithm="RS256",
            jwks_url=JWKS_URL,
            audience=AUDIENCE,
            issuer=ISSUER,
        )
        assert isinstance(claims, ClaimSchema)
        assert claims.sub == "kc-user-1"
        assert claims.email == "a@b.com"
        assert claims.email_verified is True
        assert "user" in claims.roles
        assert claims.iss == ISSUER
        assert claims.aud == AUDIENCE

    async def test_rejects_wrong_audience(self, patched_jwk_fetch):
        private_pem, _ = patched_jwk_fetch
        token = _make_token(private_pem, _base_payload())
        with pytest.raises(jwt.InvalidAudienceError):
            await verify_jwt(
                token,
                algorithm="RS256",
                jwks_url=JWKS_URL,
                audience="wrong-audience",
                issuer=ISSUER,
            )

    async def test_rejects_wrong_issuer(self, patched_jwk_fetch):
        """Issuer is verified when passed - cross-realm tokens are rejected (BE-AUTH-01)."""
        private_pem, _ = patched_jwk_fetch
        token = _make_token(private_pem, _base_payload())
        with pytest.raises(jwt.InvalidIssuerError):
            await verify_jwt(
                token,
                algorithm="RS256",
                jwks_url=JWKS_URL,
                audience=AUDIENCE,
                issuer="http://evil-keycloak:8080/realms/other",
            )

    async def test_requires_jwks_url(self):
        with pytest.raises(ValueError, match="RS256 requires"):
            await verify_jwt("anytoken", algorithm="RS256")

    async def test_require_audience_raises_when_audience_missing(
        self, patched_jwk_fetch
    ):
        """require_audience=True forbids the implicit fail-open: no audience => error.

        Guards against an empty KEYCLOAK_AUDIENCE silently disabling ``aud``
        verification in production.
        """
        private_pem, _ = patched_jwk_fetch
        token = _make_token(private_pem, _base_payload())
        with pytest.raises(ValueError, match="audience verification is required"):
            await verify_jwt(
                token,
                algorithm="RS256",
                jwks_url=JWKS_URL,
                audience=None,
                issuer=ISSUER,
                require_audience=True,
            )

    async def test_require_audience_passes_when_audience_present(
        self, patched_jwk_fetch
    ):
        """require_audience=True with a concrete audience verifies normally."""
        private_pem, _ = patched_jwk_fetch
        token = _make_token(private_pem, _base_payload())
        claims = await verify_jwt(
            token,
            algorithm="RS256",
            jwks_url=JWKS_URL,
            audience=AUDIENCE,
            issuer=ISSUER,
            require_audience=True,
        )
        assert claims.aud == AUDIENCE
        assert claims.sub == "kc-user-1"

    async def test_missing_audience_allowed_by_default(self, patched_jwk_fetch):
        """Default (require_audience=False) preserves the lenient dev behaviour:
        with no audience supplied, the ``aud`` claim is not verified."""
        private_pem, _ = patched_jwk_fetch
        token = _make_token(private_pem, _base_payload())
        claims = await verify_jwt(
            token,
            algorithm="RS256",
            jwks_url=JWKS_URL,
            audience=None,
            issuer=ISSUER,
        )
        # Verification succeeded without an audience check; the aud claim is
        # still surfaced from the payload.
        assert claims.aud == AUDIENCE
        assert claims.sub == "kc-user-1"

    async def test_clock_skew_leeway_accepts_slightly_expired_token(
        self, patched_jwk_fetch
    ):
        """Tokens expired by up to 30 s (clock skew window) are still accepted.

        Guards against M4: multi-host deployments where Keycloak's clock is
        slightly ahead of the service clock.
        """
        private_pem, _ = patched_jwk_fetch
        now = datetime.now(UTC)
        # Token expired 20 seconds ago - within the 30 s leeway window.
        payload = _base_payload()
        payload["exp"] = int((now - timedelta(seconds=20)).timestamp())
        payload["iat"] = int((now - timedelta(minutes=5)).timestamp())
        token = _make_token(private_pem, payload)
        claims = await verify_jwt(
            token,
            algorithm="RS256",
            jwks_url=JWKS_URL,
            audience=AUDIENCE,
            issuer=ISSUER,
        )
        assert claims.sub == "kc-user-1"

    async def test_rejects_token_expired_beyond_leeway(self, patched_jwk_fetch):
        """Tokens expired by more than 30 s are rejected even with leeway."""
        private_pem, _ = patched_jwk_fetch
        now = datetime.now(UTC)
        payload = _base_payload()
        payload["exp"] = int((now - timedelta(seconds=60)).timestamp())
        payload["iat"] = int((now - timedelta(minutes=10)).timestamp())
        token = _make_token(private_pem, payload)
        with pytest.raises(jwt.ExpiredSignatureError):
            await verify_jwt(
                token,
                algorithm="RS256",
                jwks_url=JWKS_URL,
                audience=AUDIENCE,
                issuer=ISSUER,
            )


class TestJwksKeyRotation:
    async def test_kid_cache_miss_recreates_client_and_recovers(self, monkeypatch):
        """A kid missing from the cached JWKS forces a client refresh (rotation).

        PyJWKClient itself fetches twice on a kid miss (initial + internal
        refresh); serving the stale set for both exhausts the client and
        triggers the module's drop-cached-client-and-retry path, whose fresh
        client (third fetch) then finds the rotated key.
        """
        private_pem, public = _generate_keypair()
        stale_jwks = _jwks_for(public, kid="stale-kid")
        fresh_jwks = _jwks_for(public, kid="rotated-kid")
        fetches: list[int] = []

        def _fake_fetch(self):
            fetches.append(1)
            return stale_jwks if len(fetches) <= 2 else fresh_jwks

        monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", _fake_fetch)
        token = _make_token(private_pem, _base_payload(), kid="rotated-kid")
        claims = await verify_jwt(
            token,
            algorithm="RS256",
            jwks_url=JWKS_URL,
            audience=AUDIENCE,
            issuer=ISSUER,
        )
        assert claims.sub == "kc-user-1"
        assert len(fetches) == 3

    async def test_unknown_kid_still_fails_after_refresh(self, monkeypatch):
        """If the refetched JWKS still lacks the kid, the error propagates."""
        private_pem, public = _generate_keypair()
        stale_jwks = _jwks_for(public, kid="stale-kid")
        fetches: list[int] = []

        def _fake_fetch(self):
            fetches.append(1)
            return stale_jwks

        monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", _fake_fetch)
        token = _make_token(private_pem, _base_payload(), kid="unknown-kid")
        with pytest.raises(jwt.exceptions.PyJWKClientError):
            await verify_jwt(
                token,
                algorithm="RS256",
                jwks_url=JWKS_URL,
                audience=AUDIENCE,
                issuer=ISSUER,
            )
        # Two fetches per client (initial + PyJWKClient's internal refresh),
        # across the original client and the module's recreated one.
        assert len(fetches) == 4


class TestVerifyJwtRawRS256:
    async def test_raw_roundtrip_preserves_extra_claims(self, patched_jwk_fetch):
        private_pem, _ = patched_jwk_fetch
        payload = _base_payload()
        payload["events"] = {"http://schemas.openid.net/event/backchannel-logout": {}}
        token = _make_token(private_pem, payload)
        raw = await verify_jwt_raw(
            token,
            algorithm="RS256",
            jwks_url=JWKS_URL,
            audience=AUDIENCE,
            issuer=ISSUER,
        )
        assert raw["sub"] == "kc-user-1"
        assert raw["events"] == {
            "http://schemas.openid.net/event/backchannel-logout": {}
        }

    async def test_raw_requires_jwks_url(self):
        with pytest.raises(ValueError, match="RS256 requires"):
            await verify_jwt_raw("anytoken", algorithm="RS256")

    async def test_raw_require_audience_without_audience_raises(
        self, patched_jwk_fetch
    ):
        private_pem, _ = patched_jwk_fetch
        token = _make_token(private_pem, _base_payload())
        with pytest.raises(ValueError, match="audience verification is required"):
            await verify_jwt_raw(
                token,
                algorithm="RS256",
                jwks_url=JWKS_URL,
                audience=None,
                issuer=ISSUER,
                require_audience=True,
            )
