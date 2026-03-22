from __future__ import annotations

"""
Stripe billing service — subscriptions, checkout, and webhook handling.

Tier structure:
  - free: 3 sessions, basic stats, no AI
  - pro: unlimited sessions, full analytics, AI analysis, 3 profiles
  - pro_plus: everything in pro + unlimited profiles, priority support

Stripe integration pattern:
  1. User clicks "Upgrade" → frontend calls create_checkout_session
  2. We create a Stripe Checkout Session → return URL
  3. User completes payment on Stripe's hosted page
  4. Stripe fires webhook → we update user.subscription_tier
  5. On cancellation, Stripe fires webhook → we downgrade at period end
"""

from datetime import datetime, timezone

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.user import User


def _configure_stripe() -> None:
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured")
    stripe.api_key = settings.stripe_secret_key


# ═══════════════════════════════════════════════
# Checkout
# ═══════════════════════════════════════════════


async def create_checkout_session(
    db: AsyncSession,
    user: User,
    *,
    price_id: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """
    Create a Stripe Checkout Session for subscription.

    Returns the checkout URL for the frontend to redirect to.
    """
    _configure_stripe()

    # Track if this is a new Stripe customer (for trial coupon)
    is_new_customer = not user.stripe_customer_id

    # Create or reuse Stripe customer
    if is_new_customer:
        customer = stripe.Customer.create(
            email=user.email,
            name=user.display_name,
            metadata={"user_id": str(user.id)},
        )
        user.stripe_customer_id = customer.id
        await db.commit()

    settings = get_settings()
    session_kwargs: dict = {
        "customer": user.stripe_customer_id,
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {"user_id": str(user.id)},
        "subscription_data": {
            "metadata": {"user_id": str(user.id)},
        },
        "allow_promotion_codes": True,
    }

    # Apply trial coupon for first-time subscribers ($1.99 first month)
    if settings.stripe_trial_coupon and is_new_customer:
        session_kwargs["discounts"] = [{"coupon": settings.stripe_trial_coupon}]
        session_kwargs.pop("allow_promotion_codes", None)  # Can't combine with discounts

    session = stripe.checkout.Session.create(**session_kwargs)

    return session.url


async def create_billing_portal_session(
    user: User,
    *,
    return_url: str,
) -> str:
    """
    Create a Stripe Billing Portal session for managing subscription.

    Allows users to update payment method, view invoices, cancel, etc.
    """
    _configure_stripe()

    if not user.stripe_customer_id:
        raise ValidationError("No active subscription to manage")

    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=return_url,
    )

    return session.url


# ═══════════════════════════════════════════════
# Webhook handling
# ═══════════════════════════════════════════════

# Map Stripe price IDs to our tier names
def _get_price_tier_map() -> dict[str, str]:
    settings = get_settings()
    return {
        settings.stripe_price_pro_monthly: "pro",
        settings.stripe_price_pro_yearly: "pro",
        settings.stripe_price_pro_plus_monthly: "pro_plus",
        settings.stripe_price_pro_plus_yearly: "pro_plus",
    }


async def handle_webhook_event(
    db: AsyncSession,
    payload: bytes,
    sig_header: str,
) -> dict:
    """
    Process a Stripe webhook event.

    Verifies the signature, parses the event, and updates the database.
    Returns a dict with the action taken for logging.
    """
    _configure_stripe()
    settings = get_settings()

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        raise ValidationError("Invalid webhook signature")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        return await _handle_checkout_completed(db, data)

    elif event_type == "customer.subscription.updated":
        return await _handle_subscription_updated(db, data)

    elif event_type == "customer.subscription.deleted":
        return await _handle_subscription_deleted(db, data)

    elif event_type == "invoice.payment_failed":
        return await _handle_payment_failed(db, data)

    return {"action": "ignored", "event_type": event_type}


async def _handle_checkout_completed(
    db: AsyncSession, session_data: dict
) -> dict:
    """New subscription created via Checkout."""
    user_id = session_data.get("metadata", {}).get("user_id")
    if not user_id:
        return {"action": "skipped", "reason": "no user_id in metadata"}

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return {"action": "skipped", "reason": f"user {user_id} not found"}

    # Get the subscription to determine tier
    sub_id = session_data.get("subscription")
    if sub_id:
        subscription = stripe.Subscription.retrieve(sub_id)
        price_id = subscription["items"]["data"][0]["price"]["id"]
        tier_map = _get_price_tier_map()
        tier = tier_map.get(price_id, "pro")

        user.subscription_tier = tier
        user.stripe_customer_id = session_data.get("customer", user.stripe_customer_id)
        await db.commit()

        return {"action": "upgraded", "user_id": user_id, "tier": tier}

    return {"action": "skipped", "reason": "no subscription in session"}


async def _handle_subscription_updated(
    db: AsyncSession, subscription: dict
) -> dict:
    """Subscription changed (upgrade, downgrade, renewal)."""
    user_id = subscription.get("metadata", {}).get("user_id")
    if not user_id:
        # Try finding by customer ID
        customer_id = subscription.get("customer")
        if customer_id:
            result = await db.execute(
                select(User).where(User.stripe_customer_id == customer_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user_id = str(user.id)

    if not user_id:
        return {"action": "skipped", "reason": "cannot identify user"}

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return {"action": "skipped", "reason": f"user {user_id} not found"}

    status = subscription.get("status")
    if status == "active":
        price_id = subscription["items"]["data"][0]["price"]["id"]
        tier_map = _get_price_tier_map()
        tier = tier_map.get(price_id, "pro")
        user.subscription_tier = tier
    elif status in ("past_due", "unpaid"):
        # Keep tier but flag — could add a grace period
        pass
    elif status in ("canceled", "incomplete_expired"):
        user.subscription_tier = "free"

    await db.commit()
    return {"action": "updated", "user_id": user_id, "status": status}


async def _handle_subscription_deleted(
    db: AsyncSession, subscription: dict
) -> dict:
    """Subscription canceled — downgrade to free."""
    customer_id = subscription.get("customer")
    if not customer_id:
        return {"action": "skipped", "reason": "no customer_id"}

    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return {"action": "skipped", "reason": f"customer {customer_id} not found"}

    user.subscription_tier = "free"
    await db.commit()

    return {"action": "downgraded", "user_id": str(user.id)}


async def _handle_payment_failed(
    db: AsyncSession, invoice: dict
) -> dict:
    """Payment failed — log it, Stripe handles retry logic."""
    customer_id = invoice.get("customer")
    return {
        "action": "payment_failed",
        "customer_id": customer_id,
        "amount": invoice.get("amount_due"),
        "attempt": invoice.get("attempt_count"),
    }
