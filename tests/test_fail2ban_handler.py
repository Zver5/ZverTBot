"""
Тесты для handlers/features/fail2ban.py
Проверяет callback'и Fail2ban: menu, status, logs, unban
"""

from unittest.mock import Mock, patch

import pytest

from handlers.features.fail2ban import (
    handle_fail2ban_callback,
    process_fail2ban_unban,
    render_fail2ban_logs,
    render_fail2ban_menu,
    render_fail2ban_unban_input,
)


@pytest.fixture
def mock_bot():
    bot = Mock()
    bot.edit_message_text = Mock()
    bot.send_message = Mock()
    bot.answer_callback_query = Mock()
    bot.register_next_step_handler = Mock()
    return bot


@pytest.fixture(autouse=True)
def mock_navigation():
    """Изолировать unit-тесты обработчика Fail2ban от глобальной navigation."""
    with patch("handlers.features.fail2ban.navigation") as navigation:
        navigation.current.return_value = None
        yield navigation


@pytest.fixture
def mock_call():
    call = Mock()
    call.id = "12345"
    call.message = Mock()
    call.message.message_id = 67890
    call.message.chat.id = 111222
    return call


@pytest.fixture
def mock_message():
    message = Mock()
    message.chat.id = 111222
    message.message_id = 12345
    message.text = "192.168.1.100"
    return message


class TestHandleFail2banCallback:
    """Тесты для handle_fail2ban_callback"""

    def test_fail2ban_menu_returns_true(self, mock_bot, mock_call):
        """Тест: data='fail2ban_menu' возвращает True"""
        with patch("ui.keyboards.fail2ban_menu_kb", return_value=Mock()):
            result = handle_fail2ban_callback(
                mock_bot, 111222, mock_call, "fail2ban_menu"
            )
            assert result.show_alert is False
            assert result.text is None

    def test_fail2ban_menu_calls_navigation_render(
        self,
        mock_bot,
        mock_call,
        mock_navigation,
    ):
        """Тест: fail2ban_menu передаёт экран в navigation.render"""
        handle_fail2ban_callback(mock_bot, 111222, mock_call, "fail2ban_menu")

        mock_navigation.go.assert_called_once()
        mock_navigation.render.assert_called_once_with(
            "fail2ban_menu",
            mock_bot,
            111222,
            mock_call.message.message_id,
        )

    def test_fail2ban_menu_returns_callback_response(self, mock_bot, mock_call):
        """Тест: fail2ban_menu возвращает CallbackResponse"""
        with patch("ui.keyboards.fail2ban_menu_kb", return_value=Mock()):
            result = handle_fail2ban_callback(
                mock_bot, 111222, mock_call, "fail2ban_menu"
            )

        assert result.text is None
        assert result.show_alert is False
        mock_bot.answer_callback_query.assert_not_called()

    def test_fail2ban_logs_returns_true(self, mock_bot, mock_call):
        """Тест: data='fail2ban_logs' возвращает True"""
        with patch(
            "handlers.features.fail2ban.get_fail2ban_logs", return_value="📋 Логи"
        ):
            result = handle_fail2ban_callback(
                mock_bot, 111222, mock_call, "fail2ban_logs"
            )
            assert result.text == "Загружаю логи..."
            assert result.show_alert is False

    def test_fail2ban_logs_calls_navigation_render(
        self,
        mock_bot,
        mock_call,
        mock_navigation,
    ):
        """Тест: fail2ban_logs передаёт экран в navigation.render"""
        handle_fail2ban_callback(mock_bot, 111222, mock_call, "fail2ban_logs")

        mock_navigation.go.assert_called_once()
        mock_navigation.render.assert_called_once_with(
            "fail2ban_logs",
            mock_bot,
            111222,
            mock_call.message.message_id,
        )

    def test_fail2ban_unban_returns_callback_response(self, mock_bot, mock_call):
        """Тест: data='fail2ban_unban' возвращает CallbackResponse"""
        result = handle_fail2ban_callback(mock_bot, 111222, mock_call, "fail2ban_unban")
        assert result.text is None
        assert result.show_alert is False

    def test_fail2ban_unban_registers_handler(self, mock_bot, mock_call):
        """Тест: fail2ban_unban регистрирует next_step_handler"""
        handle_fail2ban_callback(mock_bot, 111222, mock_call, "fail2ban_unban")
        mock_bot.register_next_step_handler.assert_called_once()

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        """Тест: неизвестный data возвращает False"""
        result = handle_fail2ban_callback(mock_bot, 111222, mock_call, "unknown_action")
        assert result is False


class TestProcessFail2banUnban:
    """Тесты для process_fail2ban_unban"""

    def test_unban_admin_calls_unban_ip(self, mock_message, mock_bot):
        """Тест: админ вызывает unban_ip"""
        with (
            patch("handlers.features.fail2ban.is_admin", return_value=True),
            patch(
                "handlers.features.fail2ban.unban_ip",
                return_value=(True, "✅ Разбанен"),
            ) as mock_unban,
        ):
            process_fail2ban_unban(mock_bot, 67890, mock_message)
            mock_unban.assert_called_once_with("192.168.1.100")

    def test_unban_not_admin_returns(self, mock_message, mock_bot):
        """Тест: не админ не вызывает unban_ip"""
        with (
            patch("handlers.features.fail2ban.is_admin", return_value=False),
            patch("handlers.features.fail2ban.unban_ip") as mock_unban,
        ):
            process_fail2ban_unban(mock_bot, 67890, mock_message)
            mock_unban.assert_not_called()

    def test_unban_sends_result(self, mock_message, mock_bot):
        """Тест: unban отправляет результат"""
        with (
            patch("handlers.features.fail2ban.is_admin", return_value=True),
            patch(
                "handlers.features.fail2ban.unban_ip",
                return_value=(True, "✅ IP разбанен"),
            ),
        ):
            process_fail2ban_unban(mock_bot, 67890, mock_message)
            mock_bot.send_message.assert_called_once()

    def test_unban_strips_whitespace(self, mock_message, mock_bot):
        """Тест: unban удаляет пробелы из IP"""
        mock_message.text = "  192.168.1.100  "
        with (
            patch("handlers.features.fail2ban.is_admin", return_value=True),
            patch(
                "handlers.features.fail2ban.unban_ip", return_value=(True, "✅")
            ) as mock_unban,
        ):
            process_fail2ban_unban(mock_bot, 67890, mock_message)
            mock_unban.assert_called_once_with("192.168.1.100")


def test_handle_fail2ban_callback_unexpected_error_returns_false(
    mock_bot,
    mock_call,
):
    with patch(
        "handlers.features.fail2ban.navigation.go",
        side_effect=RuntimeError("boom"),
    ):
        result = handle_fail2ban_callback(
            mock_bot,
            111222,
            mock_call,
            "fail2ban_menu",
        )

    assert result is False


def test_process_fail2ban_unban_error_logs_failed_action(
    mock_message,
    mock_bot,
):
    with (
        patch("handlers.features.fail2ban.is_admin", return_value=True),
        patch(
            "handlers.features.fail2ban.unban_ip",
            return_value=(False, "❌ IP не найден"),
        ),
        patch("handlers.features.fail2ban.log_action") as mock_log_action,
    ):
        process_fail2ban_unban(mock_bot, 67890, mock_message)

    mock_log_action.assert_called_once_with(
        "РАЗБАН IP",
        "192.168.1.100",
        "ERROR",
        "❌ IP не найден",
    )


def test_render_fail2ban_menu_edits_message(mock_bot):
    with (
        patch(
            "handlers.features.fail2ban.get_fail2ban_status",
            return_value=(
                "🔒 *Fail2ban меню*\n"
                "✅ Служба: активна\n"
                "📊 Активных jail: 1\n\n"
                "🛡 *sshd*\n"
                "├─ Забанено сейчас: 1\n"
                "└─ Всего банов: 104"
            ),
        ),
        patch(
            "handlers.features.fail2ban.fail2ban_menu_kb",
            return_value=Mock(),
        ) as mock_kb,
    ):
        result = render_fail2ban_menu(mock_bot, 111222, 67890)

    assert result is mock_bot.edit_message_text.return_value
    mock_kb.assert_called_once()
    mock_bot.edit_message_text.assert_called_once_with(
        "🔒 *Fail2ban меню*\n"
        "✅ Служба: активна\n"
        "📊 Активных jail: 1\n\n"
        "🛡 *sshd*\n"
        "├─ Забанено сейчас: 1\n"
        "└─ Всего банов: 104",
        111222,
        67890,
        parse_mode="Markdown",
        reply_markup=mock_kb.return_value,
    )


def test_render_fail2ban_logs_edits_logs(mock_bot):
    with (
        patch(
            "handlers.features.fail2ban.get_fail2ban_logs",
            return_value="📋 Logs",
        ) as mock_logs,
        patch(
            "handlers.features.fail2ban.types.InlineKeyboardMarkup",
            return_value=Mock(),
        ),
        patch(
            "handlers.features.fail2ban.types.InlineKeyboardButton",
            return_value=Mock(),
        ),
    ):
        result = render_fail2ban_logs(mock_bot, 111222, 67890)

    assert result is mock_bot.edit_message_text.return_value
    mock_logs.assert_called_once_with(limit=10)
    mock_bot.edit_message_text.assert_called_once()


def test_handle_fail2ban_callback_suppresses_telegram_message_error(
    mock_bot,
    mock_call,
):
    with patch(
        "handlers.features.fail2ban.navigation.go",
        side_effect=Exception("400 Bad Request: message is not modified"),
    ):
        result = handle_fail2ban_callback(
            mock_bot,
            111222,
            mock_call,
            "fail2ban_menu",
        )

    assert result is False



def test_render_fail2ban_unban_input_edits_message(mock_bot):
    with (
        patch(
            "handlers.features.fail2ban.types.InlineKeyboardMarkup",
            return_value=Mock(),
        ) as mock_kb,
        patch(
            "handlers.features.fail2ban.types.InlineKeyboardButton",
            return_value=Mock(),
        ) as mock_button,
    ):
        result = render_fail2ban_unban_input(mock_bot, 111222, 67890)

    assert result is mock_bot.edit_message_text.return_value
    mock_kb.assert_called_once_with(row_width=1)
    mock_button.assert_called_once_with(
        "↩️ Назад",
        callback_data="nav:back",
    )
    mock_bot.edit_message_text.assert_called_once_with(
        "🔓 *Введите IP для разбана:*\nПример: `192.168.1.100`",
        111222,
        67890,
        parse_mode="Markdown",
        reply_markup=mock_kb.return_value,
    )


def test_process_fail2ban_unban_invalid_ip_returns_error(mock_message, mock_bot):
    mock_message.text = "not-an-ip"

    with (
        patch("handlers.features.fail2ban.is_admin", return_value=True),
        patch("handlers.features.fail2ban.validate_ip", return_value=False),
        patch("handlers.features.fail2ban.unban_ip") as mock_unban,
    ):
        process_fail2ban_unban(mock_bot, 67890, mock_message)

    mock_bot.send_message.assert_called_once_with(
        111222,
        "❌ Неверный IPv4-адрес",
    )
    mock_unban.assert_not_called()


def test_process_fail2ban_unban_delete_prompt_error_is_logged(
    mock_message,
    mock_bot,
):
    mock_bot.delete_message.side_effect = [
        RuntimeError("prompt delete failed"),
        None,
    ]

    with (
        patch("handlers.features.fail2ban.is_admin", return_value=True),
        patch(
            "handlers.features.fail2ban.unban_ip",
            return_value=(True, "✅ Разбанен"),
        ),
        patch("handlers.features.fail2ban.logger.debug") as mock_debug,
    ):
        process_fail2ban_unban(mock_bot, 67890, mock_message)

    mock_debug.assert_called_once()
    args = mock_debug.call_args.args
    assert args[0] == "fail2ban.handler.input_cleanup_failed | error=%s"
    assert isinstance(args[1], RuntimeError)
    assert str(args[1]) == "prompt delete failed"


def test_process_fail2ban_unban_delete_ip_error_is_logged(
    mock_message,
    mock_bot,
):
    mock_bot.delete_message.side_effect = [
        None,
        RuntimeError("ip delete failed"),
    ]

    with (
        patch("handlers.features.fail2ban.is_admin", return_value=True),
        patch(
            "handlers.features.fail2ban.unban_ip",
            return_value=(True, "✅ Разбанен"),
        ),
        patch("handlers.features.fail2ban.logger.debug") as mock_debug,
    ):
        process_fail2ban_unban(mock_bot, 67890, mock_message)

    mock_debug.assert_called_once()
    args = mock_debug.call_args.args
    assert args[0] == "fail2ban.handler.ip_message_cleanup_failed | error=%s"
    assert isinstance(args[1], RuntimeError)
    assert str(args[1]) == "ip delete failed"
