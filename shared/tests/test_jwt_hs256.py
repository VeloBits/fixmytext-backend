"""HS256 round-trip tests via verify_jwt() dispatcher."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from fixmytext_shared.security import verify_jwt
from fixmytext_shared.security.claims import ClaimSchema

SECRET = "test-secret-at-least-32-characters-long-for-pytest"


def _make_token(payload: dict, *, secret: str = SECRET) -> str:
    return jwt.encode(payload, secret, algorithm="HS256")


def _base_payload(sub: str = "user-123") -> dict:
    now = datetime.now(UTC)
    return {
        "sub": sub,
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "iat": int(now.timestamp()),
        "type": "access",
    }


class TestVerifyJwtHS256:
    async def test_roundtrip_minimal_payload(self):
        token = _make_token(_base_payload("user-42"))
        claims = await verify_jwt(token, algorithm="HS256", secret=SECRET)
        assert isinstance(claims, ClaimSchema)
        assert claims.sub == "user-42"
        assert claims.type == "access"
        assert claims.org_id is None
        assert claims.email is None
        assert claims.roles == []

    async def test_roundtrip_with_email_and_roles(self):
        payload = _base_payload()
        payload.update(
            {
                "email": "a@b.com",
                "email_verified": True,
                "roles": ["user", "admin"],
            }
        )
        token = _make_token(payload)
        claims = await verify_jwt(token, algorithm="HS256", secret=SECRET)
        assert claims.email == "a@b.com"
        assert claims.email_verified is True
        assert claims.roles == ["user", "admin"]

    async def test_rejects_wrong_secret(self):
        token = _make_token(_base_payload())
        with pytest.raises(jwt.PyJWTError):
            await verify_jwt(token, algorithm="HS256", secret="wrong-secret")

    async def test_rejects_expired_token(self):
        payload = _base_payload()
        now = datetime.now(UTC)
        payload["exp"] = int((now - timedelta(minutes=1)).timestamp())
        token = _make_token(payload)
        with pytest.raises(jwt.ExpiredSignatureError):
            await verify_jwt(token, algorithm="HS256", secret=SECRET)

    async def test_requires_secret_for_hs256(self):
        token = _make_token(_base_payload())
        with pytest.raises(ValueError, match="HS256 requires"):
            await verify_jwt(token, algorithm="HS256")

    async def test_defaults_to_hs256_when_no_algorithm_specified(self, monkeypatch):
        # No JWT_ALGORITHM env -> defaults to HS256
        monkeypatch.delenv("JWT_ALGORITHM", raising=False)
        token = _make_token(_base_payload())
        claims = await verify_jwt(token, secret=SECRET)
        assert claims.sub == "user-123"

    async def test_env_var_jwt_algorithm_respected(self, monkeypatch):
        monkeypatch.setenv("JWT_ALGORITHM", "HS256")
        token = _make_token(_base_payload())
        claims = await verify_jwt(token, secret=SECRET)
        assert claims.type == "access"
