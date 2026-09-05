"""
services/system.py
Модуль для системных операций через Telegram-бот.
Функции: очистка диска, speedtest, логи служб.
"""

import json
import os
import re
import shutil
import subprocess

from config.paths import LOG_DIR, XRAY_ACCESS_LOG
from utils.logger import logger
from utils.service_control import service_exists


def run_disk_cleanup():
    """Очистка диска: apt clean, journalctl vacuum, удаление старых логов"""
    try:
        BT = chr(96)
        st_before = os.statvfs("/")
        used_before = (st_before.f_blocks - st_before.f_bavail) * st_before.f_frsize

        subprocess.run(["apt-get", "clean", "-y"], check=True, capture_output=True)
        subprocess.run(
            ["journalctl", "--vacuum-size=50M"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "find",
                LOG_DIR,
                "-type",
                "f",
                "-name",
                "*.gz",
                "-mtime",
                "+7",
                "-delete",
            ],
            check=True,
            capture_output=True,
        )

        st_after = os.statvfs("/")
        used_after = (st_after.f_blocks - st_after.f_bavail) * st_after.f_frsize

        freed_mb = (used_before - used_after) / (1024 * 1024)
        return (
            "✅ Очистка завершена"
            + chr(10)
            + "📦 Освобождено: "
            + BT
            + f"{freed_mb:.1f}"
            + " MB"
            + BT
        )
    except Exception as e:
        BT = chr(96)
        return "❌ Ошибка: " + BT + str(e) + BT


def run_speedtest_and_ip():
    """Запуск speedtest (Ookla) и возврат результата"""
    try:
        BT = chr(96)
        NL = chr(10)

        # Проверяем наличие speedtest (Ookla)
        if not shutil.which("speedtest"):
            return "❌ *Speedtest:* " + BT + "speedtest не установлен" + BT

        # Запуск с JSON форматом (Ookla)
        st_res = subprocess.run(
            ["speedtest", "--accept-license", "--accept-gdpr", "--format=json"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if st_res.returncode != 0:
            return "❌ *Speedtest:* " + BT + st_res.stderr.strip()[:150] + BT

        # Парсинг JSON
        data = json.loads(st_res.stdout)

        # Извлечение данных
        ping = f"{data.get('ping', {}).get('latency', 0):.1f} ms"
        dl_mbps = (
            data.get("download", {}).get("bandwidth", 0) / 125000
        )  # bytes/s -> Mbps
        ul_mbps = data.get("upload", {}).get("bandwidth", 0) / 125000
        dl = f"{dl_mbps:.2f} Mbit/s"
        ul = f"{ul_mbps:.2f} Mbit/s"

        # Информация о сервере
        server_info = data.get("server", {})
        srv = (
            f"{server_info.get('host', 'N/A')} "
            f"({server_info.get('location', '')}, "
            f"{server_info.get('country', '')})"
        )

        return (
            "🚀 *Speedtest Result*"
            + NL
            + "📡 Сервер: "
            + BT
            + srv
            + BT
            + NL
            + "⏱️ Ping: "
            + BT
            + ping
            + BT
            + NL
            + "⬇️ Download: "
            + BT
            + dl
            + BT
            + NL
            + "⬆️ Upload: "
            + BT
            + ul
            + BT
        )
    except subprocess.TimeoutExpired:
        return "⏱️ Таймаут speedtest (>2 минут)"
    except json.JSONDecodeError:
        return "❌ Ошибка парсинга JSON от speedtest"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:150]}"


def get_service_logs(service_name):
    """Получает информацию о службе"""
    BT = chr(96)
    NL = chr(10)

    service = service_name.lower().strip()

    # AWG не пишет нормальные journal-логи.
    # Для него показываем состояние интерфейса и peer.
    if service == "awg":
        try:
            if not shutil.which("awg"):
                return "⚠️ AmneziaWG не установлен."

            # awg-quick@awg0 — это экземпляр шаблонного
            # systemd-юнита awg-quick@.service.
            # list-unit-files для конкретного экземпляра может
            # вернуть код 1, даже когда сам сервис существует.
            if not service_exists("awg-quick@.service"):
                return "⚠️ AmneziaWG не установлен."

            result = subprocess.run(
                ["awg", "show", "awg0"], capture_output=True, text=True, timeout=10
            )

            data = result.stdout.strip()

            if not data:
                return "📭 AWG awg0 не отвечает."

            data = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])").sub("", data)

            return (
                "🛡 **AWG статус awg0**"
                + NL
                + BT
                + BT
                + BT
                + "text"
                + NL
                + data[:3900]
                + NL
                + BT
                + BT
                + BT
            )

        except Exception as e:
            return f"❌ Ошибка AWG: {str(e)[:150]}"

    services = {"xray": "xray", "bot": "zvertbot"}

    unit = services.get(service)

    if not unit:
        return (
            "❓ Доступно: "
            + BT
            + "xray"
            + BT
            + ", "
            + BT
            + "awg"
            + BT
            + ", "
            + BT
            + "bot"
            + BT
        )

    try:
        if service == "xray":
            logs = ""

            if XRAY_ACCESS_LOG.exists():
                logs = XRAY_ACCESS_LOG.read_text(
                    encoding="utf-8",
                    errors="replace",
                ).strip()

                if logs:
                    logs = logs.splitlines()[-30:]
                    logs = NL.join(logs)

            if not logs:
                result = subprocess.run(
                    ["journalctl", "-u", unit, "-n", "30", "--no-pager", "-q"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                logs = result.stdout.strip()

        else:
            result = subprocess.run(
                ["journalctl", "-u", unit, "-n", "30", "--no-pager", "-q"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            logs = result.stdout.strip()

        if not logs:
            return "📭 Логи " + unit + " пусты."

        logs = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])").sub("", logs)

        return (
            "📜 **Логи: "
            + unit
            + "**"
            + NL
            + BT
            + BT
            + BT
            + "text"
            + NL
            + logs[:3900]
            + NL
            + BT
            + BT
            + BT
        )

    except Exception as e:
        logger.error("system.logs.read_failed | unit=%s | error=%s", unit, e)
        return "❌ Ошибка чтения"
