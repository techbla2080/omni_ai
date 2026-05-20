"""
#47 — Pro gating decorator.

Apply @require_pro to any endpoint that should be paywalled.
Free users hitting these endpoints get HTTP 402 Payment Required with a
structured response the frontend can catch and turn into an upgrade modal.

Usage:
    from api.pro_gate import require_pro

    @router.post("/api/v1/gmail/send")
    async def send_email(
        ...,
        _pro: None = Depends(require_pro("gmail_send"))
    ):
        ...
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db
from api.auth import get_current_user


# Map feature keys to user-facing labels shown in the upgrade modal.
FEATURE_LABELS = {
    "gmail_send":          "Send emails via Gmail",
    "calendar_create":     "Create calendar events",
    "custom_prompt":       "Custom AI personality",
    "memory_extended":     "Unlimited memories",
    "email_to_calendar":   "Book meetings from emails",
}


async def _user_is_pro(db: AsyncSession, user_id: str) -> bool:
    """
    Returns True if user has an active, non-expired Pro subscription.
    Uses raw SQL since there's no Subscription ORM model.
    """
    result = await db.execute(
        text("""
            SELECT id FROM subscriptions
            WHERE user_id = :uid
              AND is_active = TRUE
              AND expires_at > NOW()
            ORDER BY expires_at DESC
            LIMIT 1
        """),
        {"uid": user_id},
    )
    return result.first() is not None


def require_pro(feature_name: str):
    """
    Returns a FastAPI dependency that raises 402 if the current user
    is not Pro.

    Args:
        feature_name: One of FEATURE_LABELS keys (or any string) — used
                      in the error response so the frontend can show
                      contextual messaging.
    """
    async def _checker(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> None:
        # Call auth manually — matches codebase pattern (get_current_user
        # takes Request + db without being wrapped in Depends)
        user_id = await get_current_user(request, db)

        if await _user_is_pro(db, user_id):
            return  # Pro user — allow through

        # Free user — block with 402
        label = FEATURE_LABELS.get(feature_name, feature_name)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "pro_required",
                "feature": feature_name,
                "feature_label": label,
                "message": f"{label} is a Pro feature. Upgrade to OmniAI Pro for ₹499/month to unlock.",
            },
        )

    return _checker


async def get_pro_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> bool:
    """
    Non-blocking helper. Use this when an endpoint should gracefully
    degrade for free users (e.g. memory endpoint returns capped list)
    rather than 402-erroring out.
    """
    user_id = await get_current_user(request, db)
    return await _user_is_pro(db, user_id)