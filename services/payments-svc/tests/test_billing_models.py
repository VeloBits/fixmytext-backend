"""DB constraint correctness tests for billing ORM models.

Verifies that the SQLAlchemy check constraints on billing tables match what
the codebase actually writes, so mis-classified status values produce clear
IntegrityErrors at flush time rather than silently corrupting the table or
causing the DB to reject the row with a cryptic 500.

  PaymentEvent.status  must allow 'failed' (webhook error paths) and must NOT
                       allow 'error' (which was mistakenly used and violates
                       the DB check constraint — C-1).
  Subscription.status  must allow 'halted' (subscription.halted webhook — C-2).
"""

from sqlalchemy import CheckConstraint


def _get_status_constraint(model) -> str:
    """Return the SQL text of the status check constraint for *model*."""
    constraints = [
        c
        for c in model.__table_args__
        if isinstance(c, CheckConstraint) and "status" in str(c.sqltext)
    ]
    assert constraints, f"{model.__name__} must have a status check constraint"
    return str(constraints[0].sqltext)


# ── PaymentEvent (payment_events table) ──────────────────────────────────────


def test_payment_event_status_allows_failed():
    """'failed' must be a valid status so webhook error paths can persist an
    audit record without violating the DB constraint (C-1)."""
    from app.db.models.billing_subscription import PaymentEvent

    sql = _get_status_constraint(PaymentEvent)
    assert "failed" in sql


def test_payment_event_status_does_not_allow_error():
    """'error' must NOT be in the PaymentEvent status constraint.
    Setting pe.status='error' raised IntegrityError → 500 → infinite Razorpay
    retry on any webhook with bad notes data (C-1)."""
    from app.db.models.billing_subscription import PaymentEvent

    sql = _get_status_constraint(PaymentEvent)
    assert "error" not in sql


def test_payment_event_status_complete_allowed_set():
    """All four documented status values must be present."""
    from app.db.models.billing_subscription import PaymentEvent

    sql = _get_status_constraint(PaymentEvent)
    for value in ("received", "processed", "failed", "duplicate"):
        assert value in sql, f"'{value}' missing from PaymentEvent status constraint"


# ── Subscription (subscriptions table) ───────────────────────────────────────


def test_subscription_status_allows_halted():
    """'halted' must be a valid Subscription status.
    The subscription.halted Razorpay webhook sets status='halted'; without it
    in the constraint every such webhook returned 500 and retried forever (C-2)."""
    from app.db.models.billing_subscription import Subscription

    sql = _get_status_constraint(Subscription)
    assert "halted" in sql


def test_subscription_status_retains_original_values():
    """Adding 'halted' must not have dropped any of the original allowed values."""
    from app.db.models.billing_subscription import Subscription

    sql = _get_status_constraint(Subscription)
    for value in ("active", "cancelled", "expired", "pending"):
        assert value in sql, f"'{value}' missing from Subscription status constraint"
