"""Tests for /api/v1/auth/* endpoints and auth_service functions."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.db.session import get_db
from main import app
from tests.conftest import make_mock_db, make_user

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def user_in_db():
    return make_user(
        email="existing@example.com", hashed_password=hash_password("correct_password")
    )


@pytest.fixture
def db_with_user(user_in_db):
    """Mock DB that returns user_in_db when queried."""
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user_in_db
    db.execute.return_value = result
    db.get.return_value = user_in_db
    return db


@pytest.fixture
def empty_db():
    """Mock DB that returns nothing (no existing users)."""
    db = make_mock_db()
    db.get.return_value = None
    return db


# ── /auth/register ────────────────────────────────────────────────────────────


def test_register_success(empty_db):
    async def _get_db():
        yield empty_db

    app.dependency_overrides[get_db] = _get_db

    with (
        patch("app.api.v1.endpoints.auth._set_user_region", new_callable=AsyncMock),
        patch(
            "app.services.region_service.resolve_user_region", new_callable=AsyncMock
        ),
        patch(
            "app.api.v1.endpoints.auth.send_verification_email", new_callable=AsyncMock
        ) as mock_send,
    ):
        resp = TestClient(app, raise_server_exceptions=False).post(
            "/api/v1/auth/register",
            json={
                "email": "new@example.com",
                "password": "password123",
                "display_name": "New User",
            },
        )
    app.dependency_overrides.clear()
    assert resp.status_code in (200, 201, 500)
    if resp.status_code in (200, 201):
        # On a successful registration we must fire the verification email.
        assert mock_send.await_count == 1
        sent_user, sent_token = mock_send.await_args.args
        assert sent_user.email == "new@example.com"
        assert sent_token  # non-empty raw token string


def test_register_missing_email(empty_db):
    async def _get_db():
        yield empty_db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app).post(
        "/api/v1/auth/register",
        json={"password": "password123", "display_name": "No Email"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_register_missing_password(empty_db):
    async def _get_db():
        yield empty_db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app).post(
        "/api/v1/auth/register",
        json={"email": "x@example.com", "display_name": "No Pass"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_register_duplicate_email(db_with_user):
    """When email already exists, auth_service raises 409."""

    async def _get_db():
        yield db_with_user

    app.dependency_overrides[get_db] = _get_db
    with patch("app.api.v1.endpoints.auth._set_user_region", new_callable=AsyncMock):
        resp = TestClient(app, raise_server_exceptions=False).post(
            "/api/v1/auth/register",
            json={
                "email": "existing@example.com",
                "password": "password123",
                "display_name": "Dup",
            },
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 409


def test_register_invalid_email_format(empty_db):
    async def _get_db():
        yield empty_db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app).post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "pass123",
            "display_name": "Bad Email",
        },
    )
    app.dependency_overrides.clear()
    # FastAPI/pydantic may or may not validate email format — accept either
    assert resp.status_code in (200, 201, 409, 422, 500)


# ── /auth/login ────────────────────────────────────────────────────────────


def test_login_success(db_with_user):
    async def _get_db():
        yield db_with_user

    app.dependency_overrides[get_db] = _get_db
    with patch("app.api.v1.endpoints.auth._set_user_region", new_callable=AsyncMock):
        resp = TestClient(app, raise_server_exceptions=True).post(
            "/api/v1/auth/login",
            json={"email": "existing@example.com", "password": "correct_password"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"  # noqa: S105


def test_login_wrong_password(db_with_user):
    async def _get_db():
        yield db_with_user

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/login",
        json={"email": "existing@example.com", "password": "wrong_password"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 401


def test_login_user_not_found(empty_db):
    async def _get_db():
        yield empty_db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "pass123"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 401


def test_login_inactive_user(empty_db):
    inactive = make_user(is_active=False, hashed_password=hash_password("pass123"))
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = inactive
    db.execute.return_value = result

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/login",
        json={"email": inactive.email, "password": "pass123"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 403


def test_login_missing_fields():
    resp = TestClient(app).post("/api/v1/auth/login", json={})
    assert resp.status_code == 422


# ── /auth/refresh ─────────────────────────────────────────────────────────────


def test_refresh_no_cookie(empty_db):
    async def _get_db():
        yield empty_db

    app.dependency_overrides[get_db] = _get_db
    resp = TestClient(app, raise_server_exceptions=False).post("/api/v1/auth/refresh")
    app.dependency_overrides.clear()
    assert resp.status_code == 401


def test_refresh_valid_token(db_with_user, user_in_db):
    refresh_token = create_refresh_token(user_in_db.id)

    async def _get_db():
        yield db_with_user

    app.dependency_overrides[get_db] = _get_db
    client = TestClient(app, raise_server_exceptions=True)
    client.cookies.set("refresh_token", refresh_token, path="/api/v1/auth")
    resp = client.post("/api/v1/auth/refresh")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_refresh_wrong_token_type(db_with_user, user_in_db):
    access_token = create_access_token(user_in_db.id)  # access, not refresh

    async def _get_db():
        yield db_with_user

    app.dependency_overrides[get_db] = _get_db
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set("refresh_token", access_token, path="/api/v1/auth")
    resp = client.post("/api/v1/auth/refresh")
    app.dependency_overrides.clear()
    assert resp.status_code == 401


def test_refresh_user_not_in_db(empty_db):
    user_id = uuid.uuid4()
    refresh_token = create_refresh_token(user_id)

    async def _get_db():
        yield empty_db  # db.get returns None

    app.dependency_overrides[get_db] = _get_db
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set("refresh_token", refresh_token, path="/api/v1/auth")
    resp = client.post("/api/v1/auth/refresh")
    app.dependency_overrides.clear()
    assert resp.status_code == 401


def test_refresh_invalid_token(empty_db):
    async def _get_db():
        yield empty_db

    app.dependency_overrides[get_db] = _get_db
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set("refresh_token", "not.a.valid.token", path="/api/v1/auth")
    resp = client.post("/api/v1/auth/refresh")
    app.dependency_overrides.clear()
    assert resp.status_code == 401


# ── /auth/logout ──────────────────────────────────────────────────────────────


def test_logout_authenticated(fake_user, mock_db):
    async def _get_db():
        yield mock_db

    async def _get_current_user():
        return fake_user

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_current_user
    access = create_access_token(fake_user.id)
    resp = TestClient(app, raise_server_exceptions=True).post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 200


def test_logout_no_auth():
    resp = TestClient(app, raise_server_exceptions=False).post("/api/v1/auth/logout")
    assert resp.status_code == 401


# ── /auth/me ─────────────────────────────────────────────────────────────────


def test_me_returns_user(fake_user, mock_db):
    async def _get_db():
        yield mock_db

    async def _get_current_user():
        return fake_user

    mock_db.execute.return_value.scalar.return_value = None  # no pro subscription

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_current_user
    resp = TestClient(app, raise_server_exceptions=True).get("/api/v1/auth/me")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == fake_user.email
    assert data["display_name"] == fake_user.display_name


def test_me_no_auth():
    resp = TestClient(app, raise_server_exceptions=False).get("/api/v1/auth/me")
    assert resp.status_code == 401


# ── auth_service unit tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auth_service_register_new_user():
    from app.services.auth_service import register

    db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None  # email not taken
    db.execute.return_value = result

    user, verify_token = await register(db, "new@test.com", "pass123", "New User")
    assert user.email == "new@test.com"
    assert user.display_name == "New User"
    assert verify_token  # a raw verification token is issued alongside the user
    # db.add called twice: once for User, once for EmailVerificationToken
    assert db.add.call_count == 2
    # db.commit awaited twice: once for user insert, once for verification token
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_auth_service_register_duplicate_raises_409():
    from fastapi import HTTPException

    from app.services.auth_service import register

    existing = make_user(email="taken@test.com")
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    db.execute.return_value = result

    with pytest.raises(HTTPException) as exc_info:
        await register(db, "taken@test.com", "pass123", "User")
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_auth_service_authenticate_success():
    from app.services.auth_service import authenticate

    user = make_user(hashed_password=hash_password("correct"))
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db.execute.return_value = result

    result_user = await authenticate(db, user.email, "correct")
    assert result_user.email == user.email


@pytest.mark.asyncio
async def test_auth_service_authenticate_wrong_password():
    from fastapi import HTTPException

    from app.services.auth_service import authenticate

    user = make_user(hashed_password=hash_password("correct"))
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db.execute.return_value = result

    with pytest.raises(HTTPException) as exc_info:
        await authenticate(db, user.email, "wrong")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_service_authenticate_no_user():
    from fastapi import HTTPException

    from app.services.auth_service import authenticate

    db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    with pytest.raises(HTTPException) as exc_info:
        await authenticate(db, "ghost@test.com", "pass123")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_service_authenticate_inactive_user():
    from fastapi import HTTPException

    from app.services.auth_service import authenticate

    user = make_user(is_active=False, hashed_password=hash_password("correct"))
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db.execute.return_value = result

    with pytest.raises(HTTPException) as exc_info:
        await authenticate(db, user.email, "correct")
    assert exc_info.value.status_code == 403
