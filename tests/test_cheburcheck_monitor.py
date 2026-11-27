import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from services.cheburcheck_monitor import (
    CHECK_INTERVAL,
    RETRY_INTERVAL,
    check_due,
    clear_pending_notification,
)


class FakeResponse:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


def call_api(payload, requests=None):
    def opener(request, timeout):
        if requests is not None:
            requests.append((request, timeout))
        return FakeResponse(payload)

    return opener


def test_blocked_first_check_creates_alert(tmp_path):
    now = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
    requests = []
    result = {
        "blocked": True,
        "target_type": "ip",
        "blocked_subnets": ["203.0.113.0/24"],
        "rkn_domain": "<script>alert(1)</script>",
    }

    state = check_due(
        path=tmp_path / "state.json",
        target="203.0.113.10",
        now=now,
        opener=call_api(result, requests),
    )

    assert state["blocked"] is True
    assert state["last_checked_at"] == now.isoformat()
    assert state["next_check_at"] == (now + CHECK_INTERVAL).isoformat()
    assert state["last_error"] is None
    assert state["pending_notification"]["state"] == "down"
    assert "&lt;script&gt;" in state["pending_notification"]["message"]
    assert len(requests) == 1
    assert requests[0][1] == 20
    query = parse_qs(urlparse(requests[0][0].full_url).query)
    assert query["target"] == ["203.0.113.10"]


def test_clean_first_check_does_not_create_alert(tmp_path):
    state = check_due(
        path=tmp_path / "state.json",
        target="203.0.113.10",
        now=datetime(2026, 11, 27, tzinfo=timezone.utc),
        opener=call_api({"blocked": False}),
    )

    assert state["blocked"] is False
    assert "pending_notification" not in state


def test_blocked_to_clean_transition_creates_recovery_alert(tmp_path):
    path = tmp_path / "state.json"
    now = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
    path.write_text(
        json.dumps(
            {
                "target": "203.0.113.10",
                "blocked": True,
                "next_check_at": (now - timedelta(seconds=1)).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    state = check_due(
        path=path,
        target="203.0.113.10",
        now=now,
        opener=call_api({"blocked": False}),
    )

    assert state["blocked"] is False
    assert state["pending_notification"]["state"] == "up"
    assert "больше не обнаруживается" in state["pending_notification"]["message"]


def test_clean_to_blocked_transition_creates_alert(tmp_path):
    path = tmp_path / "state.json"
    now = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
    path.write_text(
        json.dumps(
            {
                "target": "203.0.113.10",
                "blocked": False,
                "next_check_at": (now - timedelta(seconds=1)).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    state = check_due(
        path=path,
        target="203.0.113.10",
        now=now,
        opener=call_api({"blocked": True}),
    )

    assert state["pending_notification"]["state"] == "down"


def test_check_is_skipped_before_due_time(tmp_path):
    path = tmp_path / "state.json"
    now = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
    original = {
        "target": "203.0.113.10",
        "blocked": False,
        "next_check_at": (now + timedelta(hours=1)).isoformat(),
    }
    path.write_text(json.dumps(original), encoding="utf-8")

    def unexpected_opener(*args, **kwargs):
        raise AssertionError("API must not be called before next_check_at")

    state = check_due(
        path=path,
        target="203.0.113.10",
        now=now,
        opener=unexpected_opener,
    )

    assert state == original


def test_api_error_preserves_last_known_status_and_retries(tmp_path):
    path = tmp_path / "state.json"
    now = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
    path.write_text(
        json.dumps(
            {
                "target": "203.0.113.10",
                "blocked": True,
                "next_check_at": (now - timedelta(seconds=1)).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    def failing_opener(*args, **kwargs):
        raise TimeoutError("API timeout")

    state = check_due(
        path=path,
        target="203.0.113.10",
        now=now,
        opener=failing_opener,
    )

    assert state["blocked"] is True
    assert state["last_error"] == "TimeoutError: API timeout"
    assert state["next_check_at"] == (now + RETRY_INTERVAL).isoformat()
    assert "pending_notification" not in state


def test_invalid_api_response_is_treated_as_error(tmp_path):
    now = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)

    state = check_due(
        path=tmp_path / "state.json",
        target="203.0.113.10",
        now=now,
        opener=call_api({"blocked": "false"}),
    )

    assert state["last_error"].startswith("ValueError:")
    assert state["next_check_at"] == (now + RETRY_INTERVAL).isoformat()
    assert "blocked" not in state


def test_changed_target_is_treated_as_new_baseline(tmp_path):
    path = tmp_path / "state.json"
    now = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
    path.write_text(
        json.dumps(
            {
                "target": "203.0.113.10",
                "blocked": False,
                "next_check_at": (now - timedelta(seconds=1)).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    state = check_due(
        path=path,
        target="203.0.113.11",
        now=now,
        opener=call_api({"blocked": True}),
    )

    assert state["target"] == "203.0.113.11"
    assert state["pending_notification"]["state"] == "down"


def test_missing_target_does_not_call_api(tmp_path):
    state = check_due(
        path=tmp_path / "state.json",
        target="",
        opener=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("API must not be called")
        ),
    )

    assert state == {}


def test_clear_pending_notification_preserves_other_state(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "target": "203.0.113.10",
                "blocked": True,
                "pending_notification": {"state": "down", "message": "alert"},
            }
        ),
        encoding="utf-8",
    )

    clear_pending_notification(path)

    state = json.loads(path.read_text(encoding="utf-8"))
    assert state == {"target": "203.0.113.10", "blocked": True}
