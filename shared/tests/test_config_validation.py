"""Tests for the startup production-config validator (fail-fast)."""

import pytest

from fixmytext_shared.config.validation import (
    assert_required_in_prod,
    is_production_like,
)


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ("development", False),
        ("dev", False),
        ("test", False),
        ("ci", False),
        ("local", False),
        ("production", True),
        ("staging", True),
        ("preview", True),
        ("", True),  # unknown/blank -> treat as prod-like (fail closed)
    ],
)
def test_is_production_like(env, expected):
    assert is_production_like(env) is expected


def test_dev_is_exempt():
    # Missing values in dev must NOT raise (returns None).
    assert (
        assert_required_in_prod("development", KEYCLOAK_AUDIENCE="", KEYCLOAK_ISSUER="")
        is None
    )


def test_prod_raises_on_missing():
    with pytest.raises(RuntimeError) as exc:
        assert_required_in_prod(
            "production",
            KEYCLOAK_AUDIENCE="aud",
            KEYCLOAK_ISSUER="",  # missing
            SESSION_COOKIE_SECRET="",  # missing
        )
    msg = str(exc.value)
    assert "KEYCLOAK_ISSUER" in msg
    assert "SESSION_COOKIE_SECRET" in msg
    assert "KEYCLOAK_AUDIENCE" not in msg  # this one was set


def test_prod_passes_when_all_set():
    assert (
        assert_required_in_prod(
            "production",
            KEYCLOAK_AUDIENCE="aud",
            KEYCLOAK_ISSUER="iss",
            SESSION_COOKIE_SECRET="secret",
        )
        is None
    )
