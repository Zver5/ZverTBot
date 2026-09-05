"""
Тесты для handlers/features/processes.py
Проверяет callback'и мониторинга процессов: menu, cpu, ram, search, kill
"""

from unittest.mock import Mock, mock_open, patch

import pytest

from handlers.features.processes import (
    handle_processes_callback,
    process_kill_handler,
    process_search_handler,
    render_processes_kill_input,
    render_processes_menu,
    render_processes_search_input,
    render_processes_top,
    render_processes_top_cpu,
    render_processes_top_ram,
)


@pytest.fixture
def mock_bot():
    bot = Mock()
    bot.edit_message_text = Mock()
    bot.send_message = Mock()
    bot.answer_callback_query = Mock()
    bot.register_next_step_handler = Mock()
    return bot


@pytest.fixture
def mock_call():
    call = Mock()
    call.id = "12345"
    call.message = Mock()
    call.message.message_id = 67890
    call.message.chat.id = 111222
    return call


@pytest.fixture(autouse=True)
def mock_navigation():
    """Изолировать unit-тесты обработчика процессов от глобальной navigation."""
    with patch("handlers.features.processes.navigation") as navigation:
        navigation.current.return_value = None
        yield navigation


@pytest.fixture
def mock_message():
    message = Mock()
    message.chat.id = 111222
    message.message_id = 12345
    message.text = "test"
    return message


class TestHandleProcessesCallback:
    """Тесты для handle_processes_callback"""

    def test_processes_menu_returns_true(self, mock_bot, mock_call):
        """Тест: data='processes_menu' возвращает True"""
        with patch("ui.keyboards.processes_menu_kb", return_value=Mock()):
            result = handle_processes_callback(
                mock_bot, 111222, mock_call, "processes_menu"
            )
            assert result.show_alert is False
            assert result.text is None

    def test_processes_menu_uses_navigation_renderer(
        self,
        mock_bot,
        mock_call,
        mock_navigation,
    ):
        """Тест: processes_menu переходит и отрисовывается через NavigationManager."""
        with patch("ui.keyboards.processes_menu_kb", return_value=Mock()):
            handle_processes_callback(mock_bot, 111222, mock_call, "processes_menu")

        mock_navigation.go.assert_called_once_with(
            111222,
            "processes_menu",
        )
        mock_navigation.render.assert_called_once_with(
            "processes_menu",
            mock_bot,
            111222,
            mock_call.message.message_id,
        )
        mock_bot.edit_message_text.assert_not_called()

    def test_processes_menu_returns_callback_response(self, mock_bot, mock_call):
        """Тест: processes_menu возвращает CallbackResponse"""
        with patch("ui.keyboards.processes_menu_kb", return_value=Mock()):
            result = handle_processes_callback(
                mock_bot, 111222, mock_call, "processes_menu"
            )

        assert result.text is None
        assert result.show_alert is False
        mock_bot.answer_callback_query.assert_not_called()

    def test_processes_top_uses_cpu_and_go(
        self,
        mock_bot,
        mock_call,
        mock_navigation,
    ):
        """Тест: processes_top добавляет экран через go и render."""
        result = handle_processes_callback(
            mock_bot,
            111222,
            mock_call,
            "processes_top",
        )

        assert result.text == "Загружаю топ процессов..."
        assert result.show_alert is False
        mock_navigation.go.assert_called_once_with(111222, "processes_top")
        mock_navigation.replace.assert_not_called()
        mock_navigation.render.assert_called_once_with(
            "processes_top",
            mock_bot,
            111222,
            mock_call.message.message_id,
        )

    def test_processes_top_cpu_uses_replace(
        self,
        mock_bot,
        mock_call,
        mock_navigation,
    ):
        """Тест: processes_top_cpu заменяет текущий экран."""
        with patch(
            "handlers.features.processes.format_processes_text",
            return_value="📊 Топ CPU",
        ):
            result = handle_processes_callback(
                mock_bot,
                111222,
                mock_call,
                "processes_top_cpu",
            )

        assert result.text == "Сортировка по CPU..."
        assert result.show_alert is False
        mock_navigation.replace.assert_called_once_with(
            111222,
            "processes_top_cpu",
        )
        mock_navigation.go.assert_not_called()

    def test_processes_top_ram_uses_replace(
        self,
        mock_bot,
        mock_call,
        mock_navigation,
    ):
        """Тест: processes_top_ram заменяет текущий экран."""
        with patch(
            "handlers.features.processes.format_processes_text",
            return_value="📊 Топ RAM",
        ):
            result = handle_processes_callback(
                mock_bot,
                111222,
                mock_call,
                "processes_top_ram",
            )

        assert result.text == "Сортировка по RAM..."
        assert result.show_alert is False
        mock_navigation.replace.assert_called_once_with(
            111222,
            "processes_top_ram",
        )
        mock_navigation.go.assert_not_called()

    def test_processes_cpu_returns_true(self, mock_bot, mock_call):
        """Тест: data='processes_cpu' возвращает True"""
        with patch(
            "handlers.features.processes.format_processes_text",
            return_value="📊 Топ CPU",
        ):
            result = handle_processes_callback(
                mock_bot, 111222, mock_call, "processes_top_cpu"
            )
            assert result.text == "Сортировка по CPU..."
            assert result.show_alert is False

    def test_processes_cpu_renders_registered_screen(self, mock_bot, mock_call):
        """Тест: processes_top_cpu отрисовывается через NavigationManager."""
        with patch("handlers.features.processes.navigation") as mock_navigation:
            mock_navigation.current.return_value = "processes_top"
            handle_processes_callback(
                mock_bot,
                111222,
                mock_call,
                "processes_top_cpu",
            )

        mock_navigation.replace.assert_called_once_with(
            111222,
            "processes_top_cpu",
        )
        mock_navigation.render.assert_called_once_with(
            "processes_top_cpu",
            mock_bot,
            111222,
            mock_call.message.message_id,
        )

    def test_processes_ram_returns_true(self, mock_bot, mock_call):
        """Тест: data='processes_ram' возвращает True"""
        with patch(
            "handlers.features.processes.format_processes_text",
            return_value="📊 Топ RAM",
        ):
            result = handle_processes_callback(
                mock_bot, 111222, mock_call, "processes_top_ram"
            )
            assert result.text == "Сортировка по RAM..."
            assert result.show_alert is False

    def test_processes_ram_renders_registered_screen(self, mock_bot, mock_call):
        """Тест: processes_top_ram отрисовывается через NavigationManager."""
        with patch("handlers.features.processes.navigation") as mock_navigation:
            mock_navigation.current.return_value = "processes_top"
            handle_processes_callback(
                mock_bot,
                111222,
                mock_call,
                "processes_top_ram",
            )

        mock_navigation.replace.assert_called_once_with(
            111222,
            "processes_top_ram",
        )
        mock_navigation.render.assert_called_once_with(
            "processes_top_ram",
            mock_bot,
            111222,
            mock_call.message.message_id,
        )

    def test_process_search_returns_callback_response(self, mock_bot, mock_call):
        """Тест: data='process_search' возвращает CallbackResponse"""
        result = handle_processes_callback(
            mock_bot, 111222, mock_call, "process_search"
        )
        assert result.show_alert is False
        assert result.text == "Введите имя процесса..."

    def test_process_search_registers_handler(self, mock_bot, mock_call):
        """Тест: process_search регистрирует next_step_handler"""
        handle_processes_callback(mock_bot, 111222, mock_call, "process_search")
        mock_bot.register_next_step_handler.assert_called_once()

    def test_process_kill_returns_callback_response(self, mock_bot, mock_call):
        """Тест: data='process_kill' возвращает CallbackResponse"""
        result = handle_processes_callback(mock_bot, 111222, mock_call, "process_kill")
        assert result.show_alert is False
        assert result.text == "Введите PID процесса..."

    def test_process_kill_registers_handler(self, mock_bot, mock_call):
        """Тест: process_kill регистрирует next_step_handler"""
        handle_processes_callback(mock_bot, 111222, mock_call, "process_kill")
        mock_bot.register_next_step_handler.assert_called_once()

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        """Тест: неизвестный data возвращает False"""
        result = handle_processes_callback(
            mock_bot, 111222, mock_call, "unknown_action"
        )
        assert result is False


class TestProcessSearchHandler:
    """Тесты для process_search_handler"""

    def test_search_admin_calls_search(self, mock_message, mock_bot):
        """Тест: админ вызывает search_process_by_name"""
        with (
            patch("handlers.features.processes.is_admin", return_value=True),
            patch(
                "handlers.features.processes.search_process_by_name",
                return_value="🔍 Результаты",
            ) as mock_search,
        ):
            process_search_handler(mock_bot, 99999, mock_message)
            mock_search.assert_called_once_with("test")

    def test_search_not_admin_returns(self, mock_message, mock_bot):
        """Тест: не админ не вызывает search_process_by_name"""
        with (
            patch("handlers.features.processes.is_admin", return_value=False),
            patch("handlers.features.processes.search_process_by_name") as mock_search,
        ):
            process_search_handler(mock_bot, 99999, mock_message)
            mock_search.assert_not_called()

    def test_search_sends_result(self, mock_message, mock_bot):
        """Тест: search отправляет результат"""
        with (
            patch("handlers.features.processes.is_admin", return_value=True),
            patch(
                "handlers.features.processes.search_process_by_name",
                return_value="🔍 Найдено 3 процесса",
            ),
        ):
            process_search_handler(mock_bot, 99999, mock_message)
            mock_bot.send_message.assert_called_once()

    def test_search_strips_whitespace(self, mock_message, mock_bot):
        """Тест: search удаляет пробелы из имени"""
        mock_message.text = "  xray  "
        with (
            patch("handlers.features.processes.is_admin", return_value=True),
            patch(
                "handlers.features.processes.search_process_by_name", return_value="🔍"
            ) as mock_search,
        ):
            process_search_handler(mock_bot, 99999, mock_message)
            mock_search.assert_called_once_with("xray")


class TestProcessKillHandler:
    """Тесты для process_kill_handler"""

    def test_kill_rejects_invalid_pid(self, mock_message, mock_bot):
        mock_message.text = "abc"

        with (
            patch("handlers.features.processes.is_admin", return_value=True),
            patch("handlers.features.processes.kill_process_by_pid") as mock_kill,
        ):
            process_kill_handler(mock_bot, 99999, mock_message)

        mock_kill.assert_not_called()
        mock_bot.send_message.assert_called_once_with(
            111222,
            "❌ Неверный формат PID",
        )


    def test_kill_admin_calls_kill(self, mock_message, mock_bot):
        """Тест: админ вызывает kill_process_by_pid"""
        mock_message.text = "1234"
        with (
            patch("handlers.features.processes.is_admin", return_value=True),
            patch(
                "handlers.features.processes.kill_process_by_pid",
                return_value=(True, "✅ Процесс завершён"),
            ) as mock_kill,
        ):
            process_kill_handler(mock_bot, 99999, mock_message)
            mock_kill.assert_called_once_with("1234")

    def test_kill_not_admin_returns(self, mock_message, mock_bot):
        """Тест: не админ не вызывает kill_process_by_pid"""
        mock_message.text = "1234"
        with (
            patch("handlers.features.processes.is_admin", return_value=False),
            patch("handlers.features.processes.kill_process_by_pid") as mock_kill,
        ):
            process_kill_handler(mock_bot, 99999, mock_message)
            mock_kill.assert_not_called()

    def test_kill_sends_result(self, mock_message, mock_bot):
        """Тест: kill отправляет результат"""
        mock_message.text = "1234"
        with (
            patch("handlers.features.processes.is_admin", return_value=True),
            patch(
                "handlers.features.processes.kill_process_by_pid",
                return_value=(True, "✅ PID 1234 завершён"),
            ),
        ):
            process_kill_handler(mock_bot, 99999, mock_message)
            mock_bot.send_message.assert_called_once()

    def test_kill_strips_whitespace(self, mock_message, mock_bot):
        """Тест: kill удаляет пробелы из PID"""
        mock_message.text = "  1234  "
        with (
            patch("handlers.features.processes.is_admin", return_value=True),
            patch(
                "handlers.features.processes.kill_process_by_pid",
                return_value=(True, "✅"),
            ) as mock_kill,
        ):
            process_kill_handler(mock_bot, 99999, mock_message)
            mock_kill.assert_called_once_with("1234")


def test_processes_menu_when_already_current_returns_true(
    mock_bot,
    mock_call,
):
    with patch("handlers.features.processes.navigation") as mock_navigation:
        mock_navigation.current.return_value = "processes_menu"

        result = handle_processes_callback(
            mock_bot,
            111222,
            mock_call,
            "processes_menu",
        )

    assert result.text is None
    assert result.show_alert is False
    mock_navigation.go.assert_not_called()
    mock_navigation.render.assert_not_called()


def test_handle_processes_callback_unexpected_error_returns_false(
    mock_bot,
    mock_call,
):
    with patch(
        "handlers.features.processes.navigation.current",
        side_effect=RuntimeError("boom"),
    ):
        result = handle_processes_callback(
            mock_bot,
            111222,
            mock_call,
            "processes_menu",
        )

    assert result is False


def test_render_processes_menu_edits_message(mock_bot):
    with patch(
        "handlers.features.processes.processes_menu_kb",
        return_value=Mock(),
    ) as mock_kb:
        result = render_processes_menu(mock_bot, 111222, 67890)

    assert result is mock_bot.edit_message_text.return_value
    mock_kb.assert_called_once()
    mock_bot.edit_message_text.assert_called_once_with(
        "📊 *Мониторинг процессов*\nВыберите действие:",
        111222,
        67890,
        parse_mode="Markdown",
        reply_markup=mock_kb.return_value,
    )


def test_render_processes_top_uses_cpu(mock_bot):
    with (
        patch(
            "handlers.features.processes.format_processes_text",
            return_value="CPU",
        ) as mock_format,
        patch(
            "handlers.features.processes.types.InlineKeyboardMarkup",
            return_value=Mock(),
        ),
    ):
        result = render_processes_top(mock_bot, 111222, 67890)

    assert result is mock_bot.edit_message_text.return_value
    mock_format.assert_called_once_with(sort_by="cpu")
    mock_bot.edit_message_text.assert_called_once()


def test_render_processes_top_cpu_uses_cpu(mock_bot):
    with (
        patch(
            "handlers.features.processes.format_processes_text",
            return_value="CPU",
        ) as mock_format,
        patch(
            "handlers.features.processes.types.InlineKeyboardMarkup",
            return_value=Mock(),
        ),
    ):
        result = render_processes_top_cpu(mock_bot, 111222, 67890)

    assert result is mock_bot.edit_message_text.return_value
    mock_format.assert_called_once_with(sort_by="cpu")


def test_render_processes_top_ram_uses_mem(mock_bot):
    with (
        patch(
            "handlers.features.processes.format_processes_text",
            return_value="RAM",
        ) as mock_format,
        patch(
            "handlers.features.processes.types.InlineKeyboardMarkup",
            return_value=Mock(),
        ),
    ):
        result = render_processes_top_ram(mock_bot, 111222, 67890)

    assert result is mock_bot.edit_message_text.return_value
    mock_format.assert_called_once_with(sort_by="mem")


def test_render_processes_top_message_not_modified_returns_true(mock_bot):
    with (
        patch(
            "handlers.features.processes.format_processes_text",
            return_value="CPU",
        ),
        patch(
            "handlers.features.processes.types.InlineKeyboardMarkup",
            return_value=Mock(),
        ),
    ):
        mock_bot.edit_message_text.side_effect = Exception(
            "400 Bad Request: message is not modified"
        )

        result = render_processes_top(mock_bot, 111222, 67890)

    assert result is True


def test_render_processes_top_reraises_other_error(mock_bot):
    with (
        patch(
            "handlers.features.processes.format_processes_text",
            return_value="CPU",
        ),
        patch(
            "handlers.features.processes.types.InlineKeyboardMarkup",
            return_value=Mock(),
        ),
    ):
        mock_bot.edit_message_text.side_effect = Exception("some other error")

        with pytest.raises(Exception, match="some other error"):
            render_processes_top(mock_bot, 111222, 67890)


def test_handle_processes_callback_suppresses_telegram_message_error(
    mock_bot,
    mock_call,
):
    with patch(
        "handlers.features.processes.navigation.render",
        side_effect=Exception("400 Bad Request: message error"),
    ):
        result = handle_processes_callback(
            mock_bot,
            111222,
            mock_call,
            "processes_menu",
        )

    assert result is False


def test_process_kill_reads_process_name_and_logs_error(
    mock_message,
    mock_bot,
):
    mock_message.text = "1234"

    with (
        patch("handlers.features.processes.is_admin", return_value=True),
        patch(
            "handlers.features.processes.kill_process_by_pid",
            return_value=(False, "❌ Не удалось завершить"),
        ),
        patch("handlers.features.processes.log_action") as mock_log_action,
        patch(
            "builtins.open",
            return_value=Mock(
                __enter__=Mock(return_value=Mock(read=Mock(return_value="xray\n"))),
                __exit__=Mock(return_value=None),
            ),
        ),
    ):
        process_kill_handler(mock_bot, 99999, mock_message)

    mock_log_action.assert_called_once_with(
        "ЗАВЕРШЕНИЕ ПРОЦЕССА",
        "xray",
        "ERROR",
        "❌ Не удалось завершить",
    )


def test_render_processes_search_input(mock_bot):
    result = render_processes_search_input(mock_bot, 123, 456)

    mock_bot.edit_message_text.assert_called_once()
    args, kwargs = mock_bot.edit_message_text.call_args
    assert args[:3] == (
        "🔍 *Введите имя процесса для поиска:*\nПример: `xray`, `python`, `nginx`",
        123,
        456,
    )
    assert kwargs["parse_mode"] == "Markdown"
    assert result == mock_bot.edit_message_text.return_value


def test_render_processes_kill_input(mock_bot):
    result = render_processes_kill_input(mock_bot, 123, 456)

    mock_bot.edit_message_text.assert_called_once()
    args, kwargs = mock_bot.edit_message_text.call_args
    assert args[:3] == (
        "🛑 *Введите PID процесса для завершения:*\n"
        "💡 PID можно найти в Топ CPU/RAM\n"
        "Пример: `1234`",
        123,
        456,
    )
    assert kwargs["parse_mode"] == "Markdown"
    assert result == mock_bot.edit_message_text.return_value


def test_process_search_delete_errors_are_logged(mock_message, mock_bot):
    mock_bot.delete_message.side_effect = RuntimeError("delete failed")

    with (
        patch("handlers.features.processes.is_admin", return_value=True),
        patch(
            "handlers.features.processes.search_process_by_name",
            return_value="🔍",
        ),
        patch("handlers.features.processes.logger.debug") as mock_debug,
    ):
        process_search_handler(mock_bot, 99999, mock_message)

    assert mock_debug.call_count == 2

    assert mock_debug.call_args_list[0].args[0] == (
        "processes.search.input_cleanup_failed | error=%s"
    )
    assert isinstance(mock_debug.call_args_list[0].args[1], RuntimeError)
    assert str(mock_debug.call_args_list[0].args[1]) == "delete failed"

    assert mock_debug.call_args_list[1].args[0] == (
        "processes.search.message_cleanup_failed | error=%s"
    )
    assert isinstance(mock_debug.call_args_list[1].args[1], RuntimeError)
    assert str(mock_debug.call_args_list[1].args[1]) == "delete failed"


def test_process_kill_delete_errors_are_logged(mock_message, mock_bot):
    mock_message.text = "1234"
    mock_bot.delete_message.side_effect = RuntimeError("delete failed")

    with (
        patch("handlers.features.processes.is_admin", return_value=True),
        patch(
            "handlers.features.processes.kill_process_by_pid",
            return_value=(True, "✅"),
        ),
        patch(
            "handlers.features.processes.open",
            mock_open(read_data="python\n"),
        ),
        patch("handlers.features.processes.logger.debug") as mock_debug,
    ):
        process_kill_handler(mock_bot, 99999, mock_message)

    assert mock_debug.call_count == 2

    assert mock_debug.call_args_list[0].args[0] == (
        "processes.kill.input_cleanup_failed | error=%s"
    )
    assert isinstance(mock_debug.call_args_list[0].args[1], RuntimeError)
    assert str(mock_debug.call_args_list[0].args[1]) == "delete failed"

    assert mock_debug.call_args_list[1].args[0] == (
        "processes.kill.message_cleanup_failed | error=%s"
    )
    assert isinstance(mock_debug.call_args_list[1].args[1], RuntimeError)
    assert str(mock_debug.call_args_list[1].args[1]) == "delete failed"
