"""
Payments API — Razorpay integration for OmniAI Pro subscriptions.

Endpoints in this file:
  GET  /api/v1/payments/key            (#41) Public Razorpay key for frontend init
  GET  /api/v1/payments/plans          (#41) Available subscription plans
  POST /api/v1/payments/create-order   (#41) Create Razorpay order
  POST /api/v1/payments/webhook        (#42) Razorpay event receiver (signature-verified)
  POST /api/v1/payments/verify         (#42) Optimistic post-checkout verification
  GET  /api/v1/payments/me             (#43) Current user's subscription state
  GET  /api/v1/payments/pro-test       (#44) Pro-gate verification endpoint

Pro gate: require_pro() helper for use in any endpoint that needs Pro access.

Auth pattern matches api/email_calendar.py — get_current_user returns a
user_id string and takes (request, db) directly. Webhook endpoint is the
exception: no auth, signature verification instead.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db
from services.razorpay_service import (
    get_razorpay_service,
    SUPPORTED_PLANS,
    PRO_MONTHLY_PLAN,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


# ============================================================================
# Auth helper — mirrors api/email_calendar.py pattern
# ============================================================================

async def get_user_id(request: Request, db: AsyncSession) -> str:
    """Extract authenticated user_id from JWT. 401 if missing."""
    from api.auth import get_current_user
    user_id = await get_current_user(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


async def get_user_email(user_id: str, db: AsyncSession) -> Optional[str]:
    """Fetch the user's email from the users table. None if not found."""
    try:
        result = await db.execute(
            text("SELECT email FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )
        row = result.fetchone()
        return row[0] if row else None
    except Exception:
        logger.exception(f"Could not fetch email for user {user_id[:8]}")
        return None


# ============================================================================
# Subscription helpers — shared by /webhook, /verify, /me, require_pro
# ============================================================================

async def get_active_subscription(user_id: str, db: AsyncSession) -> Optional[dict]:
    """Return the user's currently active subscription, or None."""
    result = await db.execute(
        text("""
            SELECT plan, started_at, expires_at
            FROM subscriptions
            WHERE user_id = :user_id
              AND is_active = TRUE
              AND expires_at > NOW()
            ORDER BY expires_at DESC
            LIMIT 1
        """),
        {"user_id": str(user_id)}
    )
    row = result.fetchone()
    if not row:
        return None
    return {
        "plan": row[0],
        "started_at": row[1],
        "expires_at": row[2],
    }


async def activate_subscription(
    user_id: str,
    plan: str,
    payment_id: str,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    db: AsyncSession,
) -> None:
    """
    Mark a user Pro by creating a subscription row. Idempotent — if the same
    razorpay_payment_id already exists (UNIQUE constraint), no-op.

    If user has an active subscription, the new one stacks on top of it
    (started_at = current expires_at) so the user gets full value.
    """
    plan_config = SUPPORTED_PLANS.get(plan)
    if not plan_config:
        logger.error(f"Cannot activate unknown plan: {plan}")
        return

    duration_days = plan_config["duration_days"]
    now = datetime.now(timezone.utc)

    # Find latest active subscription to stack on top of
    result = await db.execute(
        text("""
            SELECT expires_at FROM subscriptions
            WHERE user_id = :user_id
              AND is_active = TRUE
              AND expires_at > :now
            ORDER BY expires_at DESC
            LIMIT 1
        """),
        {"user_id": str(user_id), "now": now}
    )
    row = result.fetchone()

    start_at = row[0] if row else now
    expires_at = start_at + timedelta(days=duration_days)

    await db.execute(
        text("""
            INSERT INTO subscriptions (
                user_id, plan, payment_id,
                razorpay_order_id, razorpay_payment_id,
                started_at, expires_at, is_active
            ) VALUES (
                :user_id, :plan, :payment_id,
                :order_id, :payment_rp_id,
                :started_at, :expires_at, TRUE
            )
            ON CONFLICT (razorpay_payment_id) DO NOTHING
        """),
        {
            "user_id": str(user_id),
            "plan": plan,
            "payment_id": str(payment_id) if payment_id else None,
            "order_id": razorpay_order_id,
            "payment_rp_id": razorpay_payment_id,
            "started_at": start_at,
            "expires_at": expires_at,
        }
    )

    logger.info(
        f"Activated subscription: user={str(user_id)[:8]} plan={plan} "
        f"starts={start_at.isoformat()} expires={expires_at.isoformat()}"
    )


# ============================================================================
# #44 — Pro gate
# ============================================================================

async def require_pro(request: Request, db: AsyncSession) -> str:
    """
    Pro gate: ensure user is authenticated AND has active Pro subscription.

    Use as the first call in any endpoint that should be Pro-only.

    Returns: user_id (str) if user is Pro
    Raises:
        401 if not authenticated
        402 Payment Required if authenticated but not Pro

    Usage:
        @router.post("/some-pro-feature")
        async def feature_endpoint(
            body: SomeBody,
            request: Request,
            db: AsyncSession = Depends(get_db),
        ):
            user_id = await require_pro(request, db)
            # ... endpoint code, user is guaranteed Pro
    """
    user_id = await get_user_id(request, db)
    sub = await get_active_subscription(user_id, db)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "pro_required",
                "message": "This feature requires OmniAI Pro. Upgrade to continue.",
                "plan": PRO_MONTHLY_PLAN,
                "upgrade_endpoint": "/api/v1/payments/create-order",
            }
        )
    return user_id


# ============================================================================
# Request / Response schemas
# ============================================================================

class CreateOrderRequest(BaseModel):
    plan: str = Field(default=PRO_MONTHLY_PLAN, description="Plan key (e.g. 'pro_monthly')")


class CreateOrderResponse(BaseModel):
    order_id: str
    razorpay_key_id: str
    amount: int       # in paise
    currency: str
    plan: str
    plan_label: str
    plan_description: str
    user_email: Optional[str] = None


class PaymentKeyResponse(BaseModel):
    key_id: str


class PlanInfo(BaseModel):
    key: str
    label: str
    description: str
    amount: int
    amount_display: str
    currency: str
    duration_days: int


class PlansResponse(BaseModel):
    plans: list[PlanInfo]


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class VerifyPaymentResponse(BaseModel):
    verified: bool
    is_pro: bool
    plan: Optional[str] = None
    expires_at: Optional[str] = None


class MeResponse(BaseModel):
    is_pro: bool
    plan: Optional[str] = None
    started_at: Optional[str] = None
    expires_at: Optional[str] = None


# ============================================================================
# Public endpoints (#41)
# ============================================================================

@router.get("/key", response_model=PaymentKeyResponse)
async def get_razorpay_key():
    """Return the public Razorpay key id for frontend Checkout init."""
    rp = get_razorpay_service()
    return PaymentKeyResponse(key_id=rp.key_id)


@router.get("/plans", response_model=PlansResponse)
async def list_plans():
    """List all available subscription plans for the pricing page."""
    plans = []
    for key, cfg in SUPPORTED_PLANS.items():
        amount_rupees = cfg["amount"] / 100
        amount_display = (
            f"₹{amount_rupees:.0f}"
            if amount_rupees == int(amount_rupees)
            else f"₹{amount_rupees:.2f}"
        )
        plans.append(PlanInfo(
            key=key,
            label=cfg["label"],
            description=cfg["description"],
            amount=cfg["amount"],
            amount_display=amount_display,
            currency=cfg["currency"],
            duration_days=cfg["duration_days"],
        ))
    return PlansResponse(plans=plans)


@router.post("/create-order", response_model=CreateOrderResponse)
async def create_order(
    body: CreateOrderRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a Razorpay order for the current user."""
    user_id = await get_user_id(request, db)

    if body.plan not in SUPPORTED_PLANS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported plan: {body.plan}",
        )

    plan_config = SUPPORTED_PLANS[body.plan]
    rp = get_razorpay_service()
    user_email = await get_user_email(user_id, db)

    try:
        order = rp.create_order(
            plan=body.plan,
            user_id=user_id,
            user_email=user_email,
        )
    except Exception as e:
        logger.exception(f"Razorpay order creation failed for user {user_id[:8]}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not create payment order. Please try again in a moment.",
        )

    try:
        await db.execute(
            text("""
                INSERT INTO payments (
                    user_id, razorpay_order_id, amount, currency,
                    status, plan, notes
                ) VALUES (
                    :user_id, :order_id, :amount, :currency,
                    :status, :plan, CAST(:notes AS JSONB)
                )
                ON CONFLICT (razorpay_order_id) DO NOTHING
            """),
            {
                "user_id": str(user_id),
                "order_id": order["id"],
                "amount": plan_config["amount"],
                "currency": plan_config["currency"],
                "status": "created",
                "plan": body.plan,
                "notes": '{"created_via": "checkout"}',
            },
        )
        await db.commit()
        logger.info(f"Saved payment record for order {order['id']} (user {user_id[:8]})")
    except Exception:
        logger.exception(f"Failed to persist payment for order {order['id']}")
        await db.rollback()

    return CreateOrderResponse(
        order_id=order["id"],
        razorpay_key_id=rp.key_id,
        amount=plan_config["amount"],
        currency=plan_config["currency"],
        plan=body.plan,
        plan_label=plan_config["label"],
        plan_description=plan_config["description"],
        user_email=user_email,
    )


# ============================================================================
# Webhook handler (#42)
# ============================================================================

async def _record_webhook_event(
    db: AsyncSession,
    event_id: str,
    event_type: str,
    payload: dict,
) -> bool:
    """Record this webhook event. Returns True if new, False if duplicate."""
    try:
        result = await db.execute(
            text("""
                INSERT INTO webhook_events (provider, event_id, event_type, payload)
                VALUES ('razorpay', :event_id, :event_type, CAST(:payload AS JSONB))
                ON CONFLICT (provider, event_id) DO NOTHING
                RETURNING id
            """),
            {
                "event_id": event_id,
                "event_type": event_type,
                "payload": json.dumps(payload),
            }
        )
        row = result.fetchone()
        await db.commit()
        return row is not None
    except Exception:
        logger.exception("Failed to record webhook event")
        await db.rollback()
        return True


async def _handle_payment_captured(payload: dict, db: AsyncSession) -> dict:
    """Process payment.captured event."""
    payment_entity = (
        payload.get("payload", {}).get("payment", {}).get("entity", {})
    )
    razorpay_payment_id = payment_entity.get("id")
    razorpay_order_id = payment_entity.get("order_id")
    amount_paid = payment_entity.get("amount", 0)

    if not razorpay_order_id:
        logger.error("payment.captured webhook missing order_id")
        return {"status": "ignored", "reason": "no_order_id"}

    result = await db.execute(
        text("""
            UPDATE payments
            SET status = 'captured',
                razorpay_payment_id = :payment_id,
                captured_at = NOW()
            WHERE razorpay_order_id = :order_id
              AND status = 'created'
            RETURNING id, user_id, plan
        """),
        {"payment_id": razorpay_payment_id, "order_id": razorpay_order_id}
    )
    row = result.fetchone()

    if not row:
        check = await db.execute(
            text("SELECT status FROM payments WHERE razorpay_order_id = :order_id"),
            {"order_id": razorpay_order_id}
        )
        existing = check.fetchone()
        if existing and existing[0] == "captured":
            await db.commit()
            return {"status": "ok", "reason": "already_captured"}
        else:
            await db.rollback()
            logger.warning(f"No payment record for order {razorpay_order_id}")
            return {"status": "ignored", "reason": "payment_not_found"}

    payment_db_id, user_id, plan = row[0], row[1], row[2]

    await activate_subscription(
        user_id=str(user_id),
        plan=plan,
        payment_id=str(payment_db_id),
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        db=db,
    )
    await db.commit()

    logger.info(
        f"✅ Payment captured: order={razorpay_order_id} "
        f"payment={razorpay_payment_id} user={str(user_id)[:8]} amount={amount_paid}"
    )
    return {"status": "ok", "reason": "captured"}


async def _handle_payment_failed(payload: dict, db: AsyncSession) -> dict:
    """Process payment.failed event."""
    payment_entity = (
        payload.get("payload", {}).get("payment", {}).get("entity", {})
    )
    razorpay_order_id = payment_entity.get("order_id")
    razorpay_payment_id = payment_entity.get("id")

    if not razorpay_order_id:
        return {"status": "ignored", "reason": "no_order_id"}

    try:
        await db.execute(
            text("""
                UPDATE payments
                SET status = 'failed',
                    razorpay_payment_id = :payment_id
                WHERE razorpay_order_id = :order_id
                  AND status IN ('created', 'attempted')
            """),
            {"payment_id": razorpay_payment_id, "order_id": razorpay_order_id}
        )
        await db.commit()
        logger.info(f"Payment failed: order={razorpay_order_id}")
        return {"status": "ok", "reason": "marked_failed"}
    except Exception:
        await db.rollback()
        logger.exception("Failed to mark payment failed")
        return {"status": "ignored", "reason": "db_error"}


@router.post("/webhook")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Razorpay webhook receiver. NOT authenticated — verified via signature."""
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    rp = get_razorpay_service()

    if not rp.verify_webhook_signature(body, signature):
        logger.warning(
            f"Invalid Razorpay webhook signature from {request.client.host if request.client else 'unknown'}"
        )
        return {"status": "ignored", "reason": "invalid_signature"}

    try:
        payload = json.loads(body)
    except Exception:
        logger.exception("Could not parse webhook body as JSON")
        return {"status": "ignored", "reason": "invalid_body"}

    event_type = payload.get("event", "")
    event_id = payload.get("id") or payload.get("event_id") or ""

    if event_id:
        is_new = await _record_webhook_event(db, event_id, event_type, payload)
        if not is_new:
            logger.info(f"Skipping duplicate webhook event {event_id} ({event_type})")
            return {"status": "ok", "reason": "duplicate"}

    try:
        if event_type == "payment.captured":
            return await _handle_payment_captured(payload, db)
        elif event_type == "payment.failed":
            return await _handle_payment_failed(payload, db)
        else:
            logger.info(f"Unhandled webhook event type: {event_type}")
            return {"status": "ignored", "reason": "unhandled_event"}
    except Exception:
        logger.exception(f"Error processing webhook event {event_id} ({event_type})")
        return {"status": "ignored", "reason": "internal_error"}


# ============================================================================
# Optimistic verify (#42)
# ============================================================================

@router.post("/verify", response_model=VerifyPaymentResponse)
async def verify_payment(
    body: VerifyPaymentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Called by frontend immediately after Razorpay Checkout completes."""
    user_id = await get_user_id(request, db)
    rp = get_razorpay_service()

    is_valid = rp.verify_payment_signature(
        order_id=body.razorpay_order_id,
        payment_id=body.razorpay_payment_id,
        signature=body.razorpay_signature,
    )

    if not is_valid:
        logger.warning(
            f"Invalid payment signature: user={user_id[:8]} "
            f"order={body.razorpay_order_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment signature",
        )

    result = await db.execute(
        text("""
            SELECT id, user_id, status, plan
            FROM payments
            WHERE razorpay_order_id = :order_id
        """),
        {"order_id": body.razorpay_order_id}
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment record not found",
        )

    payment_db_id, payment_user_id, payment_status, payment_plan = row[0], row[1], row[2], row[3]

    if str(payment_user_id) != str(user_id):
        logger.warning(
            f"User {user_id[:8]} tried to verify payment belonging to {str(payment_user_id)[:8]}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Payment does not belong to this user",
        )

    if payment_status == "created":
        try:
            update_result = await db.execute(
                text("""
                    UPDATE payments
                    SET status = 'captured',
                        razorpay_payment_id = :payment_id,
                        captured_at = NOW()
                    WHERE id = :id AND status = 'created'
                    RETURNING id
                """),
                {"payment_id": body.razorpay_payment_id, "id": payment_db_id}
            )
            updated = update_result.fetchone()

            if updated:
                await activate_subscription(
                    user_id=user_id,
                    plan=payment_plan,
                    payment_id=str(payment_db_id),
                    razorpay_order_id=body.razorpay_order_id,
                    razorpay_payment_id=body.razorpay_payment_id,
                    db=db,
                )
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Failed to optimistically activate subscription")

    sub = await get_active_subscription(user_id, db)
    return VerifyPaymentResponse(
        verified=True,
        is_pro=sub is not None,
        plan=sub["plan"] if sub else None,
        expires_at=sub["expires_at"].isoformat() if sub else None,
    )


# ============================================================================
# Subscription state (#43)
# ============================================================================

@router.get("/me", response_model=MeResponse)
async def get_my_subscription(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return current user's subscription state for frontend Pro badge."""
    user_id = await get_user_id(request, db)
    sub = await get_active_subscription(user_id, db)

    if not sub:
        return MeResponse(is_pro=False)

    return MeResponse(
        is_pro=True,
        plan=sub["plan"],
        started_at=sub["started_at"].isoformat() if sub["started_at"] else None,
        expires_at=sub["expires_at"].isoformat(),
    )


# ============================================================================
# #44 — Pro gate verification endpoint
# ============================================================================

@router.get("/pro-test")
async def pro_only_test(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Test endpoint to verify the require_pro gate works correctly.

    Expected behavior:
      - No auth         → 401 Unauthorized
      - Auth but no Pro → 402 Payment Required
      - Auth + Pro      → 200 with subscription details

    This endpoint stays in place as a permanent "am I Pro?" diagnostic.
    """
    user_id = await require_pro(request, db)
    sub = await get_active_subscription(user_id, db)
    return {
        "is_pro": True,
        "user_id_prefix": user_id[:8],
        "plan": sub["plan"],
        "expires_at": sub["expires_at"].isoformat(),
        "message": "🎉 You're a Pro user! This gated endpoint confirms it works.",
    }