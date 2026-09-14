from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from config.paths import (
    STATS_JSON,
)


def load_prepared_vps_payload() -> dict[str, Any]:
    try:
        with open(STATS_JSON) as file:
            data = json.load(file)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


DEFAULT_MAX_STATS_AGE_SECONDS = 10 * 60


def stats_payload_age_seconds(
    data: dict[str, Any],
    *,
    now: datetime | None = None,
) -> float | None:
    """Return the age of a prepared VPS stats payload in seconds."""
    value = data.get("vps_stats_last_check")
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        updated_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    current = now or datetime.now(timezone.utc)
    return (current - updated_at.astimezone(timezone.utc)).total_seconds()


def is_stats_payload_fresh(
    data: dict[str, Any],
    *,
    max_age_seconds: int = DEFAULT_MAX_STATS_AGE_SECONDS,
    now: datetime | None = None,
) -> bool:
    """Return whether VPS stats exist and were collected recently enough."""
    age = stats_payload_age_seconds(data, now=now)
    return age is not None and 0 <= age <= max_age_seconds
