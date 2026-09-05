#!/usr/bin/env python3

import json
import queue
import re
import socketserver
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from config.paths import KUMA_STATE_FILE
from config.secrets import (
    ADMIN_CHAT,
    BOT_TOKEN,
    KUMA_HEALTHCHECK_URL,
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")


if not ADMIN_CHAT:
    raise RuntimeError("ADMIN_CHAT missing")


PORT = 8082

STATE_FILE = KUMA_STATE_FILE

# Последний известный IP:порт каждого Kuma-монитора.
LAST_MONITOR_ADDRESSES = {}


# ============================================================
# TRANSLATIONS
# ============================================================

MSG_TRANSLATIONS = [
    (r"Connection failed", "Не удалось подключиться"),
    (r"ECONNREFUSED", "Соединение отклонено"),
    (r"ETIMEDOUT", "Нет ответа от сервиса"),
    (r"systemd inactive", "Служба остановлена"),
    (r"port closed", "Порт закрыт"),
    (r"404", "Страница не найдена"),
    (r"500", "Ошибка сервера"),
    (r"503", "Сервис временно недоступен"),
]


def translate_msg(msg, fallback_address=""):
    if not msg:
        return "", fallback_address

    msg = str(msg).strip()

    # Сохраняем IP:порт из самого сообщения Kuma,
    # если он там есть.
    address_match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{1,5}\b", msg)

    address = address_match.group(0) if address_match else fallback_address

    # PING с потерей пакетов.
    if re.search(
        r"PING .*packet loss|\d+ packets transmitted,\s*0 received",
        msg,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        return "Нет ответа от сервиса", address

    # Убираем технический префикс Kuma.
    msg = re.sub(r"^connect\s+", "", msg, flags=re.IGNORECASE)

    # Переводим известные технические причины.
    for a, b in MSG_TRANSLATIONS:
        msg = re.sub(a, b, msg, flags=re.IGNORECASE)

    # Убираем технические URL-префиксы.
    msg = re.sub(r"https?:///?", "", msg, flags=re.IGNORECASE)

    # Убираем IP:порт из причины,
    # потому что он выводится отдельной строкой.
    msg = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{1,5}\b", "", msg)

    # Убираем лишние пробелы.
    msg = re.sub(r"\s+", " ", msg).strip()

    return msg, address


def get_monitor_address(monitor):
    """Возвращает фактический адрес Kuma-монитора."""

    if not monitor:
        return ""

    mtype = str(monitor.get("type") or "").strip().lower()

    hostname = str(monitor.get("hostname") or "").strip()

    port = str(monitor.get("port") or "").strip()

    url = str(monitor.get("url") or "").strip()

    # HTTP и JSON-query:
    # адрес всегда берём из URL, потому что именно URL
    # является фактической целью проверки Kuma.
    if mtype in ("http", "json-query") and url:
        match = re.search(
            r"https?://([^/:]+)(?::(\d+))?",
            url,
            flags=re.IGNORECASE,
        )

        if match:
            host = match.group(1)
            url_port = match.group(2)

            if url_port:
                return f"{host}:{url_port}"

            return host

    # Port и ping:
    # Kuma использует hostname + port.
    if hostname and port:
        return f"{hostname}:{port}"

    # Последний fallback.
    if hostname:
        return hostname

    return ""


def normalize_monitor_name(name):
    """Возвращает красивое имя Kuma-монитора с индивидуальным значком."""

    name = str(name or "").strip()

    # Убираем старые значки/префиксы, если они уже были добавлены.
    name = re.sub(r"^📡\s*", "", name)
    name = re.sub(r"^🚀\s*", "", name)

    icons = {
        "Xray VLESS 443": "🚀 Xray",
        "Xray VLESS 2096": "🚀 Xray",
        "Hass": "🏠 Hass",
        "AmneziaWG": "🛡️ AmneziaWG",
        "VPS SSH": "🔑 VPS SSH",
        "QNAP Home": "🗄️ QNAP Home",
        "VPS Healthcheck Endpoint": "❤️ VPS Healthcheck Endpoint",
        "VPS Services Status": "⚙️ VPS Services Status",
    }

    return icons.get(name, f"🔹 {name}")


def get_health():

    try:
        r = requests.get(KUMA_HEALTHCHECK_URL, timeout=5)

        return r.json()

    except Exception as e:
        return {"status": "unknown", "error": str(e)}


def health_message(data):

    text = []

    text.append("🏥 VPS Healthcheck")

    status = data.get("status", "unknown")

    status_text = "✅ Работает" if status == "healthy" else "❌ Ошибка"

    text.append(status_text)

    system = data.get("system", {})

    if system:
        text.append("")

        text.append("📊 Система:")

        if "load" in system:
            text.append(f"⚙️ Load: {system.get('load')}")

        if "ram" in system:
            text.append(f"🧠 RAM: {system.get('ram')}%")

        if "disk" in system:
            text.append(f"💾 Disk: {system.get('disk')}%")

    hostname = system.get("hostname") or data.get("hostname") or "ZverTBot VPS"

    text.append("")

    text.append(f"🖥 Сервер: `{hostname}`")

    checks = data.get("checks", {})

    if checks:
        text.append("")
        text.append("🔧 Сервисы:")

        for name, c in checks.items():
            emoji = "✅" if c.get("status") == "ok" else "❌"

            service_icons = {
                "xray": "🚀",
                "amnezia_wg": "🔐",
                "stats_http": "📡",
                "zvertbot": "🤖",
                "ssh": "🔑",
                "fail2ban": "🛡️",
                "ha_tunnel": "🏠",
            }

            icon = service_icons.get(name, "⚙️")

            text.append(f"{emoji} {icon} {name}")

    failed = data.get("failed", [])

    if failed:
        text.append("")
        text.append("❌ Проблемы:")

        for item in failed:
            reason = item.get("reason", "")

            text.append(f"- {item.get('service')}: {reason}")

    text.append("")

    text.append("⏱️ " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    return "\n".join(text)


# ============================================================
# TELEGRAM
# ============================================================


# ============================================================
# ПОСЛЕДОВАТЕЛЬНАЯ ОЧЕРЕДЬ TELEGRAM
# ============================================================

TELEGRAM_QUEUE = queue.Queue()


def _telegram_worker():
    """Последовательно отправляет сообщения в Telegram."""

    while True:
        text = TELEGRAM_QUEUE.get()

        try:
            try:
                r = requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": ADMIN_CHAT,
                        "text": text,
                    },
                    timeout=5,
                )

                if r.ok:
                    print("[TG OK]", r.text[:200], flush=True)
                else:
                    print("[TG FAIL]", r.status_code, r.text[:300], flush=True)

            except Exception as e:
                print("[TG ERROR]", e, flush=True)

        finally:
            TELEGRAM_QUEUE.task_done()


def send_telegram(text):
    """Ставит сообщение в очередь Telegram."""

    if not text:
        return

    TELEGRAM_QUEUE.put(text)


# Один worker = строгая последовательность отправки.
threading.Thread(target=_telegram_worker, name="telegram-worker", daemon=True).start()


# ============================================================
# KUMA WEBHOOK
# ============================================================


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):

        try:
            length = int(self.headers.get("Content-Length", 0))

            raw = self.rfile.read(length)

            data = json.loads(raw.decode())

            monitor = data.get("monitor", {})

            heartbeat = data.get("heartbeat", {})

            if not monitor and not heartbeat:
                self.send_response(200)
                self.end_headers()
                return

            status = heartbeat.get("status", -1)

            raw_name = monitor.get("name", "Unknown")

            name = normalize_monitor_name(raw_name)

            # Получаем адрес непосредственно из конфигурации Kuma.
            # Если Kuma прислал адрес в heartbeat — он имеет приоритет.
            monitor_address = get_monitor_address(monitor)

            msg, address = translate_msg(heartbeat.get("msg", ""), monitor_address)

            # Сохраняем последний известный адрес.
            # Он используется как запасной вариант при UP.
            global LAST_MONITOR_ADDRESSES

            if address:
                LAST_MONITOR_ADDRESSES[raw_name] = address

            elif raw_name in LAST_MONITOR_ADDRESSES:
                address = LAST_MONITOR_ADDRESSES[raw_name]

            if status == 0:
                if KUMA_HEALTHCHECK_URL:
                    health = get_health()

                    if health.get("status") == "degraded":
                        text = "🔴 Kuma: VPS Healthcheck\n\n"
                        text += health_message(health)
                    else:
                        text = (
                            "🔴 Kuma: СЕРВИС НЕДОСТУПЕН\n\n"
                            f"{name}\n"
                            f"💬 Статус: {msg or 'Нет ответа'}"
                        )

                        if address:
                            text += f"\n🌐 Адрес: {address}"
                else:
                    text = (
                        "🔴 Kuma: СЕРВИС НЕДОСТУПЕН\n\n"
                        f"{name}\n"
                        f"💬 Статус: {msg or 'Нет ответа'}"
                    )

                    if address:
                        text += f"\n🌐 Адрес: {address}"

                send_telegram(text)

            elif status == 1:
                text = f"🟢 Kuma: СЕРВИС ВОССТАНОВЛЕН\n\n{name}\n💬 Статус: Доступен"

                if address:
                    text += f"\n🌐 Адрес: {address}"

                send_telegram(text)

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

        except Exception as e:
            print("[ERROR]", e, flush=True)

            self.send_response(500)
            self.end_headers()

    def log_message(self, *args):
        pass


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    print(f"[START] Smart Kuma webhook :{PORT}", flush=True)

    ThreadedHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
