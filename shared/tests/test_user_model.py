"""Tests for the shared User ORM factory (make_user_class)."""

import uuid

from sqlalchemy.orm import DeclarativeBase

from fixmytext_shared.db.models.user import make_user_class


def _fresh_user_class(schema: str = "auth"):
    class Base(DeclarativeBase):
        pass

    return make_user_class(Base, schema)


class TestMakeUserClass:
    def test_tablename_and_schema(self):
        user_cls = _fresh_user_class("auth_test")
        assert user_cls.__tablename__ == "users"
        assert user_cls.__table__.schema == "auth_test"

    def test_class_name_normalised(self):
        user_cls = _fresh_user_class()
        assert user_cls.__name__ == "User"
        assert user_cls.__qualname__ == "User"

    def test_expected_columns_present(self):
        user_cls = _fresh_user_class()
        cols = set(user_cls.__table__.columns.keys())
        assert {
            "id",
            "email",
            "keycloak_id",
            "display_name",
            "is_active",
            "is_email_verified",
            "created_at",
            "updated_at",
            "referral_code",
            "referred_by",
            "region",
        } <= cols

    def test_removed_legacy_columns_absent(self):
        # hashed_password + last_login_at were dropped once auth went
        # Keycloak-only (2026-07-09) - guard against reintroduction.
        cols = set(_fresh_user_class().__table__.columns.keys())
        assert "hashed_password" not in cols
        assert "last_login_at" not in cols

    def test_nullability(self):
        cols = _fresh_user_class().__table__.columns
        assert cols["email"].nullable is False
        assert cols["display_name"].nullable is False
        assert cols["is_email_verified"].nullable is False
        assert cols["keycloak_id"].nullable is True
        assert cols["referral_code"].nullable is True
        assert cols["region"].nullable is True

    def test_unique_indexes_declared(self):
        indexes = {i.name: i for i in _fresh_user_class().__table__.indexes}
        assert indexes["uq_users_email"].unique is True
        assert indexes["uq_users_referral_code"].unique is True
        assert "ix_auth_users_email" in indexes

    def test_referred_by_fk_targets_users_in_same_schema(self):
        user_cls = _fresh_user_class("myschema")
        fks = list(user_cls.__table__.columns["referred_by"].foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "myschema.users.id"
        assert fks[0].ondelete == "SET NULL"

    def test_id_is_uuid_primary_key(self):
        col = _fresh_user_class().__table__.columns["id"]
        assert col.primary_key is True
        assert col.server_default is not None

    def test_instances_accept_column_kwargs(self):
        user_cls = _fresh_user_class()
        kc_id = uuid.uuid4()
        user = user_cls(
            email="a@b.com",
            display_name="A",
            keycloak_id=kc_id,
        )
        assert user.email == "a@b.com"
        assert user.display_name == "A"
        assert user.keycloak_id == kc_id

    def test_each_service_gets_an_independent_class(self):
        cls_a = _fresh_user_class("auth_a")
        cls_b = _fresh_user_class("auth_b")
        assert cls_a is not cls_b
        assert cls_a.__table__.schema == "auth_a"
        assert cls_b.__table__.schema == "auth_b"
