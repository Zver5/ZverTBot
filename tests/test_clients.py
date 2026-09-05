"""
Тесты для handlers/admin/clients.py
"""

from unittest.mock import Mock, patch

import pytest

from handlers.admin.clients import (
    handle_create_client_callback,
    handle_lists_delete_callback,
    handle_search_callback,
    process_rename_menu,
    process_search_input,
)


@pytest.fixture
def mock_bot():
    bot = Mock()
    bot.edit_message_text = Mock()
    bot.send_message = Mock()
    bot.answer_callback_query = Mock()
    bot.send_photo = Mock()
    bot.register_next_step_handler = Mock()
    bot.reply_to = Mock()
    bot.clear_step_handler_by_chat_id = Mock()
    return bot


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
    message.text = "test"
    return message


class TestHandleListsDeleteCallback:
    """Тесты для handle_lists_delete_callback"""

    def test_ask_del_returns_true(self, mock_bot, mock_call):
        result = handle_lists_delete_callback(
            mock_bot, 111222, mock_call, "ask_del:vless:client1"
        )
        assert result.text is None
        assert result.show_alert is False

    def test_confirm_del_returns_true(self, mock_bot, mock_call):
        with (
            patch("handlers.admin.clients.delete_client_service") as delete_client,
            patch("handlers.admin.clients.get_users_list", return_value=[]),
            patch("handlers.admin.clients.os.path.exists", return_value=True),
            patch("handlers.admin.clients.os.remove"),
            patch("handlers.admin.clients.log_action"),
        ):
            result = handle_lists_delete_callback(
                mock_bot, 111222, mock_call, "confirm_del:vless:client1"
            )
            assert result.text == "⏳ Удаляю..."
            assert result.show_alert is False
            delete_client.assert_called_once_with("client1", "vless")

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        result = handle_lists_delete_callback(
            mock_bot, 111222, mock_call, "unknown_action"
        )
        assert result is False


class TestHandleSearchCallback:
    """Тесты для handle_search_callback"""

    def test_search_vless_returns_true(self, mock_bot, mock_call):
        result = handle_search_callback(
            mock_bot, 111222, mock_call, "nav:clients_search_vless"
        )
        assert result.text is None
        assert result.show_alert is False

    def test_search_awg_returns_true(self, mock_bot, mock_call):
        result = handle_search_callback(
            mock_bot, 111222, mock_call, "nav:clients_search_awg"
        )
        assert result.text is None
        assert result.show_alert is False

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        result = handle_search_callback(mock_bot, 111222, mock_call, "unknown_action")
        assert result is False


class TestHandleCreateClientCallback:
    """Тесты для handle_create_client_callback"""

    def test_add_vless_returns_true(self, mock_bot, mock_call):
        result = handle_create_client_callback(mock_bot, 111222, mock_call, "add_vless")
        assert result.text is None
        assert result.show_alert is False

    def test_add_awg_returns_true(self, mock_bot, mock_call):
        result = handle_create_client_callback(mock_bot, 111222, mock_call, "add_awg")
        assert result.text is None
        assert result.show_alert is False

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        result = handle_create_client_callback(
            mock_bot, 111222, mock_call, "unknown_action"
        )
        assert result is False


class TestProcessSearchInput:
    """Тесты для process_search_input"""

    def test_process_search_with_results(self, mock_message):
        mock_message.text = "client"
        with (
            patch("handlers.admin.clients.bot") as mock_bot,
            patch("handlers.admin.clients.is_admin", return_value=True),
            patch(
                "handlers.admin.clients.get_users_list",
                return_value=["client1", "client2", "other"],
            ),
            patch("handlers.admin.clients.safe_delete"),
            patch("handlers.admin.clients.INPUT_REQUEST_MSGS", {}),
        ):
            process_search_input(mock_message, "vless")
            mock_bot.send_message.assert_called_once()

    def test_process_search_no_results(self, mock_message):
        mock_message.text = "nonexistent"
        with (
            patch("handlers.admin.clients.bot") as mock_bot,
            patch("handlers.admin.clients.is_admin", return_value=True),
            patch(
                "handlers.admin.clients.get_users_list",
                return_value=["client1", "client2"],
            ),
            patch("handlers.admin.clients.safe_delete"),
            patch("handlers.admin.clients.INPUT_REQUEST_MSGS", {}),
        ):
            process_search_input(mock_message, "vless")
            mock_bot.send_message.assert_called_once()

    def test_process_search_not_admin(self, mock_message):
        with patch("handlers.admin.clients.is_admin", return_value=False):
            process_search_input(mock_message, "vless")


class TestProcessRenameMenu:
    """Тесты для process_rename_menu"""

    def test_rename_valid_names(self, mock_message):
        mock_message.text = "old_name new_name"
        with (
            patch("handlers.admin.clients.bot") as mock_bot,
            patch("handlers.admin.clients.is_admin", return_value=True),
            patch("handlers.admin.clients.validate_username", return_value=True),
            patch("handlers.admin.clients.get_users_list", return_value=["old_name"]),
            patch("handlers.admin.clients.rename_client", return_value=[]),
            patch("handlers.admin.clients.log_action"),
            patch("handlers.admin.clients.safe_delete"),
            patch("handlers.admin.clients.INPUT_REQUEST_MSGS", {}),
        ):
            process_rename_menu(mock_message)
            mock_bot.reply_to.assert_not_called()

            # Без input_message_id SUCCESS отправляется fallback-сообщением.
            assert mock_bot.send_message.call_count == 2
            assert "Переименовываю" in mock_bot.send_message.call_args_list[0][0][1]

            menu_message = mock_bot.send_message.call_args_list[1][0][1]
            assert menu_message == "👥 *Клиенты*"

    def test_rename_invalid_format(self, mock_message):
        mock_message.text = "only_one_name"
        with (
            patch("handlers.admin.clients.bot") as mock_bot,
            patch("handlers.admin.clients.is_admin", return_value=True),
            patch("handlers.admin.clients.safe_delete"),
            patch("handlers.admin.clients.INPUT_REQUEST_MSGS", {}),
        ):
            process_rename_menu(mock_message)
            mock_bot.reply_to.assert_called_once()

    def test_rename_not_admin(self, mock_message):
        with patch("handlers.admin.clients.is_admin", return_value=False):
            process_rename_menu(mock_message)
