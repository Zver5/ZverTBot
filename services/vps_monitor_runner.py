"""Independent VPS monitoring runner.

This module is intentionally independent from the Telegram bot polling process.
It performs VPS checks, persists monitor state, and sends Telegram notifications
only when a component changes state.
"""

import errno
import fcntl
import html
import os
from datetime import datetime
from time import sleep
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from services.vps_monitor import MonitorCategory, MonitorState, check_all
from services.vps_monitor_notifications import (
    DEFAULT_NOTIFICATION_STATE_FILE,
    PendingNotification,
    enqueue_pending_notifications,
    load_pending_notifications,
    save_pending_notifications,
)
from services.vps_monitor_state import StateUpdate, prepare_results, save_states
from utils.logger import logger

POLL_INTERVAL_SECONDS = 180
MONITOR_LOCK_PATH = "/run/zvertbot-vps-monitor.lock"


def acquire_monitor_lock(lock_path: str = MONITOR_LOCK_PATH):
    """Acquire the process-wide monitor lock."""
    lock_file = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        lock_file.close()
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            return None
        raise
    return lock_file


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
    "home_assistant": ("🏠", "Home Assistant"),
    "qnap": ("🗄️", "QNAP"),
}

EXTERNAL_MONITORS = frozenset({"home_assistant", "qnap"})


def _format_backup_age(details: str) -> str:
    marker = "last backup is "
    if marker not in details or not details.endswith(" seconds old"):
        return ""

    try:
        seconds = int(details[len(marker) : -len(" seconds old")])
    except ValueError:
        return ""

    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60

    if hours:
        return f"{hours} ч {minutes} мин назад"
    return f"{minutes} мин назад"


def _external_http_failure(details: str) -> tuple[str, str, str]:
    """Return a user-friendly explanation for an external HTTP failure."""
    value = details.lower()

    if (
        "connection refused" in value
        or "errno 111" in value
        or "winerror 10061" in value
    ):
        return (
            "🔴 Подключение отклонено",
            "Удалённый узел отклонил соединение.",
            "Проверьте адрес, порт и правила firewall.",
        )

    if (
        "timed out" in value
        or "timeout" in value
        or "errno 110" in value
        or "winerror 10060" in value
    ):
        return (
            "🔴 Превышено время ожидания",
            "Возможны проблемы с сетью или перегрузка узла.",
            "Проверьте сеть и доступность службы.",
        )

    if (
        "name or service not known" in value
        or "temporary failure in name resolution" in value
        or "failed to resolve" in value
        or "getaddrinfo failed" in value
        or "nodename nor servname provided" in value
    ):
        return (
            "🔴 Не удалось определить адрес сервера",
            "Не удалось определить IP-адрес узла.",
            "Проверьте имя хоста и DNS.",
        )

    if "network is unreachable" in value or "errno 101" in value:
        return (
            "🔴 Нет сетевого маршрута",
            "Нет сетевого маршрута до целевого узла.",
            "Проверьте маршрут, шлюз и VPN.",
        )

    if "no route to host" in value or "errno 113" in value:
        return (
            "🔴 Узел недоступен по сети",
            "Не удалось установить соединение с узлом.",
            "Проверьте маршрутизацию и firewall.",
        )

    if "ssl" in value or "certificate verify failed" in value:
        return (
            "🔴 Ошибка TLS-соединения",
            "Не удалось установить HTTPS-соединение.",
            "Проверьте сертификат, имя хоста и время сервера.",
        )

    if details.upper().startswith("HTTP "):
        try:
            status_code = int(details.split()[1])
        except (IndexError, ValueError):
            status_code = 0

        if status_code >= 500:
            return (
                f"🔴 Ошибка сервера HTTP {status_code}",
                "На удалённом веб-сервисе произошла ошибка.",
                "Проверьте приложение и его журнал.",
            )

        if status_code >= 400:
            return (
                f"🔴 HTTP-запрос отклонён ({status_code})",
                "Возможны ошибки URL, авторизации или настроек доступа.",
                "Проверьте URL и настройки доступа.",
            )

    return (
        "🔴 Не удалось проверить доступность сервиса",
        "Причину сетевой или HTTP-ошибки определить не удалось.",
        "Проверьте URL, порт и журнал сервиса.",
    )


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
        "%d.%m.%Y, %H:%M MSK"
    )

    lines = [
        f"{icon} <b>Сервис: {html.escape(name)}</b>",
    ]

    if update.current == MonitorState.UP:
        if update.name == "backup":
            lines.append("🟢 Резервное копирование восстановлено")
        else:
            lines.append("🟢 Работа восстановлена")

        if update.name in EXTERNAL_MONITORS and update.details:
            lines.append(f"🌐 {html.escape(update.details)}")

        lines.append(f"🕒 Время события: {timestamp}")
        return "\n".join(lines)

    details = update.details or ""
    failure = str(update.failure or "")

    if update.name == "backup":
        age = _format_backup_age(details)

        if failure == "backup_stale":
            lines.append("🔴 Нет свежей резервной копии")
            if age:
                lines.append(f"💾 последний: {age}")
            lines.append("🔧 Проверьте расписание бэкапа и хранилище.")
        elif failure == "backup_timestamp":
            lines.append("🔴 Не удалось определить время последнего бэкапа")
            lines.append("🔧 Проверьте метку времени и часы сервера.")
        else:
            lines.append("🔴 Ошибка резервного копирования")
            lines.append("🔧 Проверьте журнал бэкапа и доступность хранилища.")

    elif failure == "http_failed" and update.name in EXTERNAL_MONITORS:
        status, explanation, action = _external_http_failure(details)
        lines.extend([status, f"📋 {explanation}", f"🔧 {action}"])
        if details:
            lines.append(f"🔎 Технические данные: {html.escape(details)}")

    elif failure == "systemd_failed":
        lines.extend(
            [
                "🔴 Служба завершилась с ошибкой",
                "⚙️ systemd: failed",
                "🔧 Журнал: journalctl -u &lt;имя-службы&gt;",
            ]
        )

    elif failure == "systemd_inactive":
        lines.extend(
            [
                "🔴 Служба не активна",
                "⚙️ systemd: inactive",
            ]
        )

    elif failure == "not_installed":
        lines.extend(
            [
                "🔴 Служба не установлена или не обнаружена",
                "🔧 Проверьте установку и имя службы.",
            ]
        )

    elif failure == "http_failed":
        lines.extend(
            [
                "🔴 HTTP-проверка не пройдена",
                "🌐 systemd: active · HTTP: failed",
            ]
        )
        if details:
            lines.append(f"🔎 Технические данные: {html.escape(details)}")

    elif failure == "tcp_failed":
        lines.extend(
            [
                "🔴 TCP-порт недоступен",
                "📋 Служба может продолжать работать.",
                "🔌 systemd: active · TCP: failed",
            ]
        )

    elif failure == "udp_failed":
        lines.extend(
            [
                "🔴 UDP-проверка не пройдена",
                "🔗 systemd: active · UDP: failed",
            ]
        )

    elif failure == "client_failed":
        lines.extend(
            [
                "🔴 Внутренняя проверка не пройдена",
                f"🔍 Проверка: {html.escape(details or 'client: failed')}",
            ]
        )

    elif failure == "config_failed":
        lines.extend(
            [
                "🔴 Ошибка конфигурации",
                "🔧 Проверьте конфигурационный файл.",
            ]
        )
        if details:
            lines.append(f"🔎 Технические данные: {html.escape(details)}")

    else:
        lines.extend(
            [
                "🔴 Сервис недоступен",
                "📋 Мониторинг обнаружил проблему, но не смог точно "
                "определить её причину.",
                "🔧 Проверьте состояние службы и её журналы.",
            ]
        )
        if details:
            lines.append(f"🔎 Технические данные: {html.escape(details)}")

    lines.append(f"🕒 Время события: {timestamp}")
    return "\n".join(lines)

def _queue_notifications(
    updates: list[StateUpdate],
    categories: dict[str, MonitorCategory],
) -> None:
    """Queue transition notifications before monitor state is persisted."""
    chats = _admin_chats()
    pending: list[PendingNotification] = []

    if not chats and any(
        update.notify
        and categories.get(update.name) != MonitorCategory.DATA_COLLECTOR
        for update in updates
    ):
        raise RuntimeError("Neither ADMIN_CHATS nor ADMIN_CHAT is configured")

    for update in updates:
        if not update.notify:
            continue

        if categories.get(update.name) == MonitorCategory.DATA_COLLECTOR:
            continue

        message = _format_update(update, categories[update.name])

        for chat_id in chats:
            pending.append(
                PendingNotification(
                    chat_id=chat_id,
                    service=update.name,
                    state=update.current,
                    message=message,
                )
            )

    enqueue_pending_notifications(
        pending,
        DEFAULT_NOTIFICATION_STATE_FILE,
    )


def _deliver_pending_notifications() -> None:
    """Deliver queued notifications and retain failures for retry."""
    pending = load_pending_notifications(
        DEFAULT_NOTIFICATION_STATE_FILE,
    )

    if not pending:
        return

    remaining = list(pending)

    for item in pending:
        try:
            _telegram_send(item.chat_id, item.message)
        except Exception:
            logger.exception(
                "Telegram notification failed | service=%s | chat=%s",
                item.service,
                item.chat_id,
            )
            continue

        remaining.remove(item)
        save_pending_notifications(
            remaining,
            DEFAULT_NOTIFICATION_STATE_FILE,
        )


def notify_updates(
    updates: list[StateUpdate],
    categories: dict[str, MonitorCategory],
) -> None:
    """Queue new notifications and retry previously failed deliveries."""
    _queue_notifications(updates, categories)
    _deliver_pending_notifications()


def run_once() -> None:
    """Run one complete monitoring cycle."""
    results = check_all()

    categories = {result.name: result.category for result in results}

    updates, states = prepare_results(results)

    for update in updates:
        if update.previous is not None and update.current != update.previous:
            logger.info(
                "vps_monitor.state_changed | service=%s | %s -> %s | details=%s",
                update.name,
                update.previous.value,
                update.current.value,
                update.details or "none",
            )

    _queue_notifications(updates, categories)
    save_states(states)
    _deliver_pending_notifications()


def main() -> None:
    """Run monitoring continuously."""
    lock_file = acquire_monitor_lock()
    if lock_file is None:
        print("vps-monitor already running; exiting", flush=True)
        return

    try:
        while True:
            try:
                run_once()
            except Exception as exc:
                print(
                    f"vps-monitor cycle failed: {exc}",
                    flush=True,
                )

            sleep(POLL_INTERVAL_SECONDS)
    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


if __name__ == "__main__":
    main()
