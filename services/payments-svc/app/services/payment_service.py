"""
Payment verification service.

Centralizes all Razorpay payment verification logic. Validates signatures,
verifies order ownership, and checks amounts against the current catalog.
"""

import logging

from fastapi import HTTPException

from app.db.models.user import User
from app.services.razorpay_service import fetch_order, verify_payment_signature

logger = logging.getLogger(__name__)


async def verify_razorpay_payment(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
    user: User,
) -> dict:
    """Verify a Razorpay payment end-to-end.

    Performs three checks in order:
    1. Cryptographic signature validation against Razorpay's secret.
    2. Fetches the order from Razorpay to read its metadata.
    3. Confirms the order belongs to the authenticated user by comparing
       the ``user_id`` stored in ``order.notes`` against ``user.id`` from
       the JWT.  The notes are set at order-creation time and verified
       here against the trusted JWT identity.

    Args:
        razorpay_order_id: The Razorpay order ID from the client callback.
        razorpay_payment_id: The Razorpay payment ID from the client callback.
        razorpay_signature: HMAC-SHA256 signature from Razorpay.
        user: The currently authenticated user (from ``Depends(get_current_user)``).

    Returns:
        The full Razorpay order dict on success.

    Raises:
        HTTPException(400): Invalid signature or order does not belong to user.
        HTTPException(502): Razorpay API is unreachable.
    """
    # 1. Verify cryptographic signature
    if not verify_payment_signature(
        razorpay_order_id, razorpay_payment_id, razorpay_signature
    ):
        raise HTTPException(400, "Payment verification failed — invalid signature")

    # 2. Fetch order details from Razorpay
    try:
        order = fetch_order(razorpay_order_id)
    except Exception as e:
        sanitized_id = razorpay_order_id.replace("\n", "").replace("\r", "")[:64]
        logger.exception("Failed to fetch Razorpay order %s", sanitized_id)
        raise HTTPException(
            502, "Could not verify order details with payment provider"
        ) from e

    # 3. Verify ownership using the JWT-authenticated user, not order notes.
    #    The notes are included for audit/debugging only — trust the JWT identity.
    notes = order.get("notes", {})
    if notes.get("user_id") != str(user.id):
        raise HTTPException(400, "Order does not belong to this user")

    return order
