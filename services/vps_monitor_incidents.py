"""Persistent incident history for VPS monitoring."""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.vps_monitor import MonitorState
from services.vps_monitor_state import StateUpdate

DEFAULT_INCIDENT_FILE = Path("data/vps_monitor_incidents.json")
MAX_CLOSED_INCIDENTS = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load(path: Path) -> dict:
    empty = {"version": 1, "active": {}, "history": []}
    if not path.exists():
        return empty

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read incident journal {path}") from exc

    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid incident journal structure: {path}")

    active = data.get("active", {})
    history = data.get("history", [])
    if not isinstance(active, dict) or not isinstance(history, list):
        raise RuntimeError(f"Invalid incident journal sections: {path}")

    return {"version": 1, "active": active, "history": history}


def _save(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def collect_due_reminders(
    data: dict,
    now: datetime | None = None,
    available_services: set[str] | None = None,
) -> list[dict]:
    """Collect due reminders and advance schedules without saving the journal."""
    now = now or _now()
    due = []

    for service, incident in data.get("active", {}).items():
        if available_services is not None and service not in available_services:
            continue
        try:
            started = datetime.fromisoformat(incident["started_at"])
            next_at = datetime.fromisoformat(
                incident.get("next_reminder_at")
                or (started + timedelta(minutes=30)).isoformat()
            )
        except (KeyError, TypeError, ValueError):
            continue

        if next_at > now:
            continue

        due.append({**incident, "service": service})
        if next_at <= started + timedelta(minutes=30):
            next_at = started + timedelta(hours=2)
            if next_at <= now:
                next_at = started + timedelta(hours=8)
        elif next_at <= started + timedelta(hours=2):
            next_at = started + timedelta(hours=8)
        else:
            next_at += timedelta(hours=6)

        while next_at <= now:
            next_at += timedelta(hours=6)
        incident["next_reminder_at"] = next_at.isoformat()

    return due


def save_incident_data(data: dict, path: Path = DEFAULT_INCIDENT_FILE) -> None:
    """Persist a previously loaded and updated incident journal."""
    _save(data, path)


def process_incidents(
    updates: list[StateUpdate],
    path: Path = DEFAULT_INCIDENT_FILE,
) -> dict:
    """Record confirmed state transitions without duplicating incidents."""
    data = _load(path)
    changed = False

    for update in updates:
        active = data["active"].get(update.name)

        # A confirmed UP state closes an active incident even when no
        # notification transition is needed (for example, after a restart).
        if update.current == MonitorState.UP and active is not None:
            now = _now()
            try:
                started = datetime.fromisoformat(active["started_at"])
                duration = max(0, int((now - started).total_seconds()))
            except (KeyError, TypeError, ValueError):
                duration = 0

            closed = {
                **active,
                "recovered_at": now.isoformat(),
                "duration_seconds": duration,
                "recovery_details": update.details or "",
            }
            data["history"].append(closed)
            data["history"] = data["history"][-MAX_CLOSED_INCIDENTS:]
            del data["active"][update.name]
            changed = True
            continue

        if not update.notify:
            continue

        now = _now()
        active = data["active"].get(update.name)

        if update.current == MonitorState.DOWN:
            if active is not None:
                continue
            data["active"][update.name] = {
                "service": update.name,
                "started_at": now.isoformat(),
                "next_reminder_at": (now + timedelta(minutes=30)).isoformat(),
                "failure": getattr(update.failure, "value", str(update.failure))
                if update.failure
                else None,
                "details": update.details or "",
            }
            changed = True
            continue

    if changed:
        _save(data, path)

    return data
