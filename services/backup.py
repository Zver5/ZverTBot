"""
services/backup.py
Модуль для работы с бэкапами через Telegram-бот.
Функция: формирование текста истории бэкапов.
"""

import json
import subprocess
from datetime import datetime

from config import BOT_TZ
from config.paths import (
    BACKUP_REMOTE,
    BACKUP_ROOT_DIR,
    CONFIG_BACKUPS_DIR,
    RCLONE_STATUS_JSON,
)
from utils.logger import logger

# Маппинг статусов на русский
STATUS_MAP = {
    "success": "Успешно",
    "failed": "Ошибка",
    "running": "Выполняется",
    "warning": "Предупреждение",
}


def format_msk_time(iso_time: str) -> str:
    """Конвертирует ISO-время в московское формат ДД.ММ.ГГГГ ЧЧ:ММ"""
    try:
        # Парсим ISO формат (2026-07-08T15:46:49+00:00)
        dt = datetime.fromisoformat(iso_time)
        # Конвертируем в MSK
        dt_msk = dt.astimezone(BOT_TZ)
        return dt_msk.strftime("%d.%m.%Y %H:%M MSK")
    except Exception as e:
        logger.warning(
            "backup.time.format_failed | error=%s",
            e,
        )
        return iso_time


def get_backup_remote_size() -> str:
    """Получает размер бэкапов в настроенном rclone remote."""
    if not BACKUP_REMOTE or not BACKUP_ROOT_DIR:
        return "N/A"

    remote_path = f"{BACKUP_REMOTE}:{BACKUP_ROOT_DIR}/configs/"

    try:
        result = subprocess.run(
            ["rclone", "size", remote_path, "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return "N/A"
        data = json.loads(result.stdout)
        bytes_total = data.get("bytes", 0)
        count = data.get("count", 0)
        # Форматируем размер
        if bytes_total >= 1024 * 1024 * 1024:
            size_str = f"{bytes_total / (1024 * 1024 * 1024):.2f} GB"
        elif bytes_total >= 1024 * 1024:
            size_str = f"{bytes_total / (1024 * 1024):.1f} MB"
        elif bytes_total >= 1024:
            size_str = f"{bytes_total / 1024:.1f} KB"
        else:
            size_str = f"{bytes_total} B"
        return f"{size_str} ({count} шт.)"
    except Exception as e:
        logger.warning(
            "backup.remote.size_failed | error=%s",
            e,
        )
        return "N/A"


def get_backup_history_text():
    """Формирует текст с историей бэкапов"""
    try:
        # Локальные бэкапы
        result = subprocess.run(
            ["ls", "-lh", str(CONFIG_BACKUPS_DIR)],
            capture_output=True,
            text=True,
        )
        local_files = []

        for line in result.stdout.splitlines():
            if "vps-backup" not in line:
                continue

            prefix, separator, name = line.partition(" vps-backup")
            if not separator:
                continue

            fields = prefix.split()
            if len(fields) < 5:
                continue

            size = fields[4]
            local_files.append((size, "vps-backup" + name))

        text = "💾 *История бэкапов*\n"
        text += f"📁 *Локальные ({len(local_files)} шт.):*\n"
        for size, name in local_files[-5:]:
            text += f"• `{name}` ({size})\n"

        # Размер резервных копий на настроенном remote
        remote_size = get_backup_remote_size()
        text += f"\n☁️ *В облаке:* `{remote_size}`\n"

        # Статус последнего
        try:
            with open(RCLONE_STATUS_JSON) as f:
                status = json.load(f)
            last_time = format_msk_time(status.get("last_backup", ""))
            status_ru = STATUS_MAP.get(
                status.get("status", ""),
                status.get("status", "N/A"),
            )
            text += "\n📊 *Последний бэкап:*\n"
            text += f"📅 `{last_time}`\n"
            text += f"📏 `{status.get('size_mb', 0)} MB`\n"
            text += f"✅ Статус: `{status_ru}`"
        except Exception as e:
            logger.error(
                "backup.history.status_read_failed | error=%s",
                e,
            )
            text += "\n⚠️ Статус недоступен"

        return text
    except Exception as e:
        logger.error(
            "backup.history.failed | error=%s",
            e,
        )
        return f"❌ Ошибка: {e}"
