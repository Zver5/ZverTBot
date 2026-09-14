from datetime import datetime, timedelta, timezone

from services.vps_status_source import (
    DEFAULT_MAX_STATS_AGE_SECONDS,
    is_stats_payload_fresh,
    stats_payload_age_seconds,
)


def test_stats_payload_freshness_accepts_recent_timestamp():
    now = datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc)
    data = {"vps_stats_last_check": (now - timedelta(minutes=2)).isoformat()}

    assert stats_payload_age_seconds(data, now=now) == 120
    assert is_stats_payload_fresh(data, now=now)


def test_stats_payload_freshness_rejects_stale_timestamp():
    now = datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc)
    data = {
        "vps_stats_last_check": (
            now - timedelta(seconds=DEFAULT_MAX_STATS_AGE_SECONDS + 1)
        ).isoformat()
    }

    assert not is_stats_payload_fresh(data, now=now)


def test_stats_payload_freshness_rejects_missing_or_invalid_timestamp():
    now = datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc)

    assert stats_payload_age_seconds({}, now=now) is None
    assert not is_stats_payload_fresh({}, now=now)
    assert not is_stats_payload_fresh(
        {"vps_stats_last_check": "not-a-timestamp"},
        now=now,
    )
