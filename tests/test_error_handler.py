"""
Unit-тесты для модуля utils/error_handler.py
"""

import pytest
from telebot.apihelper import ApiTelegramException

from utils.error_handler import handle_errors


class TestHandleErrors:
    """Тесты декоратора @handle_errors"""

    def test_successful_function(self):
        """Тест: функция без ошибок возвращает результат"""

        @handle_errors("Test error")
        def success_func():
            return "success"

        result = success_func()
        assert result == "success"

    @staticmethod
    def _telegram_exception(description, error_code=400):
        class Result:
            status_code = error_code
            reason = "Bad Request"
            text = "test response"

        return ApiTelegramException(
            "editMessageText",
            Result(),
            {
                "ok": False,
                "error_code": error_code,
                "description": description,
            },
        )

    def test_suppress_message_not_modified(self):
        """Тест: подавляет реальный ApiTelegramException."""

        @handle_errors("Test error")
        def raise_message_not_modified():
            raise self._telegram_exception("Bad Request: message is not modified")

        result = raise_message_not_modified()
        assert result is None

    def test_suppress_message_to_edit_not_found(self):
        """Тест: подавляет ошибку удалённого сообщения."""

        @handle_errors("Test error")
        def raise_message_not_found():
            raise self._telegram_exception("Bad Request: message to edit not found")

        result = raise_message_not_found()
        assert result is None

    def test_suppress_query_too_old(self):
        """Тест: устаревший callback query является штатной ошибкой."""

        @handle_errors("Test error")
        def raise_old_query():
            raise self._telegram_exception(
                "Bad Request: query is too old and response timeout expired "
                "or query ID is invalid"
            )

        result = raise_old_query()
        assert result is None

    def test_raise_other_telegram_error(self):
        """Тест: другие Telegram API ошибки пробрасываются."""

        @handle_errors("Test error")
        def raise_other_telegram_error():
            raise self._telegram_exception("Bad Request: message can't be parsed")

        with pytest.raises(ApiTelegramException):
            raise_other_telegram_error()

    def test_raise_other_errors(self):
        """Тест: другие ошибки пробрасываются"""

        @handle_errors("Test error")
        def raise_other_error():
            raise ValueError("Some other error")

        # Должно выбросить исключение
        with pytest.raises(ValueError, match="Some other error"):
            raise_other_error()

    def test_preserves_function_name(self):
        """Тест: сохраняет имя функции (functools.wraps)"""

        @handle_errors("Test error")
        def my_function():
            """My docstring"""

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring"

    def test_log_level_parameter(self):
        """Тест: параметр log_level работает"""

        @handle_errors("Test error", log_level="warning")
        def raise_error():
            raise RuntimeError("Test")

        # Должно выбросить исключение (log_level не влияет на пробрасывание)
        with pytest.raises(RuntimeError):
            raise_error()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
