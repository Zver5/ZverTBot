"""Middleware для учёта Telegram-команд."""

from telebot.handler_backends import BaseMiddleware

from data.storage import record_stat_action
from utils.logger import logger


class StatsMiddleware(BaseMiddleware):
    """Учитывает команды до передачи сообщений обработчикам."""

    def __init__(self):
        super().__init__()
        self.update_sensitive = True
        self.update_types = ["message"]

    def pre_process_message(self, message, data):
        text = getattr(message, "text", None)
        if not isinstance(text, str) or not text.startswith("/"):
            return

        command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()
        if len(command) <= 1:
            return

        try:
            record_stat_action(command)
        except Exception:
            logger.exception(
                "stats.command.record_failed | command=%s",
                command,
            )

    def post_process_message(self, message, data, exception):
        """Не вмешивается в результат обработки сообщения."""
        return None
