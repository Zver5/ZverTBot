"""
Тесты сетевого handler'а.

Проверяет MTR и очистку ожидаемого ввода при навигации назад.
"""

from unittest.mock import Mock, patch

import pytest

from core.state import INPUT_REQUEST_MSGS
from handlers.admin.navigation import handle_navigation_callback
from handlers.features.network import handle_network_callback, process_mtr_input


@pytest.fixture
def mock_bot():
    """Фикстура: мок бота."""
    bot = Mock()
    bot.edit_message_text = Mock()
    bot.send_message = Mock()
    bot.answer_callback_query = Mock()
    bot.clear_step_handler_by_chat_id = Mock()
    bot.register_next_step_handler = Mock()
    bot.register_next_step_handler_by_chat_id = Mock()
    return bot


@pytest.fixture
def mock_call():
    """Фикстура: мок callback query."""
    call = Mock()
    call.id = "12345"
    call.message = Mock()
    call.message.message_id = 67890
    call.message.chat.id = 111222
    return call


@pytest.fixture(autouse=True)
def cleanup_input_context():
    """Очищает глобальный контекст ввода между тестами."""
    INPUT_REQUEST_MSGS.clear()
    yield
    INPUT_REQUEST_MSGS.clear()


class TestMtrNavigationCleanup:
    """Регрессионные тесты MTR → Назад."""

    @patch("handlers.features.network.types.InlineKeyboardMarkup")
    @patch("handlers.features.network.types.InlineKeyboardButton")
    def test_mtr_registers_input_handler(
        self,
        mock_button,
        mock_markup,
        mock_bot,
        mock_call,
    ):
        """MTR регистрирует текстовый ввод без отдельного сообщения."""
        result = handle_network_callback(
            mock_bot,
            111222,
            mock_call,
            "net_mtr",
        )

        assert result.show_alert is False
        mock_bot.send_message.assert_not_called()
        mock_bot.register_next_step_handler_by_chat_id.assert_called_once_with(
            111222,
            process_mtr_input,
            mock_bot,
            111222,
        )

    def test_navigation_back_clears_mtr_input_context(
        self,
        mock_bot,
        mock_call,
    ):
        """Назад после MTR полностью очищает ожидаемый текстовый ввод."""
        INPUT_REQUEST_MSGS[111222] = 55555

        with (
            patch(
                "handlers.admin.navigation.navigation.back",
                return_value="network_menu",
            ),
            patch(
                "handlers.admin.navigation.render_navigation_screen",
                return_value=True,
            ),
            patch(
                "handlers.admin.navigation.safe_delete",
            ) as mock_delete,
        ):
            result = handle_navigation_callback(
                mock_bot,
                111222,
                mock_call,
                "nav:back",
            )

        assert result is True
        mock_bot.clear_step_handler_by_chat_id.assert_called_once_with(111222)
        assert 111222 not in INPUT_REQUEST_MSGS
        mock_delete.assert_called_once_with(mock_bot, 111222, 55555)

    def test_navigation_home_clears_mtr_input_context(
        self,
        mock_bot,
        mock_call,
    ):
        """Домой после MTR также очищает ожидаемый текстовый ввод."""
        INPUT_REQUEST_MSGS[111222] = 66666

        with (
            patch(
                "handlers.admin.navigation.navigation.home",
                return_value="main",
            ),
            patch(
                "handlers.admin.navigation.render_navigation_screen",
                return_value=True,
            ),
            patch(
                "handlers.admin.navigation.safe_delete",
            ) as mock_delete,
        ):
            result = handle_navigation_callback(
                mock_bot,
                111222,
                mock_call,
                "nav:home",
            )

        assert result is True
        mock_bot.clear_step_handler_by_chat_id.assert_called_once_with(111222)
        assert 111222 not in INPUT_REQUEST_MSGS
        mock_delete.assert_called_once_with(
            mock_bot,
            111222,
            66666,
        )


class TestNetworkCallback:
    """Тесты callback-веток сетевого handler'а."""

    def test_net_mtr_opens_screen_and_answers_callback(
        self,
        mock_bot,
        mock_call,
    ):
        with patch("handlers.features.network.navigation") as mock_navigation:
            mock_navigation.current.return_value = "network_menu"

            result = handle_network_callback(
                mock_bot,
                111222,
                mock_call,
                "net_mtr",
            )

        assert result.show_alert is False
        assert result.text is None
        mock_navigation.go.assert_called_once_with(111222, "net_mtr")
        mock_navigation.render.assert_called_once_with(
            "net_mtr",
            mock_bot,
            111222,
            67890,
        )

    def test_net_mtr_does_not_go_when_already_current(
        self,
        mock_bot,
        mock_call,
    ):
        with patch("handlers.features.network.navigation") as mock_navigation:
            mock_navigation.current.return_value = "net_mtr"

            result = handle_network_callback(
                mock_bot,
                111222,
                mock_call,
                "net_mtr",
            )

        assert result.show_alert is False
        mock_navigation.go.assert_not_called()
        mock_navigation.render.assert_called_once_with(
            "net_mtr",
            mock_bot,
            111222,
            67890,
        )

    def test_mtr_target_starts_mtr(
        self,
        mock_bot,
        mock_call,
    ):
        with patch("handlers.features.network._run_mtr") as mock_run:
            result = handle_network_callback(
                mock_bot,
                111222,
                mock_call,
                "mtr_target_8.8.8.8",
            )

        assert result.show_alert is False
        assert result.text is None
        mock_run.assert_called_once_with(
            mock_bot,
            111222,
            67890,
            "8.8.8.8",
        )

    def test_unknown_callback_returns_false(
        self,
        mock_bot,
        mock_call,
    ):
        result = handle_network_callback(
            mock_bot,
            111222,
            mock_call,
            "unknown_action",
        )

        assert result is False


class TestProcessMtrInput:
    """Тесты текстового ввода цели MTR."""

    def test_invalid_empty_input_shows_error(
        self,
        mock_bot,
    ):
        message = Mock()
        message.text = "   "

        process_mtr_input(message, mock_bot, 111222)

        mock_bot.send_message.assert_called_once_with(
            111222,
            "❌ Некорректный ввод. Попробуйте ещё раз:",
        )

    def test_invalid_short_input_shows_error(
        self,
        mock_bot,
    ):
        message = Mock()
        message.text = "ab"

        process_mtr_input(message, mock_bot, 111222)

        mock_bot.send_message.assert_called_once_with(
            111222,
            "❌ Некорректный ввод. Попробуйте ещё раз:",
        )

    def test_valid_input_starts_mtr(
        self,
        mock_bot,
    ):
        message = Mock()
        message.text = "  example.com  "

        status_message = Mock()
        status_message.message_id = 54321
        mock_bot.send_message.return_value = status_message

        with patch("handlers.features.network._run_mtr") as mock_run:
            process_mtr_input(message, mock_bot, 111222)

        mock_bot.send_message.assert_called_once_with(
            111222,
            "📡 Запуск MTR для `example.com`...\n⏳ Ожидание ~25 сек...",
            parse_mode="Markdown",
        )
        mock_run.assert_called_once_with(
            mock_bot,
            111222,
            54321,
            "example.com",
        )


class TestRunMtr:
    """Тесты выполнения MTR в worker-потоке."""

    @patch("handlers.features.network.threading.Thread")
    def test_mtr_not_installed_shows_error(
        self,
        mock_thread,
        mock_bot,
    ):
        from handlers.features.network import _run_mtr

        worker = None

        def capture_worker(*args, **kwargs):
            nonlocal worker
            worker = kwargs["target"]
            thread = Mock()
            return thread

        mock_thread.side_effect = capture_worker

        with patch(
            "handlers.features.network.shutil.which",
            return_value=None,
        ):
            _run_mtr(mock_bot, 111222, 67890, "8.8.8.8")
            worker()

        mock_bot.edit_message_text.assert_called_once()
        text = mock_bot.edit_message_text.call_args.args[0]

        assert "MTR не установлен" in text

    @patch("handlers.features.network.threading.Thread")
    def test_mtr_success_shows_result(
        self,
        mock_thread,
        mock_bot,
    ):
        from handlers.features.network import _run_mtr

        worker = None

        def capture_worker(*args, **kwargs):
            nonlocal worker
            worker = kwargs["target"]
            return Mock()

        mock_thread.side_effect = capture_worker

        mock_loop = Mock()

        with (
            patch(
                "handlers.features.network.shutil.which",
                return_value="/usr/bin/mtr",
            ),
            patch(
                "handlers.features.network.asyncio.new_event_loop",
                return_value=mock_loop,
            ),
            patch(
                "handlers.features.network.asyncio.set_event_loop",
            ),
            patch(
                "handlers.features.network.diagnose",
                new_callable=Mock,
                return_value="<b>MTR OK</b>",
            ),
        ):
            mock_loop.run_until_complete.return_value = "<b>MTR OK</b>"

            _run_mtr(mock_bot, 111222, 67890, "8.8.8.8")
            worker()

        mock_loop.close.assert_called_once()
        mock_bot.edit_message_text.assert_called_once_with(
            "<b>MTR OK</b>",
            111222,
            67890,
            parse_mode="HTML",
            reply_markup=mock_bot.edit_message_text.call_args.kwargs["reply_markup"],
        )

    @patch("handlers.features.network.threading.Thread")
    def test_mtr_exception_shows_error(
        self,
        mock_thread,
        mock_bot,
    ):
        from handlers.features.network import _run_mtr

        worker = None

        def capture_worker(*args, **kwargs):
            nonlocal worker
            worker = kwargs["target"]
            return Mock()

        mock_thread.side_effect = capture_worker

        with patch(
            "handlers.features.network.shutil.which",
            side_effect=RuntimeError("boom"),
        ):
            _run_mtr(mock_bot, 111222, 67890, "8.8.8.8")
            worker()

        mock_bot.edit_message_text.assert_called_once()
        text = mock_bot.edit_message_text.call_args.args[0]

        assert text == "❌ Ошибка MTR: boom"
