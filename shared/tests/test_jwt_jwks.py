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
    def test_roundtrip_rs256(self, patched_jwk_fetch):
        private_pem, _ = patched_jwk_fetch
        token = _make_token(private_pem, _base_payload())
        claims = verify_jwt(
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

    def test_rejects_wrong_audience(self, patched_jwk_fetch):
        private_pem, _ = patched_jwk_fetch
        token = _make_token(private_pem, _base_payload())
        with pytest.raises(jwt.InvalidAudienceError):
            verify_jwt(
                token,
                algorithm="RS256",
                jwks_url=JWKS_URL,
                audience="wrong-audience",
                issuer=ISSUER,
            )

    def test_rejects_wrong_issuer(self, patched_jwk_fetch):
        """Issuer is verified when passed — cross-realm tokens are rejected (BE-AUTH-01)."""
        private_pem, _ = patched_jwk_fetch
        token = _make_token(private_pem, _base_payload())
        with pytest.raises(jwt.InvalidIssuerError):
            verify_jwt(
                token,
                algorithm="RS256",
                jwks_url=JWKS_URL,
                audience=AUDIENCE,
                issuer="http://evil-keycloak:8080/realms/other",
            )

    def test_requires_jwks_url(self):
        with pytest.raises(ValueError, match="RS256 requires"):
            verify_jwt("anytoken", algorithm="RS256")

    def test_require_audience_raises_when_audience_missing(self, patched_jwk_fetch):
        """require_audience=True forbids the implicit fail-open: no audience => error.

        Guards against an empty KEYCLOAK_AUDIENCE silently disabling ``aud``
        verification in production.
        """
        private_pem, _ = patched_jwk_fetch
        token = _make_token(private_pem, _base_payload())
        with pytest.raises(ValueError, match="audience verification is required"):
            verify_jwt(
                token,
                algorithm="RS256",
                jwks_url=JWKS_URL,
                audience=None,
                issuer=ISSUER,
                require_audience=True,
            )

    def test_require_audience_passes_when_audience_present(self, patched_jwk_fetch):
        """require_audience=True with a concrete audience verifies normally."""
        private_pem, _ = patched_jwk_fetch
        token = _make_token(private_pem, _base_payload())
        claims = verify_jwt(
            token,
            algorithm="RS256",
            jwks_url=JWKS_URL,
            audience=AUDIENCE,
            issuer=ISSUER,
            require_audience=True,
        )
        assert claims.aud == AUDIENCE
        assert claims.sub == "kc-user-1"

    def test_missing_audience_allowed_by_default(self, patched_jwk_fetch):
        """Default (require_audience=False) preserves the lenient dev behaviour:
        with no audience supplied, the ``aud`` claim is not verified."""
        private_pem, _ = patched_jwk_fetch
        token = _make_token(private_pem, _base_payload())
        claims = verify_jwt(
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
