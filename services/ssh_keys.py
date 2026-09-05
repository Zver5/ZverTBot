"""
services/ssh_keys.py
Модуль для управления SSH-ключами через Telegram-бот.
Функции: список ключей, удаление, история подключений, экспорт.
"""

import os
import re
import shutil
import subprocess
from datetime import datetime

from config.paths import SSH_AUTHORIZED_KEYS
from config.secrets import HA_TUNNEL_IP
from utils.atomic import atomic_write
from utils.client_operation_lock import client_operation_lock
from utils.logger import logger
from utils.service_control import service_is_active

# Маппинг SHA256 отпечатков -> имена ключей (из SERVER-PASSPORT.md)
SSH_KEY_MAP = {
    "SHA256:UxaFCxSulXUszioipn6BmWgxVsclklATdtJET5Xm7jA": {
        "name": "HA_Tunnel",
        "desc": "HA -> VPS туннель (SOCKS5:1080)",
        "emoji": "🏭",
    },
    "SHA256:CfVRabOgO6p0n7pnykUnQhnfHlL+YRSS0G1tHKmg4ro": {
        "name": "PC_Work",
        "desc": "Work ПК (Win11, PowerShell + PuTTY)",
        "emoji": "💼",
    },
    "SHA256:9Zh34ityt6hkjS1APYVs9uFu39xamw40AuLLX2JPDJE": {
        "name": "PC_Home",
        "desc": "Home ПК / ноутбук",
        "emoji": "🏠",
    },
    "SHA256:W1zHG+RTUV0mTBB58UH7MyD0JaoOTusC7vZdWEkRT24": {
        "name": "iphone-termius",
        "desc": "iPhone, приложение Termius",
        "emoji": "📱",
    },
}

# Маппинг IP -> имя устройства (из истории подключений)
SSH_IP_MAP = {
    "203.0.113.11": "PC_Work",
    HA_TUNNEL_IP: "PC_Home / HA",
}


def get_ssh_keys_list():
    """Получает список SSH-ключей с отпечатками и описаниями"""
    try:
        auth_keys = SSH_AUTHORIZED_KEYS
        if not os.path.exists(auth_keys):
            return "❌ Файл authorized_keys не найден"

        # Пустой файл = ключей нет
        if os.path.getsize(auth_keys) == 0:
            return "🔐 *SSH-ключи доступа*\
\
🔑 SSH-ключи не найдены."

        # Получаем отпечатки всех ключей
        result = subprocess.run(
            ["ssh-keygen", "-lf", auth_keys], capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return f"❌ Ошибка: {result.stderr}"

        full_output = result.stdout

        # Ищем SHA256 отпечатки (устойчиво к переносам строк)
        # Паттерн: SHA256:xxx (43 символа base64) + пробел + комментарий
        matches = re.findall(r"(SHA256:[A-Za-z0-9+/=]{43})\s+(\S+)", full_output)
        if not matches:
            return "🔐 *SSH-ключи доступа*\n\n🔑 SSH-ключи не найдены."

        # Формируем текст
        text = f"🔐 *SSH-ключи ({len(matches)})*\n\n"
        for fingerprint, comment in matches:
            # Определяем тип ключа из контекста вокруг fingerprint
            fp_pos = full_output.find(fingerprint)
            context = (
                full_output[max(0, fp_pos - 200) : fp_pos + 200] if fp_pos >= 0 else ""
            )
            if "ED25519" in context or "ssh-ed25519" in context.lower():
                key_type = "ED25519"
            elif "RSA" in context or "ssh-rsa" in context.lower():
                key_type = "RSA"
            else:
                key_type = "ED25519"

            # Ищем описание в маппинге
            key_info = SSH_KEY_MAP.get(
                fingerprint,
                {"name": comment, "desc": "Неизвестный ключ", "emoji": "🔑"},
            )
            text += (
                f"{key_info['emoji']} *"
                f"{key_info['name'].replace('_', ' ')}* "
                f"({key_info['desc']})\n"
            )
            text += f"🔧 {key_type}\n\n"
        return text
    except Exception as e:
        logger.error(
            "ssh.keys.list.failed | error=%s",
            e,
        )
        return f"❌ Ошибка: {e}"


@client_operation_lock
def delete_ssh_key(comment):
    """Удаляет SSH-ключ по комментарию с бэкапом"""
    try:
        auth_keys = SSH_AUTHORIZED_KEYS
        if not os.path.exists(auth_keys):
            return False, "❌ Файл authorized_keys не найден"

        # Создаём бэкап перед удалением
        backup_path = f"{auth_keys}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(auth_keys, backup_path)

        # Считаем ключи до удаления
        with open(auth_keys) as f:
            lines_before = f.readlines()
        count_before = len(
            [line for line in lines_before if line.strip() and not line.startswith("#")]
        )

        # Удаляем строку с указанным комментарием
        result = subprocess.run(
            ["grep", "-v", f" {comment}$", auth_keys],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode not in (0, 1):
            return False, f"❌ Ошибка поиска ключа: {result.stderr}"

        if result.returncode == 1 and result.stdout.strip():
            return False, f"❌ Ошибка удаления ключа '{comment}'"

        # Записываем обновлённый файл
        # Записываем обновлённый файл атомарно
        atomic_write(auth_keys, result.stdout)

        # Считаем ключи после удаления
        with open(auth_keys) as f:
            lines_after = f.readlines()
        count_after = len(
            [line for line in lines_after if line.strip() and not line.startswith("#")]
        )

        if count_before == count_after:
            shutil.copy2(backup_path, auth_keys)
            return False, f"⚠️ Ключ '{comment}' не найден в authorized_keys"

        return (
            True,
            f"✅ Ключ `{comment}` удалён\n"
            f"📦 Бэкап: `{backup_path}`\n"
            f"📊 Ключей было: {count_before}, стало: {count_after}",
        )
    except Exception as e:
        return False, f"❌ Ошибка: {e}"


def get_ssh_history(limit=10):
    """Показывает последние SSH-входы в компактном виде."""
    try:
        result = subprocess.run(
            ["last", "-ai"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            logger.error(
                "ssh.history.command_failed | error=%s",
                result.stderr.strip(),
            )
            return "📜 *SSH-входы*\n❌ Не удалось получить историю SSH"

        entries = []
        seen = set()

        for line in result.stdout.splitlines():
            parts = line.split()

            if len(parts) < 7:
                continue

            if parts[0] in ("wtmp", "reboot", "shutdown"):
                continue

            user = parts[0]
            terminal = parts[1]

            if not (terminal.startswith("pts/") or terminal.startswith("tty")):
                continue

            month = parts[3]
            day = parts[4]
            time_str = parts[5]

            ip = parts[-1]

            if ip in ("0.0.0.0", "::1", "localhost", "-"):
                continue

            date_str = f"{day}.{month}"

            dedup_key = (user, terminal, date_str, time_str, ip)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            entries.append(
                {
                    "date": date_str,
                    "time": time_str,
                    "ip": ip,
                    "name": user,
                    "emoji": "🔐",
                }
            )

        if not entries:
            return "📜 *SSH-входы*\n❌ Успешных подключений не найдено"

        # `last` выводит записи от новых к старым.
        entries = entries[:limit]

        logger.info(
            "ssh.history.formatted | entries=%s",
            len(entries),
        )

        text = f"📜 *SSH-входы* · {len(entries)}\n\n"

        for entry in entries:
            text += (
                f"{entry['emoji']} *{entry['name']}* · "
                f"{entry['date']} {entry['time']}\n"
                f"🌐 `{entry['ip']}`\n\n"
            )

        return text.rstrip()

    except Exception as e:
        logger.error(
            "ssh.history.failed | error=%s",
            e,
        )
        return f"❌ Ошибка: {e}"


def get_ssh_status():
    """
    Безопасная диагностика SSH.
    Только чтение.
    """

    NL = chr(10)
    BT = chr(96)

    try:
        # Проверяем правильное имя службы
        service_status = "unknown"

        for unit in ("ssh", "sshd"):
            if service_is_active(unit):
                service_status = "active"
                break

        service_text = "🟢 работает" if service_status == "active" else "🔴 не работает"

        # Получаем конфигурацию sshd
        ssh_config = {}

        try:
            result = subprocess.run(
                ["sshd", "-T"], capture_output=True, text=True, timeout=5
            )

            for line in result.stdout.splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2:
                    ssh_config[parts[0]] = parts[1]

        except Exception:
            pass

        port = ssh_config.get("port", "22")

        password_auth = ssh_config.get("passwordauthentication", "unknown").lower()

        permit_root = ssh_config.get("permitrootlogin", "unknown").lower()

        if password_auth == "yes":
            password_text = "⚠️ разрешён"
        elif password_auth == "no":
            password_text = "✅ отключён"
        else:
            password_text = "❓ неизвестно"

        if permit_root == "without-password":
            root_text = "🔑 только ключи"
        elif permit_root == "no":
            root_text = "🚫 запрещён полностью"
        elif permit_root == "yes":
            root_text = "⚠️ разрешён"
        else:
            root_text = permit_root

        return (
            f"🔐 *SSH-меню*{NL}"
            f"🖥 Сервис: {BT}{service_text}{BT}{NL}"
            f"🔌 Порт: {BT}{port}{BT}{NL}{NL}"
            f"🔐 Авторизация по паролю:{NL}"
            f"🔓 Пользователь: {BT}{password_text}{BT}{NL}"
            f"👤 Root вход: {BT}{root_text}{BT}"
        )

    except Exception as e:
        return f"❌ Ошибка SSH статуса: {BT}{e}{BT}"


def get_authorized_keys_path():
    """Возвращает путь к authorized_keys для экспорта"""
    return str(SSH_AUTHORIZED_KEYS)


# Экспорт словарей для использования в zvertbot.py
__all__ = [
    "SSH_IP_MAP",
    "SSH_KEY_MAP",
    "delete_ssh_key",
    "get_authorized_keys_path",
    "get_ssh_history",
    "get_ssh_keys_list",
    "get_ssh_status",
]
