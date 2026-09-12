"""Independent VPS monitoring runner.

This module is intentionally independent from the Telegram bot polling process.
It performs VPS checks, persists monitor state, and sends Telegram notifications
only when a component changes state.
"""

import html
import os
from datetime import datetime
from time import sleep
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from services.vps_monitor import MonitorCategory, MonitorState, check_all
from services.vps_monitor_state import StateUpdate, prepare_results, save_states
from utils.logger import logger

POLL_INTERVAL_SECONDS = 60
TELEGRAM_API = "https://api.telegram.org"


def _admin_chats() -> list[str]:
    """Return configured Telegram administrator chat IDs."""
    value = os.getenv("ADMIN_CHATS") or os.getenv("ADMIN_CHAT") or ""
    return [item.strip() for item in value.split(",") if item.strip()]


def _telegram_send(chat_id: str, text: str) -> None:
    """Send one Telegram message without using the bot polling process."""
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not configured")

    data = urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode()

    request = Request(
        f"{TELEGRAM_API}/bot{token}/sendMessage",
        data=data,
        method="POST",
    )

    with urlopen(request, timeout=10):
        pass


SERVICE_DISPLAY = {
    "zvertbot": ("🤖", "ZverTBot"),
    "stats-http": ("📊", "Stats HTTP HASS"),
    "backup": ("💾", "Backup"),
    "xray": ("🚀", "Xray"),
    "awg": ("🛡️", "AWG"),
    "ssh": ("🔑", "SSH"),
    "fail2ban": ("🔐", "Fail2Ban"),
}


def _format_backup_age(details: str) -> str:
    marker = "last backup is "
    if marker not in details or not details.endswith(" seconds old"):
        return ""

    try:
        seconds = int(details[len(marker):-len(" seconds old")])
    except ValueError:
        return ""

    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60

    if hours:
        return f"{hours} ч {minutes} мин назад"
    return f"{minutes} мин назад"


def _format_update(
    update: StateUpdate,
    category: MonitorCategory,
) -> str:
    del category

    icon, name = SERVICE_DISPLAY.get(
        update.name,
        ("⚙️", update.name),
    )
    timestamp = datetime.now(ZoneInfo("Europe/Moscow")).strftime(
        "%Y-%m-%d %H:%M MSK"
    )

    if update.current == MonitorState.UP:
        if update.name == "backup":
            status = "🟢 Бэкап снова выполняется успешно"
        else:
            status = "🟢 Работа восстановлена"

        return (
            f"{icon} <b>Сервис: {name}</b>\n"
            f"{status}\n"
            f"⏱️ {timestamp}"
        )

    details = update.details

    if update.name == "backup":
        age = _format_backup_age(update.details)
        if update.failure == "backup_stale" and age:
            status = "🔴 Бэкап просрочен"
            technical = f"последний: {age}"
            technical_icon = "💾"
        else:
            status = "🔴 Последний бэкап завершился с ошибкой"
            technical = ""
            technical_icon = ""

    else:
        if update.failure == "systemd_failed":
            status = "🔴 Сервис завершился с ошибкой"
            technical = "systemd: failed"
            technical_icon = "💥"
        elif update.failure == "systemd_inactive":
            status = "🔴 Сервис остановлен"
            technical = "systemd: inactive"
            technical_icon = "⚙️"
        elif update.failure == "http_failed":
            status = "🔴 Сервис запущен, но не отвечает"
            technical = "systemd: active · HTTP: failed"
            technical_icon = "🌐"
        elif update.failure == "tcp_failed":
            status = "🔴 Сервис запущен, но порт недоступен"
            technical = "systemd: active · TCP: failed"
            technical_icon = "🔌"
        elif update.failure == "udp_failed":
            status = "🔴 Сервис запущен, но порт недоступен"
            technical = "systemd: active · UDP: failed"
            technical_icon = "🔗"
        elif update.failure == "client_failed":
            status = "🔴 Сервис запущен, но проверка не прошла"
            technical = "systemd: active · client: failed"
            technical_icon = "🔍"
        else:
            status = "🔴 Сервис недоступен"
            technical = details or "причина не определена"
            technical_icon = "❓"

    lines = [
        f"{icon} <b>Сервис: {name}</b>",
        status,
    ]

    if technical:
        lines.append(f"{technical_icon} {html.escape(technical)}")

    lines.append(f"⏱️ {timestamp}")

    return "\n".join(lines)


def notify_updates(
    updates: list[StateUpdate],
    categories: dict[str, MonitorCategory],
) -> None:
    """Send notifications for actual state transitions."""
    chats = _admin_chats()

    if not chats:
        raise RuntimeError(
            "Neither ADMIN_CHATS nor ADMIN_CHAT is configured"
        )

    for update in updates:
        if not update.notify:
            continue

        category = categories[update.name]

        # Data collectors are intentionally not alarm sources.
        if category == MonitorCategory.DATA_COLLECTOR:
            continue

        message = _format_update(update, category)

        for chat_id in chats:
            _telegram_send(chat_id, message)


def run_once() -> None:
    """Run one complete monitoring cycle."""
    results = check_all()

    categories = {
        result.name: result.category
        for result in results
    }

    updates, states = prepare_results(results)

    for update in updates:
        if (
            update.previous is not None
            and update.current != update.previous
        ):
            logger.info(
                "vps_monitor.state_changed | service=%s | %s -> %s | details=%s",
                update.name,
                update.previous.value,
                update.current.value,
                update.details or "none",
            )

    notify_updates(updates, categories)
    save_states(states)


def main() -> None:
    """Run monitoring continuously."""
    while True:
        try:
            run_once()
        except Exception as exc:
            print(
                f"vps-monitor cycle failed: {exc}",
                flush=True,
            )

        sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
