"""Unit tests for server-side order scope/amount validation (H-3, BE-PAY-03).

Pure-logic tests — no database. They prove that:
  * tool scope is taken from server-set order notes and the tool count is
    enforced (a client cannot widen a 1-tool pass into N tools),
  * the paid amount is reconciled against the catalog price for the *charged
    currency* (paying a cheaper region's price is rejected),
  * Pro amount mismatches now BLOCK rather than warn.
"""

import pytest
from fastapi import HTTPException

from app.services.order_validation import (
    region_for_currency,
    validate_order_scope_and_amount,
    validate_pro_amount,
)


def _order(item_id, item_type, amount, currency="INR", tool_ids=None):
    notes = {"item_id": item_id, "item_type": item_type}
    if tool_ids is not None:
        notes["tool_ids"] = tool_ids
    return {"notes": notes, "amount": amount, "currency": currency}


# ── Happy paths ──────────────────────────────────────────────────────────────


def test_valid_single_tool_pass_returns_notes_tool_ids():
    tool_ids, amount, currency = validate_order_scope_and_amount(
        order=_order("quick_fix", "pass", 200, "INR", "humanizer"),
        expected_item_id="quick_fix",
        expected_item_type="pass",
    )
    assert tool_ids == ["humanizer"]
    assert amount == 200
    assert currency == "INR"


def test_all_tools_pass_returns_wildcard_ignoring_notes():
    tool_ids, amount, _ = validate_order_scope_and_amount(
        order=_order("day_all", "pass", 9900, "INR", "anything,here"),
        expected_item_id="day_all",
        expected_item_type="pass",
    )
    assert tool_ids == ["*"]
    assert amount == 9900


def test_valid_credit_pack():
    tool_ids, amount, _ = validate_order_scope_and_amount(
        order=_order("credits_5", "credit", 500, "INR"),
        expected_item_id="credits_5",
        expected_item_type="credit",
    )
    assert tool_ids == []
    assert amount == 500


def test_valid_us_pricing():
    tool_ids, amount, currency = validate_order_scope_and_amount(
        order=_order("quick_fix", "pass", 50, "USD", "humanizer"),
        expected_item_id="quick_fix",
        expected_item_type="pass",
    )
    assert tool_ids == ["humanizer"]
    assert amount == 50
    assert currency == "USD"


# ── H-3: scope / quantity tampering ──────────────────────────────────────────


def test_tool_count_widening_rejected():
    """A 1-tool pass with 4 tool_ids in the (server) notes is rejected."""
    with pytest.raises(HTTPException) as exc:
        validate_order_scope_and_amount(
            order=_order("quick_fix", "pass", 200, "INR", "a,b,c,d"),
            expected_item_id="quick_fix",
            expected_item_type="pass",
        )
    assert exc.value.status_code == 400


def test_item_id_mismatch_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_order_scope_and_amount(
            order=_order("day_all", "pass", 9900, "INR", ""),
            expected_item_id="quick_fix",
            expected_item_type="pass",
        )
    assert exc.value.status_code == 400


# ── H-3: amount / currency tampering ─────────────────────────────────────────


def test_amount_tampering_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_order_scope_and_amount(
            order=_order("quick_fix", "pass", 1, "INR", "humanizer"),
            expected_item_id="quick_fix",
            expected_item_type="pass",
        )
    assert exc.value.status_code == 400


def test_wrong_region_amount_for_currency_rejected():
    """Paying the INR price (200) but charged in USD (expects 50) is rejected."""
    with pytest.raises(HTTPException) as exc:
        validate_order_scope_and_amount(
            order=_order("quick_fix", "pass", 200, "USD", "humanizer"),
            expected_item_id="quick_fix",
            expected_item_type="pass",
        )
    assert exc.value.status_code == 400


def test_unsupported_currency_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_order_scope_and_amount(
            order=_order("quick_fix", "pass", 200, "JPY", "humanizer"),
            expected_item_id="quick_fix",
            expected_item_type="pass",
        )
    assert exc.value.status_code == 400


# ── Pro amount validation now BLOCKS (BE-PAY-03) ─────────────────────────────


def test_valid_pro_amount_passes():
    validate_pro_amount(39900, "INR")  # ₹399 — must not raise


def test_pro_amount_mismatch_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_pro_amount(1, "INR")
    assert exc.value.status_code == 400


def test_pro_unsupported_currency_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_pro_amount(39900, "JPY")
    assert exc.value.status_code == 400


def test_pro_missing_amount_rejected():
    with pytest.raises(HTTPException) as exc:
        validate_pro_amount(None, "INR")
    assert exc.value.status_code == 400


# ── region_for_currency ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("currency", "expected"),
    [
        ("INR", "IN"),
        ("inr", "IN"),
        ("USD", "US"),
        ("eur", "EU"),
        ("GBP", "GB"),
        ("JPY", None),
        ("", None),
        (None, None),
    ],
)
def test_region_for_currency(currency, expected):
    assert region_for_currency(currency) == expected


# ── Pass consumption ordering (H-2) ──────────────────────────────────────────


def test_check_passes_consumes_soonest_expiring_pass_first():
    """_check_passes must ORDER BY expires_at ASC so a 1-day pass is consumed
    before a 30-day pass when both cover the same tool (H-2).

    Source-level check (no DB) — the atomicity of the actual query ordering is
    exercised by the integration test in test_entitlement_atomic.py at runtime.
    """
    import inspect

    from app.services import pass_service

    src = inspect.getsource(pass_service._check_passes)
    assert "order_by" in src and "expires_at" in src, (
        "_check_passes must ORDER BY expires_at so the soonest-expiring pass "
        "is consumed first, not an arbitrary DB-order pass (H-2)"
    )


# ── validate_tool_selection (order-time scope validation) ─────────────────────


class TestValidateToolSelection:
    def _pass(self, tools: int) -> dict:
        return {"id": "test_pass", "tools": tools}

    def test_all_tools_pass_ignores_client_ids(self):
        from app.services.order_validation import validate_tool_selection

        assert validate_tool_selection(self._pass(-1), ["uppercase", "x"]) == []
        assert validate_tool_selection(self._pass(-1), []) == []

    def test_exact_count_returns_canonical_list(self):
        from app.services.order_validation import validate_tool_selection

        result = validate_tool_selection(
            self._pass(3), ["uppercase", "translate", "grammar_fix"]
        )
        assert result == ["uppercase", "translate", "grammar_fix"]

    def test_duplicates_collapse_and_fail_count(self):
        from app.services.order_validation import validate_tool_selection

        with pytest.raises(HTTPException) as exc:
            validate_tool_selection(
                self._pass(3), ["uppercase", "uppercase", "translate"]
            )
        assert exc.value.status_code == 400
        assert "exactly 3 tools" in exc.value.detail.lower()

    def test_empty_selection_for_scoped_pass_rejected(self):
        from app.services.order_validation import validate_tool_selection

        with pytest.raises(HTTPException) as exc:
            validate_tool_selection(self._pass(1), [])
        assert exc.value.status_code == 400
        assert "exactly 1 tool" in exc.value.detail.lower()

    def test_too_many_tools_rejected(self):
        from app.services.order_validation import validate_tool_selection

        with pytest.raises(HTTPException):
            validate_tool_selection(self._pass(1), ["uppercase", "translate"])

    def test_always_free_tool_rejected(self):
        from app.services.order_validation import validate_tool_selection

        with pytest.raises(HTTPException) as exc:
            validate_tool_selection(self._pass(1), ["find_replace"])
        assert "always free" in exc.value.detail.lower()

    def test_malformed_tool_id_rejected(self):
        from app.services.order_validation import validate_tool_selection

        for bad in ["UPPER", "has space", "a" * 65, "semi;colon", ""]:
            with pytest.raises(HTTPException):
                validate_tool_selection(self._pass(1), [bad])
