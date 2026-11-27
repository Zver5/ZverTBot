"""Independent Cheburcheck IP blocklist monitoring."""

import html
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_URL = "https://cheburcheck.ru/api/v1/check"
DEFAULT_STATE_FILE = Path("data/cheburcheck_state.json")
CHECK_INTERVAL = timedelta(hours=6)
RETRY_INTERVAL = timedelta(minutes=30)


def _now(value=None):
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _load(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid Cheburcheck state format")
    return data


def _save(data, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp_path.replace(path)


def _format_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _notification_message(target, result, blocked):
    if blocked:
        lines = [
            "🚨 <b>IP обнаружен в списках блокировок</b>",
            f"🌐 IP: <code>{html.escape(target)}</code>",
            "🔴 Cheburcheck: blocked = true",
        ]
    else:
        lines = [
            "🟢 <b>IP больше не обнаруживается в списках блокировок</b>",
            f"🌐 IP: <code>{html.escape(target)}</code>",
            "Cheburcheck: blocked = false",
        ]

    fields = (
        ("target_type", "Тип цели"),
        ("ips", "Обнаруженные IP"),
        ("blocked_subnets", "Заблокированные подсети"),
        ("rkn_domain", "Данные реестра РКН"),
        ("geo", "География"),
        ("cdn_providers", "CDN-провайдеры"),
    )
    for key, label in fields:
        value = result.get(key)
        if value not in (None, "", [], {}):
            lines.append(
                f"📋 {label}: <code>{html.escape(_format_value(value))}</code>"
            )

    lines.append(
        "ℹ️ Результат отражает данные источников Cheburcheck, "
        "а не гарантирует доступность или блокировку у каждого оператора."
    )
    return "\n".join(lines)


def check_due(
    path=DEFAULT_STATE_FILE,
    target=None,
    now=None,
    opener=urlopen,
):
    """Check the configured VPS IP when due; API failures are not VPS failures."""
    target = (target if target is not None else os.getenv("SERVER_IP", "")).strip()
    state = _load(path)

    if not target:
        return state

    current = _now(now)
    next_check = state.get("next_check_at")
    if next_check:
        try:
            if current < datetime.fromisoformat(next_check):
                return state
        except (TypeError, ValueError):
            pass

    previous_target = state.get("target")
    previous_blocked = state.get("blocked") if previous_target == target else None

    request = Request(
        f"{API_URL}?{urlencode({'target': target})}",
        headers={"Accept": "application/json", "User-Agent": "ZverTBot-Monitor/1.0"},
    )

    try:
        with opener(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if not isinstance(payload, dict) or not isinstance(
            payload.get("blocked"), bool
        ):
            raise ValueError("Cheburcheck returned an invalid response")

        blocked = payload["blocked"]
        state.update(
            {
                "target": target,
                "blocked": blocked,
                "last_result": payload,
                "last_checked_at": current.isoformat(),
                "next_check_at": (current + CHECK_INTERVAL).isoformat(),
                "last_error": None,
            }
        )

        changed = (previous_blocked is None and blocked) or (
            previous_blocked is not None and previous_blocked != blocked
        )
        if changed:
            from services.vps_monitor import MonitorState

            notification_state = (
                MonitorState.DOWN.value if blocked else MonitorState.UP.value
            )
            state["pending_notification"] = {
                "state": notification_state,
                "message": _notification_message(target, payload, blocked),
            }

    except Exception as exc:
        state.update(
            {
                "target": target,
                "last_attempt_at": current.isoformat(),
                "next_check_at": (current + RETRY_INTERVAL).isoformat(),
                "last_error": f"{type(exc).__name__}: {exc}"[:500],
            }
        )

    _save(state, path)
    return state


def clear_pending_notification(path=DEFAULT_STATE_FILE):
    """Clear a transition only after it has entered the durable Telegram queue."""
    state = _load(path)
    if "pending_notification" not in state:
        return
    state.pop("pending_notification", None)
    _save(state, path)
