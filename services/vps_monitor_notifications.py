"""Persistent Telegram notification queue for VPS monitoring."""

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from services.vps_monitor import MonitorState

DEFAULT_NOTIFICATION_STATE_FILE = Path("data/vps_monitor_notifications.json")


@dataclass(frozen=True)
class PendingNotification:
    chat_id: str
    service: str
    state: MonitorState | None
    message: str
    kind: str = "transition"


def load_pending_notifications(
    path: Path | None = None,
) -> list[PendingNotification]:
    """Load pending Telegram notifications from disk."""
    path = path or DEFAULT_NOTIFICATION_STATE_FILE
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(data, list):
        return []

    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        chat_id = item.get("chat_id")
        service = item.get("service")
        state = item.get("state")
        message = item.get("message")
        kind = item.get("kind", "transition")
        valid = (
            isinstance(chat_id, str)
            and isinstance(service, str)
            and isinstance(message, str)
            and (
                (kind == "transition" and state in ("up", "down"))
                or (kind == "reminder" and state is None)
            )
        )
        if valid:
            result.append(
                PendingNotification(
                    chat_id=chat_id,
                    service=service,
                    state=MonitorState(state) if state else None,
                    message=message,
                    kind=kind,
                )
            )
    return result


def save_pending_notifications(
    pending: list[PendingNotification],
    path: Path | None = None,
) -> None:
    """Atomically persist Telegram notifications."""
    path = path or DEFAULT_NOTIFICATION_STATE_FILE
    if not pending:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(item) for item in pending]
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp_path.replace(path)


def enqueue_pending_notifications(
    notifications: list[PendingNotification],
    path: Path | None = None,
) -> None:
    """Coalesce pending events to avoid stale DOWN/UP notification pairs."""
    if not notifications:
        return

    pending = load_pending_notifications(path)
    changed = False

    for item in notifications:
        matching = [
            queued
            for queued in pending
            if queued.chat_id == item.chat_id and queued.service == item.service
        ]

        if item.kind == "reminder":
            if not any(q.kind == "reminder" for q in matching):
                pending.append(item)
                changed = True
            continue

        if item.state == MonitorState.UP and any(
            queued.state == MonitorState.DOWN for queued in matching
        ):
            # DOWN was never delivered; suppress both stale DOWN and recovery.
            pending = [
                queued
                for queued in pending
                if not (
                    queued.chat_id == item.chat_id and queued.service == item.service
                )
            ]
            changed = True
            continue

        pending = [
            queued
            for queued in pending
            if not (
                queued.chat_id == item.chat_id
                and queued.service == item.service
                and (item.state == MonitorState.UP or queued.kind == "transition")
            )
        ]
        pending.append(item)
        changed = True

    if changed:
        save_pending_notifications(pending, path)
