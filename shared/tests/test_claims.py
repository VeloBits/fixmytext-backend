"""Edge-case tests for ClaimSchema.from_payload / to_dict."""

import pytest

from fixmytext_shared.security.claims import ClaimSchema


def _payload(**overrides) -> dict:
    payload = {"sub": "user-1", "exp": 2_000_000_000, "iat": 1_000_000_000}
    payload.update(overrides)
    return payload


class TestFromPayload:
    def test_missing_sub_rejected(self):
        with pytest.raises(ValueError, match="'sub'"):
            ClaimSchema.from_payload({"exp": 2_000_000_000})

    def test_blank_sub_rejected(self):
        with pytest.raises(ValueError, match="'sub'"):
            ClaimSchema.from_payload(_payload(sub="   "))

    def test_missing_exp_rejected(self):
        payload = _payload()
        del payload["exp"]
        with pytest.raises(ValueError, match="'exp'"):
            ClaimSchema.from_payload(payload)

    def test_numeric_sub_coerced_to_string(self):
        assert ClaimSchema.from_payload(_payload(sub=123)).sub == "123"

    def test_roles_fall_back_to_realm_access(self):
        claims = ClaimSchema.from_payload(
            _payload(realm_access={"roles": ["user", "admin"]})
        )
        assert claims.roles == ["user", "admin"]

    def test_direct_roles_win_over_realm_access(self):
        claims = ClaimSchema.from_payload(
            _payload(roles=["direct"], realm_access={"roles": ["realm"]})
        )
        assert claims.roles == ["direct"]

    def test_non_list_roles_coerced_to_empty(self):
        assert ClaimSchema.from_payload(_payload(roles="admin")).roles == []

    def test_aud_list_picks_first_string(self):
        claims = ClaimSchema.from_payload(
            _payload(aud=[42, "fixmytext-backend", "other"])
        )
        assert claims.aud == "fixmytext-backend"

    def test_aud_list_without_strings_is_none(self):
        assert ClaimSchema.from_payload(_payload(aud=[42, None])).aud is None

    def test_non_string_aud_is_none(self):
        assert ClaimSchema.from_payload(_payload(aud=123)).aud is None

    def test_iat_defaults_to_zero(self):
        payload = _payload()
        del payload["iat"]
        assert ClaimSchema.from_payload(payload).iat == 0

    def test_unknown_extra_keys_ignored(self):
        claims = ClaimSchema.from_payload(_payload(events={"logout": {}}, azp="cli"))
        assert claims.sub == "user-1"


class TestToDict:
    def test_round_trips_all_fields(self):
        claims = ClaimSchema.from_payload(
            _payload(
                email="a@b.com",
                email_verified=True,
                roles=["user"],
                org_id="org-9",
                iss="http://kc/realms/test",
                aud="fixmytext-backend",
                preferred_username="abc",
            )
        )
        assert claims.to_dict() == {
            "sub": "user-1",
            "exp": 2_000_000_000,
            "iat": 1_000_000_000,
            "type": "access",
            "email": "a@b.com",
            "email_verified": True,
            "roles": ["user"],
            "org_id": "org-9",
            "iss": "http://kc/realms/test",
            "aud": "fixmytext-backend",
            "preferred_username": "abc",
        }

    def test_roles_list_is_a_copy(self):
        claims = ClaimSchema.from_payload(_payload(roles=["user"]))
        d = claims.to_dict()
        d["roles"].append("admin")
        assert claims.roles == ["user"]
