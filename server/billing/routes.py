"""Billing API routes — checkout, webhooks, portal."""

from __future__ import annotations

import logging
import os
import uuid

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
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
def checkout_pro():
    """Start a Pro subscription from the landing page. No auth required.

    Stripe collects email during checkout. After payment, the webhook
    creates the Engram account and sends the API key.
    """
    success_url = f"{BASE_URL}/?checkout=success"
    cancel_url = f"{BASE_URL}/?checkout=cancel"

    checkout_url = create_public_checkout_session(
        tier="pro",
        success_url=success_url,
        cancel_url=cancel_url,
    )

    return CheckoutResponse(checkout_url=checkout_url)


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
        except stripe.error.SignatureVerificationError:
            raise HTTPException(400, "Invalid webhook signature")
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

    For the public landing-page flow (no pre-existing account) this
    auto-creates an Engram user, generates an API key, and links the
    Stripe customer.  The email with the API key is a TODO.
    """
    customer_id = session.get("customer")
    tier = session.get("metadata", {}).get("engram_tier", "pro")
    subscription_id = session.get("subscription")
    customer_email = session.get("customer_details", {}).get("email", "")

    user = _get_user_by_stripe_customer(customer_id)

    if not user and customer_email:
        # Check if a user with this email already exists
        user = db.get_user_by_email(customer_email)

        if not user:
            # Auto-create account for landing page checkout
            user_id = str(uuid.uuid4())
            temp_pw = hash_password(uuid.uuid4().hex)  # unusable random password
            user = db.create_user(user_id, customer_email, temp_pw, tier=tier)
            log.info("Auto-created user %s for Stripe customer %s", user_id, customer_id)

        # Link Stripe customer to user
        db.update_stripe_customer_id(user["id"], customer_id)

        # Generate an API key for the new user
        key_id, full_key, key_hash = generate_api_key()
        db.store_api_key(key_id, user["id"], key_hash, full_key[:20], name="pro-checkout")
        log.info("Generated API key %s... for user %s", full_key[:20], user["id"])
        # TODO: send welcome email with full_key to customer_email

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
    """Handle failed payment — could send notification, for now just log."""
    customer_id = invoice.get("customer")
    user = _get_user_by_stripe_customer(customer_id)
    if user:
        # TODO: Send email notification about failed payment
        pass
