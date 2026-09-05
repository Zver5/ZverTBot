from config import BOT_TZ

"""
Модуль уведомлений и логирования для ZverTBot.
Содержит функции логирования действий и обновления статистики использования бота.
"""


from datetime import datetime

from data.storage import (
    load_history,
    save_history,
)
from utils.client_operation_lock import client_operation_lock
from utils.logger import logger


@client_operation_lock
def log_action(action: str, target: str, status: str, details: str = ""):
    """Логирует действие в историю бота (bot_history.json)

    Args:
        action: Тип действия (
            СОЗДАНИЕ, УДАЛЕНИЕ, ПЕРЕИМЕНОВАНИЕ, РЕСТАРТ,
            ОЧИСТКА, ПРИВЯЗКА, ОТВЯЗКА
        )
        target: Объект действия (имя клиента, "Бот", "disk")
        status: Статус (SUCCESS, ERROR)
        details: Дополнительные детали (опционально)

    Example:
        log_action("СОЗДАНИЕ", "client_01", "SUCCESS", "Protocol: vless")
        log_action("РЕСТАРТ", "Xray", "SUCCESS")
    """
    try:
        history = load_history()
        entry = {
            "time": datetime.now(BOT_TZ).strftime("%d.%m %H:%M"),
            "action": action,
            "target": target,
            "status": status,
            "details": details,
        }
        history.append(entry)
        # Храним последние 100 записей
        history = history[-100:]
        save_history(history)
    except Exception as e:
        logger.error("notifications.action_log.failed | error=%s", e)
