"""
Razorpay SDK wrapper for OmniAI payments.

Handles order creation, payment signature verification (client-side),
and webhook signature verification (server-side).

The actual API endpoints live in api/payments.py.
"""
import os
import time
import logging
from typing import Optional, Dict, Any

import razorpay
from razorpay.errors import SignatureVerificationError, BadRequestError

logger = logging.getLogger(__name__)


# ============================================================================
# PRICING CONFIG
# Single source of truth — change ₹499 here and it applies everywhere.
# Amount is in PAISE (₹1 = 100 paise). 49900 paise = ₹499.
# ============================================================================

PRO_MONTHLY_PLAN = "pro_monthly"

SUPPORTED_PLANS: Dict[str, Dict[str, Any]] = {
    PRO_MONTHLY_PLAN: {
        "amount": 49900,                 # ₹499.00 in paise
        "currency": "INR",
        "duration_days": 30,
        "label": "OmniAI Pro — 1 Month",
        "description": "Unlimited messages, Gmail send, Calendar create, custom prompts, unlimited memories",
    },
}


class RazorpayService:
    """Razorpay SDK wrapper. Use via get_razorpay_service() singleton."""

    def __init__(self):
        key_id = os.getenv("RAZORPAY_KEY_ID")
        key_secret = os.getenv("RAZORPAY_KEY_SECRET")
        webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")

        if not key_id or not key_secret:
            raise RuntimeError(
                "Razorpay credentials missing. "
                "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in environment."
            )

        self.key_id: str = key_id
        self.webhook_secret: Optional[str] = webhook_secret
        self.client = razorpay.Client(auth=(key_id, key_secret))

        logger.info(f"RazorpayService initialized with key_id={key_id[:15]}...")

    # ------------------------------------------------------------------------
    # Plan helpers
    # ------------------------------------------------------------------------

    def get_plan(self, plan: str) -> Dict[str, Any]:
        """Return plan config or raise ValueError."""
        if plan not in SUPPORTED_PLANS:
            raise ValueError(
                f"Unsupported plan: {plan}. "
                f"Available: {list(SUPPORTED_PLANS.keys())}"
            )
        return SUPPORTED_PLANS[plan]

    # ------------------------------------------------------------------------
    # Order creation
    # ------------------------------------------------------------------------

    def create_order(
        self,
        plan: str,
        user_id: str,
        user_email: Optional[str] = None,
        receipt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a Razorpay order. Returns the raw Razorpay order dict, which
        includes:
            - id: e.g. 'order_OabCdEfGh1234I'
            - amount: paise
            - currency: 'INR'
            - status: 'created'
            - receipt: short identifier we set
            - notes: dict of metadata we attached
        """
        plan_config = self.get_plan(plan)

        # Razorpay receipt field has a 40-char max, must be unique-ish.
        # Format: omn_<user_id_short>_<unix_ts>
        if not receipt:
            user_id_short = str(user_id).replace("-", "")[:12]
            receipt = f"omn_{user_id_short}_{int(time.time())}"
        receipt = receipt[:40]

        try:
            order = self.client.order.create({
                "amount": plan_config["amount"],
                "currency": plan_config["currency"],
                "receipt": receipt,
                "notes": {
                    "plan": plan,
                    "user_id": str(user_id),
                    "user_email": user_email or "unknown",
                    "product": "OmniAI Pro",
                },
            })

            logger.info(
                f"Razorpay order created: {order['id']} "
                f"user={user_id} plan={plan} amount={plan_config['amount']}"
            )
            return order

        except BadRequestError as e:
            logger.error(f"Razorpay bad request for user {user_id}: {e}")
            raise
        except Exception:
            logger.exception(f"Razorpay order creation failed for user {user_id}")
            raise

    # ------------------------------------------------------------------------
    # Signature verification — used in #42 (webhook) and #45 (frontend confirm)
    # ------------------------------------------------------------------------

    def verify_payment_signature(
        self,
        order_id: str,
        payment_id: str,
        signature: str,
    ) -> bool:
        """
        Verify the signature returned by Razorpay Checkout after the user pays.
        Used as an optimistic client-side confirmation; the webhook is the
        source of truth for marking a user Pro.
        """
        try:
            self.client.utility.verify_payment_signature({
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            })
            return True
        except SignatureVerificationError:
            logger.warning(
                f"Invalid payment signature: order={order_id} payment={payment_id}"
            )
            return False
        except Exception:
            logger.exception("Unexpected error verifying payment signature")
            return False

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """
        Verify a Razorpay webhook call is genuine.
        body: the raw request body bytes (do NOT json.loads first)
        signature: the value from header X-Razorpay-Signature
        """
        if not self.webhook_secret:
            logger.error(
                "RAZORPAY_WEBHOOK_SECRET not set — cannot verify webhook"
            )
            return False

        try:
            body_str = body.decode("utf-8") if isinstance(body, bytes) else body
            self.client.utility.verify_webhook_signature(
                body_str,
                signature,
                self.webhook_secret,
            )
            return True
        except SignatureVerificationError:
            logger.warning("Webhook signature mismatch — possible spoofed request")
            return False
        except Exception:
            logger.exception("Unexpected error verifying webhook signature")
            return False

    # ------------------------------------------------------------------------
    # Fetch helpers (for #42 webhook reconciliation)
    # ------------------------------------------------------------------------

    def fetch_payment(self, payment_id: str) -> Dict[str, Any]:
        """Fetch full payment details from Razorpay."""
        return self.client.payment.fetch(payment_id)

    def fetch_order(self, order_id: str) -> Dict[str, Any]:
        """Fetch full order details from Razorpay."""
        return self.client.order.fetch(order_id)


# ============================================================================
# Singleton accessor
# ============================================================================

_razorpay_service: Optional[RazorpayService] = None


def get_razorpay_service() -> RazorpayService:
    """Lazy-init singleton. Used as FastAPI dependency or direct call."""
    global _razorpay_service
    if _razorpay_service is None:
        _razorpay_service = RazorpayService()
    return _razorpay_service