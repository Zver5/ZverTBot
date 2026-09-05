"""
Тесты для handlers/admin/navigation.py
Проверяет навигационные callback'и: hide, manage_menu, back_*
"""

from unittest.mock import Mock, patch

import pytest

from core.navigation import navigation
from handlers.admin.navigation import (
    _safe_edit,
    handle_navigation_callback,
    render_navigation_screen,
)


@pytest.fixture
def mock_bot():
    """Фикстура: мок бота"""
    bot = Mock()
    bot.edit_message_text = Mock()
    bot.send_message = Mock()
    bot.answer_callback_query = Mock()
    bot.clear_step_handler_by_chat_id = Mock()
    return bot


@pytest.fixture
def mock_call():
    """Фикстура: мок callback query"""
    call = Mock()
    call.id = "12345"
    call.message = Mock()
    call.message.message_id = 67890
    call.message.chat.id = 111222
    return call


class TestHandleNavigationCallback:
    """Тесты для handle_navigation_callback"""

    def setup_method(self):
        navigation.clear(111222)

    def test_manage_menu_returns_true(self, mock_bot, mock_call):
        """Тест: data='manage_menu' возвращает True"""
        result = handle_navigation_callback(mock_bot, 111222, mock_call, "nav:manage")
        assert result is True

    def test_manage_menu_calls_edit_message(self, mock_bot, mock_call):
        """Тест: data='manage_menu' вызывает edit_message_text"""
        handle_navigation_callback(mock_bot, 111222, mock_call, "nav:manage")
        mock_bot.edit_message_text.assert_called_once()

    def test_manage_menu_does_not_answer_callback_directly(self, mock_bot, mock_call):
        """Тест: навигация не отвечает callback напрямую"""
        handle_navigation_callback(mock_bot, 111222, mock_call, "nav:manage")
        mock_bot.answer_callback_query.assert_not_called()

    def test_nav_back_returns_true(self, mock_bot, mock_call):
        """Тест: data='nav:back' возвращает предыдущий экран"""
        navigation.start(111222, "main")
        navigation.go(111222, "manage_menu")

        result = handle_navigation_callback(
            mock_bot,
            111222,
            mock_call,
            "nav:back",
        )

        assert result is True
        assert navigation.current(111222) == "main"

    def test_nav_back_handles_input_context(self, mock_bot, mock_call):
        """Тест: data='nav:back' очищает context и возвращает назад"""
        navigation.start(111222, "main")
        navigation.go(111222, "network_menu")

        result = handle_navigation_callback(
            mock_bot,
            111222,
            mock_call,
            "nav:back",
        )

        assert result is True
        assert navigation.current(111222) == "main"
        mock_bot.clear_step_handler_by_chat_id.assert_called_with(111222)

    @pytest.mark.parametrize(
        "callback_data,screen_id",
        [
            ("nav:create", "create_menu"),
            ("nav:manage", "manage_menu"),
            ("nav:system", "system_menu"),
            ("nav:system", "system_menu"),
            ("nav:network", "network_menu"),
            ("nav:analytics", "analytics_menu"),
            ("nav:backups", "backups_menu"),
            ("nav:ai_logs", "ai_logs_menu"),
        ],
    )
    def test_static_navigation_callback_returns_true(
        self,
        mock_bot,
        mock_call,
        callback_data,
        screen_id,
    ):
        """Тест: nav:* navigation callback обрабатывается единым handler."""
        navigation.start(111222, "main")

        result = handle_navigation_callback(
            mock_bot,
            111222,
            mock_call,
            callback_data,
        )

        assert result is True
        assert navigation.current(111222) == screen_id

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        """Тест: неизвестный data возвращает False"""
        result = handle_navigation_callback(
            mock_bot, 111222, mock_call, "unknown_action"
        )
        assert result is False


def test_safe_edit_returns_true_when_message_not_modified(mock_bot):
    mock_bot.edit_message_text.side_effect = RuntimeError("message is not modified")

    assert (
        _safe_edit(
            mock_bot,
            111222,
            67890,
            "text",
            "KB",
        )
        is True
    )

    mock_bot.send_message.assert_not_called()


def test_safe_edit_falls_back_to_send_message_when_message_not_found(
    mock_bot,
):
    mock_bot.edit_message_text.side_effect = RuntimeError("message to edit not found")

    assert (
        _safe_edit(
            mock_bot,
            111222,
            67890,
            "text",
            "KB",
        )
        is True
    )

    mock_bot.send_message.assert_called_once_with(
        chat_id=111222,
        text="text",
        parse_mode="Markdown",
        reply_markup="KB",
    )


def test_safe_edit_returns_false_when_fallback_send_fails(mock_bot):
    mock_bot.edit_message_text.side_effect = RuntimeError("message to edit not found")
    mock_bot.send_message.side_effect = RuntimeError("send failed")

    assert (
        _safe_edit(
            mock_bot,
            111222,
            67890,
            "text",
            "KB",
        )
        is False
    )


def test_safe_edit_returns_false_on_other_edit_error(mock_bot):
    mock_bot.edit_message_text.side_effect = RuntimeError("edit failed")

    assert (
        _safe_edit(
            mock_bot,
            111222,
            67890,
            "text",
            "KB",
        )
        is False
    )

    mock_bot.send_message.assert_not_called()


def test_render_navigation_screen_returns_true_on_success(mock_bot):
    with patch("handlers.admin.navigation.navigation.render") as render:
        assert (
            render_navigation_screen(
                mock_bot,
                111222,
                67890,
                "manage_menu",
            )
            is True
        )

    render.assert_called_once_with(
        "manage_menu",
        mock_bot,
        111222,
        67890,
    )


def test_render_navigation_screen_returns_false_on_renderer_error(mock_bot):
    with (
        patch(
            "handlers.admin.navigation.navigation.render",
            side_effect=RuntimeError("render failed"),
        ),
        patch("handlers.admin.navigation.logger.exception") as exception,
    ):
        assert (
            render_navigation_screen(
                mock_bot,
                111222,
                67890,
                "manage_menu",
            )
            is False
        )

    exception.assert_called_once()


def test_nav_back_deletes_input_request_message(mock_bot, mock_call):
    from core.state import INPUT_REQUEST_MSGS

    INPUT_REQUEST_MSGS[111222] = 55555

    with (
        patch("handlers.admin.navigation.safe_delete") as mock_delete,
        patch(
            "handlers.admin.navigation.render_navigation_screen",
            return_value=True,
        ),
    ):
        navigation.start(111222, "main")
        navigation.go(111222, "manage_menu")

        result = handle_navigation_callback(
            mock_bot,
            111222,
            mock_call,
            "nav:back",
        )

    assert result is True
    mock_delete.assert_called_once_with(mock_bot, 111222, 55555)
    assert 111222 not in INPUT_REQUEST_MSGS


def test_nav_back_without_history_starts_admin_home(mock_bot, mock_call):
    with (
        patch("handlers.admin.navigation.navigation.back", return_value=None),
        patch(
            "handlers.admin.navigation.render_navigation_screen",
            return_value=True,
        ),
    ):
        result = handle_navigation_callback(
            mock_bot,
            111222,
            mock_call,
            "nav:back",
        )

    assert result is True
    from handlers.admin.navigation import ADMIN_HOME

    assert navigation.current(111222) == ADMIN_HOME


def test_nav_home_without_history_starts_admin_home(mock_bot, mock_call):
    with (
        patch("handlers.admin.navigation.navigation.home", return_value=None),
        patch(
            "handlers.admin.navigation.render_navigation_screen",
            return_value=True,
        ),
    ):
        result = handle_navigation_callback(
            mock_bot,
            111222,
            mock_call,
            "nav:home",
        )

    assert result is True
    from handlers.admin.navigation import ADMIN_HOME

    assert navigation.current(111222) == ADMIN_HOME
