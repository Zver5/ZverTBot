"""
services/fail2ban.py
Модуль для работы с Fail2ban через Telegram-бот.
Функции: статус jail, логи банов, разбан IP.
"""

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
    """Получает последние баны из логов fail2ban"""
    try:
        # Читаем лог fail2ban
        result = subprocess.run(
            ["grep", "Ban ", FAIL2BAN_LOG],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Пробуем journalctl
            result = subprocess.run(
                ["journalctl", "-u", "fail2ban", "-n", "50", "--no-pager"],
                capture_output=True,
                text=True,
            )
            lines = [line for line in result.stdout.split("\n") if "Ban " in line]
        else:
            lines = result.stdout.strip().split("\n")

        if not lines:
            return "📜 *Последние баны*\n\n❌ Банов не найдено"

        # Берём последние N записей
        recent = lines[-limit:]

        text = f"📜 *Последние {len(recent)} банов:*\n\n"

        for i, line in enumerate(recent, 1):
            # Парсим строку: 2026-06-30 12:45:03,991 fail2ban.actions
            # [449]: NOTICE [sshd] Ban 62.60.130.219
            try:
                parts = line.split()
                if len(parts) < 6:
                    raise ValueError(f"Log line has {len(parts)} parts, expected >= 6")
                date = parts[0]
                time = parts[1].split(",")[0]
                jail = parts[5].strip("[]")
                ip = parts[-1]

                text += f"{i}. `{ip}` | {jail} | {date} {time}\n"
            except Exception as e:
                logger.debug(
                    "fail2ban.logs.parse_failed | error=%s",
                    e,
                )
                text += f"{i}. {line[:80]}...\n"

        return text
    except Exception as e:
        logger.error(
            "fail2ban.logs.failed | error=%s",
            e,
        )
        return f"❌ Ошибка: {e}"


def unban_ip(ip_address):
    """Разбанивает IP во всех jail"""
    try:
        # Проверяем валидность IP
        if not validate_ip(ip_address):
            return False, "❌ Неверный формат IP"

        # Получаем список jail
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
            key = key.lstrip("`|- ").strip()
            if key == "Jail list" and separator:
                jail_list = [j.strip() for j in value.split(",") if j.strip()]

        unbanned_from = []

        # Пытаемся разбанить в каждом jail
        for jail in jail_list:
            result = subprocess.run(
                ["fail2ban-client", "set", jail, "unbanip", ip_address],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and ip_address in result.stdout:
                unbanned_from.append(jail)

        if unbanned_from:
            jails = ", ".join(unbanned_from)
            return True, (f"✅ IP {ip_address} разбанен в jail: {jails}")
        else:
            return False, f"⚠️ IP {ip_address} не найден в бан-листах"
    except Exception as e:
        logger.error(
            "fail2ban.unban.failed | error=%s",
            e,
        )
        return False, f"❌ Ошибка: {e}"
