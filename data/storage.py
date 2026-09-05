from config import BOT_TZ

"""
Модуль работы с JSON-файлами данных бота.

Централизует все операции load/save для:
- pending_bindings.json
- client_bindings.json
- bot_stats.json
- awg_users.json
- bot_history.json
"""

import copy
import fcntl
import json
import os
import tempfile
from datetime import datetime

from config.paths import (
    AWG_USERS_JSON,
    BOT_HISTORY,
    BOT_STATS_FILE,
    CLIENT_BINDINGS,
    PENDING_BINDINGS,
    TICKETS_JSON,
)
from utils.logger import logger
from utils.perf import profile

# =====================================================================
# Внутренние функции
# =====================================================================


def _load_json(path: str, default):
    """
    Загружает JSON с блокировкой файла (SHARED LOCK).

    Если файла нет — создаёт его.
    При ошибке возвращает копию значения по умолчанию.
    """
    try:
        if not os.path.isfile(path):
            _save_json(path, copy.deepcopy(default))
            return copy.deepcopy(default)

        with open(path, encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Блокировка на чтение
            try:
                data = json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # Снятие блокировки
            return data

    except Exception as e:
        logger.error("storage.load.failed | path=%s | error=%s", path, e)
        return copy.deepcopy(default)


def _save_json(path: str, data):
    """
    Сохраняет JSON с блокировкой файла (EXCLUSIVE LOCK).

    Ошибка сохранения не скрывается: вызывающий код должен знать,
    что операция записи не выполнена.
    """
    temp_path = None

    try:
        directory = os.path.dirname(path)

        if directory:
            os.makedirs(directory, exist_ok=True)

        # Атомарная запись: уникальный временный файл в той же директории.
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(path)}.",
            dir=directory or ".",
        )

        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # Атомарная замена (гарантирует целостность даже при сбое питания)
        os.replace(temp_path, path)

    except Exception as e:
        if temp_path is not None:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError as cleanup_error:
                logger.error(
                    "storage.save.cleanup_failed | path=%s | error=%s",
                    path,
                    cleanup_error,
                )

        logger.error("storage.save.failed | path=%s | error=%s", path, e)
        raise


# =====================================================================
# Pending bindings
# =====================================================================


def load_pending_bindings():
    """Загрузка заявок на привязку."""
    return _load_json(PENDING_BINDINGS, {})


def save_pending_bindings(data):
    """Сохранение заявок на привязку."""
    _save_json(PENDING_BINDINGS, data)


# =====================================================================
# Client bindings
# =====================================================================


@profile()
def load_client_bindings():
    """Загрузка активных привязок."""
    return _load_json(CLIENT_BINDINGS, {})


@profile()
def save_client_bindings(data):
    """Сохранение активных привязок."""
    _save_json(CLIENT_BINDINGS, data)


# =====================================================================
# Tickets (support system)
# =====================================================================


@profile()
def load_tickets():
    """Загрузка тикетов поддержки."""
    return _load_json(TICKETS_JSON, {})


@profile()
def save_tickets(data):
    """Сохранение тикетов поддержки."""
    _save_json(TICKETS_JSON, data)


# =====================================================================
# AWG registry
# =====================================================================


@profile()
def load_awg_registry():
    """Загрузка реестра AWG."""
    return _load_json(AWG_USERS_JSON, {})


@profile()
def save_awg_registry(data):
    """Сохранение реестра AWG."""
    _save_json(AWG_USERS_JSON, data)


# =====================================================================
# Statistics
# =====================================================================


def load_stats():
    """Загрузка статистики использования бота."""
    default = {
        "commands": {},
        "start_date": datetime.now(BOT_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "total_commands": 0,
    }

    stats = _load_json(BOT_STATS_FILE, default)

    if not isinstance(stats, dict):
        stats = copy.deepcopy(default)

    stats.setdefault("commands", {})
    stats.setdefault("start_date", default["start_date"])
    stats.setdefault("total_commands", 0)

    return stats


def save_stats(stats):
    """Сохранение статистики использования бота."""
    _save_json(BOT_STATS_FILE, stats)


# =====================================================================
# History
# =====================================================================


def load_history(history_path: str = BOT_HISTORY) -> list:
    """Загрузка истории действий бота."""
    return _load_json(history_path, [])


def save_history(history: list, history_path: str = BOT_HISTORY):
    """
    Сохранение истории действий бота.

    Хранятся только последние 100 записей.
    """
    _save_json(history_path, history[-100:])


# =====================================================================
# Callback history
# =====================================================================
