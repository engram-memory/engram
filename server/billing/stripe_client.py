"""Stripe client setup and product/price management."""

from __future__ import annotations

import os
from functools import lru_cache

import stripe

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

# Pricing: monthly in cents
PRICE_CONFIG = {
    "pro_monthly": {
        "name": "Engram Pro (Monthly)",
        "description": "250K memories, Memory Links, AutoSave, Synapse, semantic search, analytics",
        "amount": 1990,  # €19.90
        "currency": "eur",
        "interval": "month",
        "tier": "pro",
    },
    "pro_yearly": {
        "name": "Engram Pro (Yearly)",
        "description": "250K memories, Memory Links, AutoSave, Synapse, semantic search, analytics",
        "amount": 18900,  # €189.00/year (€15.75/mo, 20% off)
        "currency": "eur",
        "interval": "year",
        "tier": "pro",
    },
    "enterprise": {
        "name": "Engram Enterprise",
        "description": "Unlimited memories, SSO, audit logs, priority support",
        "amount": 19900,  # €199.00
        "currency": "eur",
        "interval": "month",
        "tier": "enterprise",
    },
}

# Backwards-compat alias
PRICE_CONFIG["pro"] = PRICE_CONFIG["pro_monthly"]


def _find_or_create_product(config_key: str) -> str:
    """Find existing Engram product or create it. Returns product ID."""
    config = PRICE_CONFIG[config_key]
    tier = config.get("tier", config_key)

    # Search for existing product by metadata
    products = stripe.Product.search(query=f'metadata["engram_tier"]:"{tier}"')
    if products.data:
        return products.data[0].id

    product = stripe.Product.create(
        name=config["name"],
        description=config["description"],
        metadata={"engram_tier": tier},
    )
    return product.id


def _find_or_create_price(config_key: str, product_id: str) -> str:
    """Find existing price or create it. Returns price ID."""
    config = PRICE_CONFIG[config_key]
    interval = config.get("interval", "month")
    tier = config.get("tier", config_key)

    prices = stripe.Price.list(product=product_id, active=True)
    for price in prices.data:
        if (
            price.unit_amount == config["amount"]
            and price.currency == config["currency"]
            and price.recurring
            and price.recurring.interval == interval
        ):
            return price.id

    price = stripe.Price.create(
        product=product_id,
        unit_amount=config["amount"],
        currency=config["currency"],
        recurring={"interval": interval},
        metadata={"engram_tier": tier},
    )
    return price.id


@lru_cache
def get_price_id(config_key: str) -> str:
    """Get or create the Stripe price ID for a config key (e.g. 'pro_monthly', 'pro_yearly')."""
    if config_key not in PRICE_CONFIG:
        raise ValueError(f"No pricing for: {config_key}")
    product_id = _find_or_create_product(config_key)
    return _find_or_create_price(config_key, product_id)


def create_customer(email: str, user_id: str) -> str:
    """Create a Stripe customer. Returns customer ID."""
    customer = stripe.Customer.create(
        email=email,
        metadata={"engram_user_id": user_id},
    )
    return customer.id


def create_checkout_session(
    customer_id: str,
    tier: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Create a Stripe Checkout session. Returns session URL."""
    price_id = get_price_id(tier)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"engram_tier": tier},
    )
    return session.url


def create_public_checkout_session(
    tier: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Create a Stripe Checkout session without a customer (landing page flow).

    Stripe collects the email during checkout. The webhook creates the
    Engram account after successful payment.
    """
    price_id = get_price_id(tier)

    session = stripe.checkout.Session.create(
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"engram_tier": tier},
    )
    return session.url


def create_portal_session(customer_id: str, return_url: str) -> str:
    """Create a Stripe Customer Portal session. Returns portal URL."""
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session.url
