"""Billing API routes — checkout, webhooks, portal."""

from __future__ import annotations

import logging
import os
import uuid

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from server.auth import database as db
from server.auth.api_keys import generate_api_key
from server.auth.dependencies import AuthUser, require_auth
from server.auth.passwords import hash_password
from server.billing.stripe_client import (
    create_checkout_session,
    create_customer,
    create_portal_session,
    create_public_checkout_session,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/billing", tags=["billing"])

WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
BASE_URL = os.environ.get("ENGRAM_BASE_URL", "https://engram-ai.dev")


# ------------------------------------------------------------------
# Request/Response models
# ------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    tier: str  # "pro" or "enterprise"
    success_url: str | None = None
    cancel_url: str | None = None


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalResponse(BaseModel):
    portal_url: str


class BillingStatus(BaseModel):
    tier: str
    stripe_customer_id: str | None
    subscription_active: bool


# ------------------------------------------------------------------
# Checkout — user starts a subscription
# ------------------------------------------------------------------


@router.post("/checkout", response_model=CheckoutResponse)
def checkout(body: CheckoutRequest, user: AuthUser = Depends(require_auth)):
    if body.tier not in ("pro", "enterprise"):
        raise HTTPException(400, "Invalid tier. Choose 'pro' or 'enterprise'.")

    if user.tier == body.tier:
        raise HTTPException(400, f"You are already on the {body.tier} plan.")

    # Get or create Stripe customer
    user_record = db.get_user_by_id(user.id)
    customer_id = user_record.get("stripe_customer_id")

    if not customer_id:
        customer_id = create_customer(user.email, user.id)
        db.update_stripe_customer_id(user.id, customer_id)

    success_url = (
        body.success_url or f"{BASE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
    )
    cancel_url = body.cancel_url or f"{BASE_URL}/billing/cancel"

    checkout_url = create_checkout_session(
        customer_id=customer_id,
        tier=body.tier,
        success_url=success_url,
        cancel_url=cancel_url,
    )

    return CheckoutResponse(checkout_url=checkout_url)


# ------------------------------------------------------------------
# Public Checkout — landing page flow (no auth required)
# ------------------------------------------------------------------


@router.post("/checkout/pro", response_model=CheckoutResponse)
def checkout_pro(interval: str = Query("monthly", pattern="^(monthly|yearly)$")):
    """Start a Pro subscription from the landing page. No auth required.

    Stripe collects email during checkout. After payment, the webhook
    creates the Engram account and sends the API key.

    Query params:
        interval: "monthly" (default) or "yearly"
    """
    success_url = f"{BASE_URL}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{BASE_URL}/?checkout=cancel"

    config_key = f"pro_{interval}"
    checkout_url = create_public_checkout_session(
        tier=config_key,
        success_url=success_url,
        cancel_url=cancel_url,
    )

    return CheckoutResponse(checkout_url=checkout_url)


# ------------------------------------------------------------------
# Activate — retrieve API key after successful checkout
# ------------------------------------------------------------------


@router.get("/activate")
def activate(session_id: str = Query(..., description="Stripe Checkout session ID")):
    """Exchange a Stripe checkout session for an API key.

    Called from the success page after payment. Verifies with Stripe
    that payment was completed, creates the user account if needed,
    and returns the API key exactly once.
    """
    # Verify with Stripe
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except (stripe.InvalidRequestError, Exception) as e:
        log.warning("Stripe session retrieval failed: %s", e)
        raise HTTPException(400, "Invalid session ID")

    if session.payment_status != "paid":
        raise HTTPException(402, "Payment not completed")

    customer_id = session.customer
    customer_email = session.customer_details.email if session.customer_details else ""
    tier = (session.metadata or {}).get("engram_tier", "pro")

    if not customer_email:
        raise HTTPException(400, "No email found in checkout session")

    # Create or find user
    user_id = _find_or_create_user(customer_email, customer_id, tier)

    # Check if key was already issued for this session
    existing_keys = db.get_api_keys_for_user_by_name(user_id, f"checkout:{session_id}")
    if existing_keys:
        raise HTTPException(
            409,
            "API key was already issued for this checkout. "
            "If you lost your key, contact levent@engram-ai.dev",
        )

    # Generate API key (name includes session_id for idempotency)
    key_id, full_key, key_hash = generate_api_key()
    db.store_api_key(key_id, user_id, key_hash, full_key[:20], name=f"checkout:{session_id}")
    log.info("Issued API key for user %s via activate endpoint", user_id)

    # Send welcome email (non-blocking, best effort)
    try:
        from server.email_service import send_welcome_email

        send_welcome_email(customer_email, full_key)
    except Exception as e:
        log.warning("Welcome email failed (non-critical): %s", e)

    return {
        "api_key": full_key,
        "email": customer_email,
        "tier": tier,
        "message": "Save this key now. It cannot be shown again.",
    }


def _find_or_create_user(email: str, stripe_customer_id: str, tier: str) -> str:
    """Find existing user or create one. Returns user_id."""
    # Try by Stripe customer ID first
    user = db.get_user_by_stripe_customer_id(stripe_customer_id)
    if user:
        # User paid — clear any active trial
        db.clear_user_trial(user["id"])
        return user["id"]

    # Try by email
    user = db.get_user_by_email(email)
    if user:
        db.update_stripe_customer_id(user["id"], stripe_customer_id)
        db.update_user_tier(user["id"], tier)
        db.clear_user_trial(user["id"])  # Trial → Paid
        return user["id"]

    # Create new user (paid directly, no trial)
    user_id = str(uuid.uuid4())
    temp_pw = hash_password(uuid.uuid4().hex)
    db.create_user(user_id, email, temp_pw, tier=tier)
    db.update_stripe_customer_id(user_id, stripe_customer_id)
    log.info("Auto-created user %s for %s", user_id, email)
    return user_id


# ------------------------------------------------------------------
# Customer Portal — manage subscription
# ------------------------------------------------------------------


@router.post("/portal", response_model=PortalResponse)
def portal(user: AuthUser = Depends(require_auth)):
    user_record = db.get_user_by_id(user.id)
    customer_id = user_record.get("stripe_customer_id")

    if not customer_id:
        raise HTTPException(400, "No active subscription. Use /v1/billing/checkout first.")

    return_url = f"{BASE_URL}/dashboard"
    portal_url = create_portal_session(customer_id, return_url)

    return PortalResponse(portal_url=portal_url)


# ------------------------------------------------------------------
# Billing status
# ------------------------------------------------------------------


@router.get("/status", response_model=BillingStatus)
def billing_status(user: AuthUser = Depends(require_auth)):
    user_record = db.get_user_by_id(user.id)
    return BillingStatus(
        tier=user.tier,
        stripe_customer_id=user_record.get("stripe_customer_id"),
        subscription_active=user.tier != "free",
    )


# ------------------------------------------------------------------
# Stripe Webhook — handle subscription events
# ------------------------------------------------------------------


@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
        except (stripe.SignatureVerificationError, Exception) as e:
            log.warning("Webhook signature verification failed: %s", e)
            raise HTTPException(400, "Invalid webhook signature")  # noqa: B904
    else:
        # Dev/test mode: parse without signature verification
        import json

        event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)

    event_type = event["type"]

    # Checkout completed — activate subscription
    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        _handle_checkout_completed(session)

    # Subscription updated (upgrade/downgrade)
    elif event_type == "customer.subscription.updated":
        subscription = event["data"]["object"]
        _handle_subscription_updated(subscription)

    # Subscription deleted (cancelled)
    elif event_type == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        _handle_subscription_deleted(subscription)

    # Invoice payment failed
    elif event_type == "invoice.payment_failed":
        invoice = event["data"]["object"]
        _handle_payment_failed(invoice)

    return {"status": "ok"}


# ------------------------------------------------------------------
# Webhook handlers
# ------------------------------------------------------------------


def _get_user_by_stripe_customer(customer_id: str) -> dict | None:
    """Look up Engram user by Stripe customer ID."""
    return db.get_user_by_stripe_customer_id(customer_id)


def _handle_checkout_completed(session: dict) -> None:
    """Activate tier after successful checkout.

    Creates the user account as a safety net — the /activate endpoint
    is the primary path for key delivery to the customer.
    """
    customer_id = session.get("customer")
    raw_tier = session.get("metadata", {}).get("engram_tier", "pro")
    tier = raw_tier if raw_tier in ("free", "pro", "enterprise") else "pro"
    subscription_id = session.get("subscription")
    customer_email = session.get("customer_details", {}).get("email", "")
    log.info("Checkout completed: customer=%s tier=%s email=%s", customer_id, tier, customer_email)

    if customer_email and customer_id:
        user_id = _find_or_create_user(customer_email, customer_id, tier)
        user = db.get_user_by_id(user_id)
    else:
        user = _get_user_by_stripe_customer(customer_id)

    if user:
        db.update_user_tier(user["id"], tier)
        db.update_stripe_subscription_id(user["id"], subscription_id)


def _handle_subscription_updated(subscription: dict) -> None:
    """Handle plan changes (upgrade/downgrade)."""
    customer_id = subscription.get("customer")
    user = _get_user_by_stripe_customer(customer_id)
    if not user:
        return

    # Determine tier from price metadata
    items = subscription.get("items", {}).get("data", [])
    if items:
        price = items[0].get("price", {})
        tier = price.get("metadata", {}).get("engram_tier", user["tier"])
        db.update_user_tier(user["id"], tier)


def _handle_subscription_deleted(subscription: dict) -> None:
    """Downgrade to free when subscription is cancelled."""
    customer_id = subscription.get("customer")
    user = _get_user_by_stripe_customer(customer_id)
    if user:
        db.update_user_tier(user["id"], "free")
        db.update_stripe_subscription_id(user["id"], None)


def _handle_payment_failed(invoice: dict) -> None:
    """Handle failed payment — log the event."""
    customer_id = invoice.get("customer")
    user = _get_user_by_stripe_customer(customer_id)
    if user:
        log.warning("Payment failed for user %s (customer=%s)", user["id"], customer_id)
