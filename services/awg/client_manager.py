"""Модуль управления клиентами AmneziaWG.
Содержит функции создания и удаления клиентов.
Работает с реестром awg_users.json, running config и awg0.conf.
"""

import shutil
import subprocess

from config.paths import AWG_CONF
from data.storage import load_awg_registry, save_awg_registry
from services.awg.config_manager import add_peer_to_config, remove_peer_from_config
from services.awg.ip_manager import find_free_awg_ip
from utils.client_operation_lock import client_operation_lock
from utils.logger import logger
from utils.validators import (
    is_username_unique_awg,
    is_username_unique_vless,
)


@client_operation_lock
def awg_add_user(username: str) -> tuple[bool, str]:
    """
    Создаёт нового клиента AmneziaWG.

    Процесс:
    1. Проверка уникальности имени (case-insensitive)
    2. Генерация приватного и публичного ключей (awg genkey/pubkey)
    3. Поиск свободного IP (10.66.66.8-99)
    4. Добавление в реестр awg_users.json
    5. Добавление в running config (awg set)
    6. Добавление в awg0.conf (для персистентности)

    Args:
        username: Имя клиента (латиница, цифры, _ -)

    Returns:
        (success, message): Кортеж (True, IP) или (False, ошибка)
    """
    try:
        # Проверка уникальности
        if not is_username_unique_awg(username):
            return False, "❌ Уже существует (без учёта регистра)"

        if not is_username_unique_vless(username):
            return False, "❌ Уже существует (без учёта регистра)"

        if shutil.which("awg") is None:
            return False, "❌ AWG не установлен"

        if not AWG_CONF.is_file():
            return False, f"❌ Путь AWG не найден: {AWG_CONF}"

        # Генерация ключей
        priv = subprocess.run(
            ["awg", "genkey"], capture_output=True, text=True, check=True
        ).stdout.strip()

        pub = subprocess.run(
            ["awg", "pubkey"], input=priv, capture_output=True, text=True, check=True
        ).stdout.strip()

        # Поиск свободного IP
        ip = find_free_awg_ip()
        if not ip:
            return False, "❌ Нет свободных IP (8-99)"

        # Добавление в реестр
        reg = load_awg_registry()
        reg[username] = {"privkey": priv, "pubkey": pub, "ip": ip}
        save_awg_registry(reg)

        # Добавление в running config (без перезапуска службы)
        result = subprocess.run(
            ["awg", "set", "awg0", "peer", pub, "allowed-ips", f"{ip}/32"],
            capture_output=True,
            text=True,
        )

        if getattr(result, "returncode", 0) != 0:
            logger.error(
                "awg.runtime.add_failed | username=%s | ip=%s | error=%s",
                username,
                ip,
                getattr(result, "stderr", ""),
            )
            del reg[username]
            save_awg_registry(reg)
            return False, f"❌ Ошибка AWG runtime: {getattr(result, 'stderr', '')}"

        # Добавление в awg0.conf (для персистентности после перезагрузки)
        try:
            add_peer_to_config(username, pub, ip)
        except Exception as e:
            logger.error(
                "awg.config.add_failed | username=%s | ip=%s | error=%s",
                username,
                ip,
                e,
            )

            rollback = subprocess.run(
                ["awg", "set", "awg0", "peer", pub, "remove"],
                capture_output=True,
                text=True,
            )

            if getattr(rollback, "returncode", 0) != 0:
                logger.error(
                    "awg.runtime.rollback_failed | username=%s | ip=%s | error=%s",
                    username,
                    ip,
                    getattr(rollback, "stderr", ""),
                )

            reg.pop(username, None)
            save_awg_registry(reg)

            return False, f"❌ Ошибка AWG: {e!s}"

        logger.info(
            "awg.client.created | username=%s | ip=%s",
            username,
            ip,
        )
        return True, ip

    except Exception as e:
        logger.error(
            "awg.client.add_failed | username=%s | error=%s",
            username,
            e,
        )
        return False, f"❌ Ошибка AWG: {e!s}"


@client_operation_lock
def awg_del_user(username: str) -> tuple[bool, str]:
    """
    Удаляет клиента AmneziaWG.

    Процесс:
    1. Проверка наличия в реестре
    2. Удаление из running config (awg set peer remove)
    3. Удаление из awg0.conf (по PublicKey, все 4 строки)
    4. Удаление из реестра awg_users.json

    Args:
        username: Имя клиента для удаления

    Returns:
        (success, message): Кортеж (True, "Удалён") или (False, ошибка)
    """
    try:
        reg = load_awg_registry()

        if username not in reg:
            return False, "❌ Не найден"

        pub = reg[username].get("pubkey")
        if not pub:
            return False, "❌ Нет PublicKey"

        # Удаление из running config
        result = subprocess.run(
            ["awg", "set", "awg0", "peer", pub, "remove"],
            capture_output=True,
            text=True,
        )

        if getattr(result, "returncode", 0) != 0:
            logger.error(
                "awg.runtime.delete_failed | username=%s | error=%s",
                username,
                getattr(result, "stderr", ""),
            )
            return False, f"❌ Ошибка AWG runtime: {getattr(result, 'stderr', '')}"

        # Удаление из awg0.conf (по PublicKey — надёжнее чем по комментарию)
        config_removed = remove_peer_from_config(pub)

        if not config_removed:
            logger.error(
                "awg.config.delete_failed | username=%s | reason=%s",
                username,
                "peer_not_removed",
            )

            rollback = subprocess.run(
                [
                    "awg",
                    "set",
                    "awg0",
                    "peer",
                    pub,
                    "allowed-ips",
                    f"{reg[username].get('ip')}/32",
                ],
                capture_output=True,
                text=True,
            )

            if getattr(rollback, "returncode", 0) != 0:
                logger.error(
                    "awg.runtime.rollback_failed | username=%s | error=%s",
                    username,
                    getattr(rollback, "stderr", ""),
                )

            return False, "❌ Ошибка удаления из awg0.conf"

        # Удаление из реестра
        del reg[username]
        save_awg_registry(reg)

        logger.info("awg.client.deleted | username=%s", username)
        return True, "Удалён"

    except Exception as e:
        logger.error(
            "awg.client.delete_failed | username=%s | error=%s",
            username,
            e,
        )
        return False, f"❌ Ошибка AWG: {e!s}"
