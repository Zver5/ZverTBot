"""
services/fail2ban.py
Модуль для работы с Fail2ban через Telegram-бот.
Функции: статус jail, логи банов, разбан IP.
"""

import ipaddress
import re
import subprocess

from config.paths import FAIL2BAN_LOG
from utils.logger import logger
from utils.service_control import service_is_active
from utils.validators import validate_ip


def get_fail2ban_status():
    """Получает статус fail2ban и всех jail"""
    try:
        # Проверяем статус службы
        if not service_is_active("fail2ban"):
            return "❌ Fail2ban не активен"

        # Получаем список jail
        result = subprocess.run(
            ["fail2ban-client", "status"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return f"❌ Ошибка: {result.stderr}"

        num_jails = 0
        jail_list = []

        for line in result.stdout.splitlines():
            key, separator, value = line.partition(":")
            if not separator:
                continue

            key = key.lstrip("`|- ").strip()
            value = value.strip()

            if key == "Number of jail":
                try:
                    num_jails = int(value)
                except ValueError:
                    logger.warning(
                        "fail2ban.status.invalid_jail_count | value=%s",
                        value,
                    )

            elif key == "Jail list":
                jail_list = [j.strip() for j in value.split(",") if j.strip()]

        text = "🔒 *Fail2ban Status*\n\n"
        text += "✅ Служба: активна\n"
        text += f"📊 Активных jail: {num_jails}\n\n"

        # Для каждого jail получаем детали
        for jail in jail_list:
            result = subprocess.run(
                ["fail2ban-client", "status", jail],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                current_banned = 0
                total_banned = 0

                for jl in result.stdout.splitlines():
                    key, separator, value = jl.partition(":")
                    if not separator:
                        continue

                    key = key.lstrip("`|- ").strip()
                    value = value.strip()

                    if key == "Currently banned":
                        try:
                            current_banned = int(value)
                        except ValueError:
                            logger.warning(
                                "fail2ban.status.invalid_banned_count | "
                                "field=currently_banned | value=%s",
                                value,
                            )

                    elif key == "Total banned":
                        try:
                            total_banned = int(value)
                        except ValueError:
                            logger.warning(
                                "fail2ban.status.invalid_banned_count | "
                                "field=total_banned | value=%s",
                                value,
                            )

                text += f"🛡 *{jail}*\n"
                text += f"├─ Забанено сейчас: {current_banned}\n"
                text += f"└─ Всего банов: {total_banned}\n\n"

        return text
    except Exception as e:
        logger.error(
            "fail2ban.status.failed | error=%s",
            e,
        )
        return f"❌ Ошибка: {e}"


def get_fail2ban_logs(limit=10):
    """Получает последние реальные события Ban из логов Fail2ban."""
    try:
        result = subprocess.run(
            ["grep", "Ban ", FAIL2BAN_LOG],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            result = subprocess.run(
                ["journalctl", "-u", "fail2ban", "-n", "100", "--no-pager"],
                capture_output=True,
                text=True,
            )
            lines = result.stdout.splitlines()
        else:
            lines = result.stdout.splitlines()

        entries = []

        for line in lines:
            match = re.search(
                r"(?P<date>\d{4}-\d{2}-\d{2})"
                r"[ T]"
                r"(?P<time>\d{2}:\d{2}:\d{2})"
                r"(?:,\d+)?"
                r".*?\[(?P<jail>[^\]]+)\]"
                r"\s+Ban\s+"
                r"(?P<ip>[^\s]+)",
                line,
            )

            if not match:
                continue

            ip = match.group("ip").strip("[](),")

            try:
                ipaddress.ip_address(ip)
            except ValueError:
                logger.debug(
                    "fail2ban.logs.invalid_ip | ip=%s | line=%s",
                    ip,
                    line[:160],
                )
                continue

            entries.append(
                (
                    match.group("date"),
                    match.group("time"),
                    match.group("jail"),
                    ip,
                )
            )

        if not entries:
            return "📜 *Последние баны*\n\n❌ Банов не найдено"

        recent = entries[-limit:]

        text = f"📜 *Последние {len(recent)} банов:*\n\n"

        for i, (date, time, jail, ip) in enumerate(recent, 1):
            text += f"{i}. `{ip}` | {jail} | {date} {time}\n"

        return text
    except Exception as e:
        logger.error(
            "fail2ban.logs.failed | error=%s",
            e,
        )
        return f"❌ Ошибка: {e}"


def unban_ip(ip_address):
    """Разбанивает IP во всех jail."""
    try:
        if not validate_ip(ip_address):
            return False, "❌ Неверный формат IP"

        result = subprocess.run(
            ["fail2ban-client", "status"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False, f"❌ Ошибка: {result.stderr}"

        jail_list = []
        for line in result.stdout.splitlines():
            key, separator, value = line.partition(":")
            if not separator:
                continue

            key = key.lstrip("`|- ").strip()
            if key == "Jail list":
                jail_list = [j.strip() for j in value.split(",") if j.strip()]

        banned_in = []

        for jail in jail_list:
            result = subprocess.run(
                ["fail2ban-client", "get", jail, "banip"],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.warning(
                    "fail2ban.unban.ban_list_failed | jail=%s | error=%s",
                    jail,
                    result.stderr.strip(),
                )
                continue

            banned_ips = set(result.stdout.split())

            if ip_address not in banned_ips:
                continue

            result = subprocess.run(
                ["fail2ban-client", "set", jail, "unbanip", ip_address],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return False, (
                    f"❌ Ошибка разбана IP {ip_address} "
                    f"в jail {jail}: {result.stderr.strip()}"
                )

            banned_in.append(jail)

        if banned_in:
            jails = ", ".join(banned_in)
            return True, f"✅ IP {ip_address} разбанен в jail: {jails}"

        return True, f"ℹ️ IP {ip_address} уже не заблокирован"

    except Exception as e:
        logger.error(
            "fail2ban.unban.failed | error=%s",
            e,
        )
        return False, f"❌ Ошибка: {e}"
