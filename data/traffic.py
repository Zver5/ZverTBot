"""
Модуль работы с файлами трафика для ZverTBot.
Централизует операции load/save для usage.json (накопительный учёт трафика).
"""

import json
import os

from config.paths import USAGE_JSON
from utils.atomic import atomic_write
from utils.client_operation_lock import client_operation_lock
from utils.logger import logger


def load_usage(usage_path: str = USAGE_JSON) -> dict:
    """Загрузка накопительного трафика из usage.json

    Args:
        usage_path: Путь к usage.json

    Returns:
        Словарь с данными трафика (clients, updated) или пустой словарь
    """
    try:
        if os.path.exists(usage_path):
            with open(usage_path) as f:
                return json.load(f)
    except Exception as e:
        logger.error(
            "traffic.load.failed | error=%s",
            e,
        )
    return {}


def save_usage(data: dict, usage_path: str = USAGE_JSON):
    """Сохранение накопительного трафика в usage.json

    Args:
        data: Словарь с данными трафика
        usage_path: Путь к usage.json
    """
    try:
        content = json.dumps(data, indent=2, ensure_ascii=False)
        atomic_write(usage_path, content)
    except Exception as e:
        logger.error(
            "traffic.save.failed | error=%s",
            e,
        )


def get_client_traffic(username: str, usage_path: str = USAGE_JSON) -> dict:
    """Получение трафика конкретного клиента"""

    try:
        data = load_usage(usage_path)

        clients = data.get("clients", {})

        client = clients.get(username)

        if not client:
            logger.warning(
                "traffic.client.not_found | username=%s",
                username,
            )
            return {"uplink": 0, "downlink": 0, "total": 0}

        return {
            "uplink": int(client.get("uplink", 0)),
            "downlink": int(client.get("downlink", 0)),
            "total": int(client.get("total", 0)),
        }

    except Exception as e:
        logger.error(
            "traffic.client.get_failed | username=%s | error=%s",
            username,
            e,
        )

    return {"uplink": 0, "downlink": 0, "total": 0}


@client_operation_lock
def remove_client_from_usage(
    username: str,
    usage_path: str = USAGE_JSON,
) -> bool:
    """Удалить клиента из usage.json.

    Возвращает True, если запись клиента была удалена.
    """
    try:
        data = load_usage(usage_path)
        clients = data.get("clients", {})

        if username not in clients:
            return False

        del clients[username]
        save_usage(data, usage_path)
        return True

    except Exception as e:
        logger.error(
            "traffic.client.remove_failed | username=%s | error=%s",
            username,
            e,
        )
        return False


@client_operation_lock
def rename_client_in_usage(
    old_name: str,
    new_name: str,
    usage_path: str = USAGE_JSON,
) -> bool:
    """Переименование клиента в usage.json

    Args:
        old_name: Старое имя клиента
        new_name: Новое имя клиента
        usage_path: Путь к usage.json

    Returns:
        True если переименование успешно, False иначе
    """
    try:
        data = load_usage(usage_path)
        clients = data.get("clients", {})

        if old_name in clients:
            clients[new_name] = clients.pop(old_name)
            save_usage(data, usage_path)
            return True
        return False
    except Exception as e:
        logger.error(
            "traffic.client.rename_failed | old_name=%s | new_name=%s | error=%s",
            old_name,
            new_name,
            e,
        )
        return False
