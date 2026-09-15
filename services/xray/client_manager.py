"""Модуль управления клиентами Xray (VLESS+Reality).
Содержит функции создания клиентов и перезапуска службы Xray.
"""

import shutil
import subprocess

from config.paths import XRAY_CONF
from services.xray.config_manager import (
    add_client_to_all_inbounds,
    get_xray_readiness,
    load_xray_config,
    save_xray_config,
)
from utils.client_operation_lock import client_operation_lock
from utils.logger import logger
from utils.perf import profile
from utils.service_control import restart_service
from utils.validators import (
    is_username_unique_awg,
    is_username_unique_vless,
    validate_username,
)


@profile()
def reload_xray():
    """Перезапускает службу Xray после изменения конфигурации."""
    restart_service("xray")



@client_operation_lock
def xray_add_user(username: str) -> tuple[bool, str]:
    """
    Создаёт нового клиента Xray (VLESS+Reality).

    Args:
        username: Имя клиента (латиница, цифры, _ -)

    Returns:
        (success, message): Кортеж (True, UUID) или (False, ошибка)
    """
    try:
        if shutil.which("xray") is None:
            return False, "❌ Xray не установлен"

        if not XRAY_CONF.is_file():
            return False, f"❌ Путь Xray не найден: {XRAY_CONF}"

        if not validate_username(username):
            return False, "❌ Только латиница, цифры, _ -"

        config = load_xray_config()

        ready, problems = get_xray_readiness(config)
        if not ready:
            details = "\n".join(f"• {problem}" for problem in problems)
            return (
                False,
                "❌ Конфигурация Xray не готова к созданию клиента.\n\n"
                f"Причина:\n{details}\n\n"
                "⚙️ Настройте config.json и повторите создание клиента.",
            )

        # Проверка на существование во всех VLESS inbound'ах
        if not is_username_unique_vless(username):
            return False, "❌ Уже существует (без учёта регистра)"

        if not is_username_unique_awg(username):
            return False, "❌ Уже существует (без учёта регистра)"

        # Генерация UUID через xray uuid
        uuid = subprocess.run(
            ["xray", "uuid"], capture_output=True, text=True, check=True
        ).stdout.strip()

        # Добавление во ВСЕ VLESS inbound'ы (дублирование для универсальности)
        added_count = add_client_to_all_inbounds(config, username, uuid)

        if added_count == 0:
            return False, "🚫 VLESS inbound не найден"

        # save_xray_config сначала проверяет candidate-конфиг,
        # и только после успешной проверки заменяет рабочий config.
        save_xray_config(config)

        # Перезапуск Xray
        reload_xray()

        return True, uuid

    except Exception as e:
        logger.error(
            "xray.client.add_failed | username=%s | error=%s",
            username,
            e,
        )
        return False, f"❌ Ошибка Xray: {e}"
