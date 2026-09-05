"""Модуль централизованной работы с Xray config.json.
Все операции чтения/записи конфигурации Xray проходят через этот модуль.
Устраняет дублирование json.load/json.dump в различных частях бота.
"""

import json
import subprocess
import tempfile
from pathlib import Path

from config.paths import XRAY_CONF
from utils.atomic import atomic_write
from utils.client_operation_lock import client_operation_lock
from utils.logger import logger
from utils.perf import profile


@profile()
def load_xray_config() -> dict:
    """
    Загружает config.json Xray.

    Returns:
        dict: Конфигурация Xray

    Raises:
        FileNotFoundError: Если config.json не существует
        json.JSONDecodeError: Если файл повреждён
    """
    if not XRAY_CONF.exists():
        raise FileNotFoundError(f"Xray config не найден: {XRAY_CONF}")

    try:
        with open(XRAY_CONF, encoding="utf-8") as f:
            config = json.load(f)

    except json.JSONDecodeError as e:
        raise ValueError(f"Поврежден Xray config: {e}") from e

    if not isinstance(config, dict):
        raise ValueError("Xray config должен быть JSON объектом")

    return config


def validate_xray_config_structure(config: dict) -> bool:
    """
    Минимальная проверка структуры Xray config
    перед сохранением.

    Не позволяет случайно заменить рабочий конфиг
    пустым или неправильным JSON.
    """
    if not isinstance(config, dict):
        return False

    if "inbounds" not in config:
        return False

    if not isinstance(config["inbounds"], list):
        return False

    # Должен существовать хотя бы один VLESS inbound
    vless_found = False

    for inbound in config["inbounds"]:
        if inbound.get("protocol") != "vless":
            continue

        vless_found = True

        settings = inbound.get("settings", {})

        if not isinstance(settings, dict):
            return False

        clients = settings.get("clients")

        if not isinstance(clients, list):
            return False

        for client in clients:
            if not isinstance(client, dict):
                return False

            if not client.get("id"):
                return False

            if not client.get("email"):
                return False

    return vless_found


def validate_xray_config(config: dict) -> bool:
    """
    Проверяет candidate-конфигурацию Xray ДО замены рабочего config.json.

    Candidate записывается во временный файл рядом с рабочим конфигом,
    после чего Xray проверяет именно этот файл.
    """
    if not validate_xray_config_structure(config):
        return False

    temp_path = None

    try:
        XRAY_CONF.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(XRAY_CONF.parent),
            prefix=f".{XRAY_CONF.name}.validate.",
            suffix=".json",
            delete=False,
        ) as f:
            temp_path = f.name
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.flush()

        result = subprocess.run(
            [
                "xray",
                "run",
                "-test",
                "-config",
                temp_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            logger.error(
                "xray.config.candidate_validation_failed | error=%s",
                result.stderr.strip(),
            )
            return False

        return True

    except Exception as e:
        logger.error(
            "xray.config.candidate_validation_error | error=%s",
            e,
        )
        return False

    finally:
        if temp_path is not None:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError as e:
                logger.error(
                    "xray.config.cleanup_failed | error=%s",
                    e,
                )


@profile()
@client_operation_lock
def save_xray_config(config: dict) -> None:
    """
    Сохраняет config.json Xray.

    Candidate сначала проходит проверку Xray.
    Рабочий config.json заменяется только после успешной проверки.
    """
    if not validate_xray_config_structure(config):
        raise ValueError("Некорректная структура Xray config")

    if not validate_xray_config(config):
        raise ValueError("Конфиг Xray не прошёл проверку")

    content = json.dumps(config, indent=2, ensure_ascii=False)
    atomic_write(XRAY_CONF, content)


def get_vless_inbounds(config: dict) -> list:
    """
    Возвращает все VLESS inbound'ы из конфига.

    Args:
        config: Конфигурация Xray

    Returns:
        list: Список VLESS inbound'ов
    """
    return [inb for inb in config.get("inbounds", []) if inb.get("protocol") == "vless"]


@profile()
def get_all_vless_clients(config: dict) -> list:
    """
    Возвращает список имён всех VLESS клиентов (без дублей).

    Args:
        config: Конфигурация Xray

    Returns:
        list[str]: Список уникальных имён клиентов
    """
    users = []
    for inb in get_vless_inbounds(config):
        if "clients" in inb.get("settings", {}):
            users.extend([c["email"] for c in inb["settings"]["clients"]])
    # Убираем дубли (клиент дублируется в порты 443 и 2096)
    return list(set(users))


def add_client_to_all_inbounds(config: dict, username: str, uuid: str) -> int:
    """
    Добавляет клиента во ВСЕ VLESS inbound'ы.

    Args:
        config: Конфигурация Xray
        username: Имя клиента
        uuid: UUID клиента

    Returns:
        int: Количество inbound'ов, куда был добавлен клиент
    """
    added_count = 0
    for inb in get_vless_inbounds(config):
        if "clients" not in inb.get("settings", {}):
            continue
        inb["settings"]["clients"].append(
            {"id": uuid, "flow": "xtls-rprx-vision", "email": username, "level": 0}
        )
        added_count += 1
    return added_count


def remove_client_from_all_inbounds(config: dict, username: str) -> int:
    """
    Удаляет клиента из ВСЕХ VLESS inbound'ов.

    Args:
        config: Конфигурация Xray
        username: Имя клиента для удаления

    Returns:
        int: Количество удалений
    """
    removed = 0
    for inb in get_vless_inbounds(config):
        if "clients" not in inb.get("settings", {}):
            continue
        before = len(inb["settings"]["clients"])
        inb["settings"]["clients"] = [
            c for c in inb["settings"]["clients"] if c["email"] != username
        ]
        removed += before - len(inb["settings"]["clients"])
    return removed


@profile()
def rename_client_in_config(config: dict, old_name: str, new_name: str) -> bool:
    """
    Переименовывает клиента во всех VLESS inbound'ах.

    Args:
        config: Конфигурация Xray
        old_name: Старое имя клиента
        new_name: Новое имя клиента

    Returns:
        bool: True если клиент найден и переименован, False иначе
    """
    found = False
    for inb in get_vless_inbounds(config):
        if "clients" not in inb.get("settings", {}):
            continue
        for c in inb["settings"]["clients"]:
            if c.get("email") == old_name:
                c["email"] = new_name
                found = True
    return found
