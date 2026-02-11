"""Memory decay / forgetting curve."""

from __future__ import annotations

import math
from datetime import datetime


def compute_decay(
    last_accessed: datetime,
    importance: int,
    access_count: int,
    rate: float = 0.01,
    now: datetime | None = None,
) -> float:
    """Return a decay score in [0, 1].

    Higher importance and access count slow down decay.
    Score of 1.0 = fully fresh, 0.0 = completely decayed.
    """
    now = now or datetime.utcnow()
    hours_since = max((now - last_accessed).total_seconds() / 3600, 0)

    # importance 10 → factor 0.1, importance 1 → factor 1.0
    importance_factor = 1.0 / max(importance, 1)

    # frequent access slows decay
    access_factor = 1.0 / (1 + math.log1p(access_count))

    effective_rate = rate * importance_factor * access_factor
    return math.exp(-effective_rate * hours_since)
