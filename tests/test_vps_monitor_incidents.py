import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.vps_monitor import MonitorState
from services.vps_monitor_incidents import collect_due_reminders, process_incidents
from services.vps_monitor_state import StateUpdate


def transition(previous, current, notify=True, failure=None, details=""):
    return StateUpdate(
        name="zvertbot",
        previous=previous,
        current=current,
        notify=notify,
        failure=failure,
        details=details,
    )


def test_confirmed_down_creates_active_incident(tmp_path: Path):
    path = tmp_path / "incidents.json"
    data = process_incidents(
        [transition(None, MonitorState.DOWN, details="connection timeout")],
        path,
    )
    assert "zvertbot" in data["active"]
    assert data["active"]["zvertbot"]["details"] == "connection timeout"
    assert data["history"] == []
    assert path.read_text().endswith("\n")


def test_repeated_down_does_not_duplicate_incident(tmp_path: Path):
    path = tmp_path / "incidents.json"
    process_incidents([transition(None, MonitorState.DOWN)], path)
    process_incidents([transition(MonitorState.DOWN, MonitorState.DOWN)], path)
    data = json.loads(path.read_text())
    assert len(data["active"]) == 1
    assert data["history"] == []


def test_recovery_closes_incident_with_duration(tmp_path: Path):
    path = tmp_path / "incidents.json"
    process_incidents([transition(None, MonitorState.DOWN)], path)
    data = process_incidents(
        [transition(MonitorState.DOWN, MonitorState.UP)],
        path,
    )
    assert data["active"] == {}
    assert len(data["history"]) == 1
    assert data["history"][0]["duration_seconds"] >= 0
    assert data["history"][0]["recovered_at"]


def test_unconfirmed_transition_is_ignored(tmp_path: Path):
    path = tmp_path / "incidents.json"
    process_incidents(
        [transition(MonitorState.UP, MonitorState.UP, notify=False)],
        path,
    )
    assert not path.exists()


def test_orphan_recovery_does_not_create_incident(tmp_path: Path):
    path = tmp_path / "incidents.json"
    data = process_incidents(
        [transition(MonitorState.DOWN, MonitorState.UP)],
        path,
    )
    assert data["active"] == {}
    assert data["history"] == []
    assert not path.exists()


import pytest


def test_corrupted_journal_is_not_overwritten(tmp_path):
    path = tmp_path / "incidents.json"
    original = "{broken json"
    path.write_text(original)
    with pytest.raises(RuntimeError, match="Cannot read incident journal"):
        process_incidents([transition(None, MonitorState.DOWN)], path)
    assert path.read_text() == original


def test_reminders_follow_30m_2h_6h_schedule():
    started = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    incident = {
        "service": "zvertbot",
        "started_at": started.isoformat(),
        "next_reminder_at": (started + timedelta(minutes=30)).isoformat(),
    }
    data = {"active": {"zvertbot": incident}}
    assert len(collect_due_reminders(data, started + timedelta(minutes=30))) == 1
    assert datetime.fromisoformat(incident["next_reminder_at"]) == started + timedelta(
        hours=2
    )
    assert len(collect_due_reminders(data, started + timedelta(hours=1))) == 0
    assert len(collect_due_reminders(data, started + timedelta(hours=2))) == 1
    assert datetime.fromisoformat(incident["next_reminder_at"]) == started + timedelta(
        hours=8
    )
    assert len(collect_due_reminders(data, started + timedelta(hours=8))) == 1
    assert datetime.fromisoformat(incident["next_reminder_at"]) == started + timedelta(
        hours=14
    )


def test_reminder_schedule_skips_missed_intervals_without_spam():
    started = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    incident = {
        "service": "zvertbot",
        "started_at": started.isoformat(),
        "next_reminder_at": (started + timedelta(minutes=30)).isoformat(),
    }
    data = {"active": {"zvertbot": incident}}
    assert len(collect_due_reminders(data, started + timedelta(hours=10))) == 1
    assert datetime.fromisoformat(incident["next_reminder_at"]) == started + timedelta(
        hours=14
    )
    assert (
        len(collect_due_reminders(data, started + timedelta(hours=10, minutes=1))) == 0
    )


def test_missing_service_does_not_advance_reminder_schedule():
    started = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    due_at = started + timedelta(minutes=30)
    incident = {
        "service": "zvertbot",
        "started_at": started.isoformat(),
        "next_reminder_at": due_at.isoformat(),
    }
    data = {"active": {"zvertbot": incident}}
    assert collect_due_reminders(data, due_at, available_services=set()) == []
    assert datetime.fromisoformat(incident["next_reminder_at"]) == due_at
    reminders = collect_due_reminders(data, due_at, available_services={"zvertbot"})
    assert len(reminders) == 1
    assert datetime.fromisoformat(incident["next_reminder_at"]) == started + timedelta(
        hours=2
    )


def test_confirmed_up_closes_active_incident_without_notification(tmp_path: Path):
    path = tmp_path / "incidents.json"
    process_incidents([transition(None, MonitorState.DOWN)], path)

    data = process_incidents(
        [transition(MonitorState.UP, MonitorState.UP, notify=False)],
        path,
    )

    assert data["active"] == {}
    assert len(data["history"]) == 1
    assert data["history"][0]["recovered_at"]
    assert data["history"][0]["duration_seconds"] >= 0


def test_unconfirmed_down_does_not_create_incident(tmp_path: Path):
    path = tmp_path / "incidents.json"

    data = process_incidents(
        [transition(MonitorState.UP, MonitorState.UP, notify=False)],
        path,
    )

    assert data["active"] == {}
    assert data["history"] == []
    assert not path.exists()


def test_skipped_service_removes_active_incident_without_recovery(tmp_path: Path):
    path = tmp_path / "incidents.json"
    process_incidents(
        [
            StateUpdate(
                name="xray",
                previous=None,
                current=MonitorState.DOWN,
                notify=True,
            )
        ],
        path,
    )

    data = process_incidents([], path, skipped_services={"xray"})

    assert data["active"] == {}
    assert data["history"] == []
