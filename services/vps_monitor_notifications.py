"""Persistent Telegram notification queue for VPS monitoring."""

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from services.vps_monitor import MonitorState

DEFAULT_NOTIFICATION_STATE_FILE = Path(
    "data/vps_monitor_notifications.json"
)


@dataclass(frozen=True)
class PendingNotification:
    chat_id: str
    service: str
    state: MonitorState
    message: str


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

    result: list[PendingNotification] = []

    for item in data:
        if not isinstance(item, dict):
            continue

        chat_id = item.get("chat_id")
        service = item.get("service")
        state = item.get("state")
        message = item.get("message")

        if (
            not isinstance(chat_id, str)
            or not isinstance(service, str)
            or state not in ("up", "down")
            or not isinstance(message, str)
        ):
            continue

        result.append(
            PendingNotification(
                chat_id=chat_id,
                service=service,
                state=MonitorState(state),
                message=message,
            )
        )

    return result


def save_pending_notifications(
    pending: list[PendingNotification],
    path: Path | None = None,
) -> None:
    """Atomically persist pending Telegram notifications."""
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
    """Add notifications to the persistent queue without duplicates."""
    if not notifications:
        return

    pending = load_pending_notifications(path)

    existing = {
        (item.chat_id, item.service, item.state)
        for item in pending
    }

    changed = False

    for item in notifications:
        key = (item.chat_id, item.service, item.state)

        if key in existing:
            continue

        pending.append(item)
        existing.add(key)
        changed = True

    if changed:
        save_pending_notifications(pending, path)
