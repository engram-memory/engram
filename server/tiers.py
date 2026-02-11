"""Subscription tier definitions and limits."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TierLimits:
    name: str
    max_memories: int  # 0 = unlimited
    max_storage_mb: int
    max_namespaces: int  # 0 = unlimited
    requests_per_second: int
    requests_per_month: int
    retention_days: int  # 0 = unlimited
    semantic_search: bool
    websocket: bool
    analytics: bool
    webhooks: int  # max webhook endpoints, 0 = none
    max_api_keys: int
    custom_embeddings: bool
    sso: bool
    audit_logs: bool
    priority_support: bool


FREE = TierLimits(
    name="free",
    max_memories=5_000,
    max_storage_mb=50,
    max_namespaces=2,
    requests_per_second=5,
    requests_per_month=50_000,
    retention_days=90,
    semantic_search=False,
    websocket=False,
    analytics=False,
    webhooks=0,
    max_api_keys=2,
    custom_embeddings=False,
    sso=False,
    audit_logs=False,
    priority_support=False,
)

PRO = TierLimits(
    name="pro",
    max_memories=250_000,
    max_storage_mb=5_000,
    max_namespaces=25,
    requests_per_second=50,
    requests_per_month=5_000_000,
    retention_days=365,
    semantic_search=True,
    websocket=True,
    analytics=True,
    webhooks=10,
    max_api_keys=25,
    custom_embeddings=False,
    sso=False,
    audit_logs=False,
    priority_support=False,
)

ENTERPRISE = TierLimits(
    name="enterprise",
    max_memories=0,
    max_storage_mb=100_000,
    max_namespaces=0,
    requests_per_second=200,
    requests_per_month=0,
    retention_days=0,
    semantic_search=True,
    websocket=True,
    analytics=True,
    webhooks=0,  # unlimited
    max_api_keys=0,  # unlimited
    custom_embeddings=True,
    sso=True,
    audit_logs=True,
    priority_support=True,
)

TIERS: dict[str, TierLimits] = {
    "free": FREE,
    "pro": PRO,
    "enterprise": ENTERPRISE,
}


def get_tier(name: str) -> TierLimits:
    return TIERS.get(name, FREE)
