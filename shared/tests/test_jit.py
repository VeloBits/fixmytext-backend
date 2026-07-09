"""Tests for JIT user provisioning (auth.jit) with a mocked AsyncSession."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase

from fixmytext_shared.auth import jit_provision_user
from fixmytext_shared.db.models.user import make_user_class


@pytest.fixture
def user_class():
    """A real mapped User class on a fresh Base so select() expressions work."""

    class Base(DeclarativeBase):
        pass

    return make_user_class(Base, "auth")


@pytest.fixture
def db():
    """Mock AsyncSession: sync add, async flush/rollback/scalar."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    session.scalar = AsyncMock()
    return session


def _payload(**overrides) -> dict:
    payload = {
        "email": "new@user.com",
        "preferred_username": "newbie",
        "email_verified": True,
    }
    payload.update(overrides)
    return payload


class TestJitProvisionUser:
    async def test_creates_user_from_claims(self, db, user_class):
        kc_id = uuid.uuid4()
        user = await jit_provision_user(db, user_class, kc_id, _payload())
        db.add.assert_called_once_with(user)
        db.flush.assert_awaited_once()
        assert user.keycloak_id == kc_id
        assert user.email == "new@user.com"
        assert user.display_name == "newbie"
        assert user.is_email_verified is True

    async def test_display_name_falls_back_to_email(self, db, user_class):
        payload = _payload(preferred_username=None)
        user = await jit_provision_user(db, user_class, uuid.uuid4(), payload)
        assert user.display_name == "new@user.com"

    async def test_email_verified_defaults_to_false(self, db, user_class):
        payload = _payload()
        del payload["email_verified"]
        user = await jit_provision_user(db, user_class, uuid.uuid4(), payload)
        assert user.is_email_verified is False

    async def test_rejects_missing_email_claim(self, db, user_class):
        with pytest.raises(HTTPException) as exc_info:
            await jit_provision_user(db, user_class, uuid.uuid4(), {})
        assert exc_info.value.status_code == 401
        db.add.assert_not_called()
        db.flush.assert_not_awaited()

    async def test_rejects_whitespace_only_email(self, db, user_class):
        with pytest.raises(HTTPException) as exc_info:
            await jit_provision_user(
                db, user_class, uuid.uuid4(), _payload(email="   ")
            )
        assert exc_info.value.status_code == 401
        db.add.assert_not_called()

    async def test_race_recovers_row_committed_by_other_request(self, db, user_class):
        """IntegrityError on flush -> rollback and re-query the winner's row."""
        kc_id = uuid.uuid4()
        existing = user_class(
            keycloak_id=kc_id, email="new@user.com", display_name="winner"
        )
        db.flush.side_effect = IntegrityError("stmt", {}, Exception("duplicate"))
        db.scalar.return_value = existing
        user = await jit_provision_user(db, user_class, kc_id, _payload())
        assert user is existing
        db.rollback.assert_awaited_once()
        db.scalar.assert_awaited_once()

    async def test_race_recovery_failure_raises_401(self, db, user_class):
        """If the re-query finds nothing, the request is rejected (401)."""
        db.flush.side_effect = IntegrityError("stmt", {}, Exception("duplicate"))
        db.scalar.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            await jit_provision_user(db, user_class, uuid.uuid4(), _payload())
        assert exc_info.value.status_code == 401
        db.rollback.assert_awaited_once()

    async def test_race_recovery_with_mismatched_keycloak_id_raises_401(
        self, db, user_class
    ):
        """A recovered row must belong to the same keycloak subject."""
        db.flush.side_effect = IntegrityError("stmt", {}, Exception("duplicate"))
        db.scalar.return_value = user_class(
            keycloak_id=uuid.uuid4(), email="other@user.com", display_name="other"
        )
        with pytest.raises(HTTPException) as exc_info:
            await jit_provision_user(db, user_class, uuid.uuid4(), _payload())
        assert exc_info.value.status_code == 401
