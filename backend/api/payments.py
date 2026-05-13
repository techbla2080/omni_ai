"""
Payments API — Razorpay integration for OmniAI Pro subscriptions.

Endpoints (this file — #41):
  GET  /api/v1/payments/key            → public Razorpay key for frontend init
  GET  /api/v1/payments/plans          → list available plans
  POST /api/v1/payments/create-order   → create order, return id for Checkout

Endpoints coming later:
  #42 POST /api/v1/payments/webhook    → Razorpay event receiver
  #42 POST /api/v1/payments/verify     → optimistic post-checkout verification
  #43 GET  /api/v1/payments/me         → current subscription state

Auth pattern matches api/email_calendar.py — get_current_user returns a
user_id string and takes (request, db) directly.
"""
import logging
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
    amount: int           # paise
    amount_display: str   # "₹499"
    currency: str
    duration_days: int


class PlansResponse(BaseModel):
    plans: list[PlanInfo]


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/key", response_model=PaymentKeyResponse)
async def get_razorpay_key():
    """
    Return the public Razorpay key id.
    Frontend needs this to initialize the Checkout SDK.
    Safe to expose — it's the "publishable" key.
    """
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
    """
    Create a Razorpay order for the current user.

    Flow:
      1. User clicks "Upgrade to Pro" in frontend
      2. Frontend calls this endpoint
      3. We create order on Razorpay, persist record in our DB
      4. We return order_id + key + amount
      5. Frontend opens Razorpay Checkout modal with these values
      6. User pays → Razorpay calls our webhook (#42) → we mark user Pro
    """
    # ---- Auth ----
    user_id = await get_user_id(request, db)

    # ---- Validate plan ----
    if body.plan not in SUPPORTED_PLANS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported plan: {body.plan}",
        )

    plan_config = SUPPORTED_PLANS[body.plan]
    rp = get_razorpay_service()

    # ---- Get user's email for Razorpay prefill (best-effort) ----
    user_email = await get_user_email(user_id, db)

    # ---- Create order on Razorpay ----
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

    # ---- Persist order in our DB ----
    # If this fails we still return success — webhook (#42) will reconcile.
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
        # Don't fail the request — order is live on Razorpay; webhook will reconcile

    # ---- Return everything the frontend needs to open Checkout ----
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