"""Server-side validation of Razorpay order scope and amount.

Used by both the synchronous verify callbacks and the webhook to guarantee the
paid amount matches the catalog price for the *charged currency* and that the
granted tool scope comes from the server-set order notes - never the client
request body. Fixes scope/quantity and amount tampering (H-3, BE-PAY-03).
"""

import re

from fastapi import HTTPException

from app.core.pass_catalog import (
    ALWAYS_FREE_TOOL_IDS,
    REGIONS,
    get_credit_pack,
    get_pass,
    get_price,
)
from app.services.razorpay_service import PRO_PLAN_PRICES

_TOOL_ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def validate_tool_selection(pass_def: dict, tool_ids: list[str]) -> list[str]:
    """Normalize and validate an order-time tool selection for a pass.

    Returns the canonical tool list to store in the order notes:
    - all-tools passes (``tools == -1``) always return ``[]`` (scope is the
      wildcard; any client-sent ids are ignored),
    - scoped passes must select exactly ``pass_def["tools"]`` distinct,
      well-formed, non-always-free tool ids.

    Raises ``HTTPException(400)`` with a user-facing message otherwise. This is
    the order-time twin of the fulfillment check in
    :func:`validate_order_scope_and_amount` - rejecting here means money never
    moves for an unfulfillable selection.
    """
    if pass_def["tools"] == -1:
        return []

    # Dedupe preserving order so the notes stay stable for idempotency hashing.
    unique: list[str] = []
    for tool_id in tool_ids:
        if tool_id not in unique:
            unique.append(tool_id)

    for tool_id in unique:
        if not _TOOL_ID_RE.match(tool_id):
            raise HTTPException(400, f"Invalid tool id: {tool_id[:64]!r}")
        if tool_id in ALWAYS_FREE_TOOL_IDS:
            raise HTTPException(
                400, f"'{tool_id}' is always free - pick a tool that uses your pass"
            )

    required = pass_def["tools"]
    if len(unique) != required:
        raise HTTPException(
            400,
            f"Select exactly {required} tool{'s' if required > 1 else ''} for this pass",
        )
    return unique


def region_for_currency(currency: str | None) -> str | None:
    """Return the region whose currency matches *currency* (case-insensitive).

    Each catalog region maps to exactly one currency, so the charged currency
    unambiguously identifies the region whose price the amount must match.
    """
    cur = (currency or "").lower()
    if not cur:
        return None
    for region, meta in REGIONS.items():
        if meta["currency"] == cur:
            return region
    return None


def validate_order_scope_and_amount(
    *,
    order: dict,
    expected_item_id: str | None,
    expected_item_type: str | None,
) -> tuple[list[str], int, str]:
    """Validate a pass/credit order's scope and amount against the catalog.

    Returns ``(tool_ids, amount, currency)`` where ``tool_ids`` is derived from
    the **server-set order notes**, never from the client request. Raises
    ``HTTPException(400)`` on any item, currency, amount, or tool-count mismatch.
    """
    notes = order.get("notes") or {}
    if (
        notes.get("item_id") != expected_item_id
        or notes.get("item_type") != expected_item_type
    ):
        raise HTTPException(
            400, "Order details do not match - item_id or item_type mismatch"
        )

    amount = order.get("amount")
    currency = order.get("currency")
    region = region_for_currency(currency)
    if region is None:
        raise HTTPException(400, "Unsupported or missing payment currency")

    expected_price = get_price(expected_item_id, region)
    if not expected_price or amount != expected_price:
        raise HTTPException(400, "Order amount does not match catalog price")

    tool_ids: list[str] = []
    if expected_item_type == "pass":
        pass_def = get_pass(expected_item_id)
        if not pass_def:
            raise HTTPException(400, f"Unknown pass: {expected_item_id}")
        if pass_def["tools"] == -1:
            # All-tools pass - scope is always the wildcard, regardless of notes.
            tool_ids = ["*"]
        else:
            raw = notes.get("tool_ids", "") or ""
            tool_ids = [t for t in raw.split(",") if t]
            if len(tool_ids) != pass_def["tools"]:
                raise HTTPException(
                    400, "tool_ids count does not match the purchased pass"
                )
    elif expected_item_type == "credit":
        if not get_credit_pack(expected_item_id):
            raise HTTPException(400, f"Unknown credit pack: {expected_item_id}")
    else:
        raise HTTPException(400, f"Unsupported item_type: {expected_item_type}")

    return tool_ids, amount, currency


def validate_pro_amount(amount: int | None, currency: str | None) -> None:
    """Validate a Pro subscription payment amount against catalog pricing.

    Raises ``HTTPException(400)`` if the amount does not match the catalog price
    for the charged currency. Unlike the previous warn-only check (BE-PAY-03),
    a mismatch now *blocks* fulfillment.
    """
    if amount is None:
        raise HTTPException(400, "Missing payment amount")
    cur = (currency or "").upper()
    for pricing in PRO_PLAN_PRICES.values():
        if pricing["currency"].upper() == cur:
            if pricing["amount"] == amount:
                return
            raise HTTPException(
                400, "Pro subscription amount does not match catalog price"
            )
    raise HTTPException(400, "Unsupported or missing payment currency")
