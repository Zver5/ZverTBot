"""
Тесты для handlers/features/ssh_keys.py
Проверяет callback'и SSH-ключей: menu, list, history, delete, export
"""

from unittest.mock import Mock, mock_open, patch

import pytest

from handlers.features.ssh_keys import (
    handle_ssh_callback,
)


@pytest.fixture
def mock_bot():
    bot = Mock()
    bot.edit_message_text = Mock()
    bot.send_message = Mock()
    bot.send_document = Mock()
    bot.answer_callback_query = Mock()
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
def reset_navigation():
    """Каждый тест SSH callback начинается с чистой истории навигации."""
    from handlers.features.ssh_keys import navigation

    navigation.clear(111222)
    yield
    navigation.clear(111222)


class TestHandleSSHCallback:
    """Тесты для handle_ssh_callback"""

    def test_ssh_menu_returns_true(self, mock_bot, mock_call):
        """Тест: data='ssh_menu' возвращает True"""
        with patch("handlers.features.ssh_keys.ssh_menu_kb", return_value=Mock()):
            result = handle_ssh_callback(mock_bot, 111222, mock_call, "ssh_menu")
            assert result.show_alert is False

    def test_ssh_menu_calls_edit_message(self, mock_bot, mock_call):
        """Тест: ssh_menu вызывает edit_message_text"""
        with patch("handlers.features.ssh_keys.ssh_menu_kb", return_value=Mock()):
            handle_ssh_callback(mock_bot, 111222, mock_call, "ssh_menu")
            mock_bot.edit_message_text.assert_called_once()

    def test_ssh_menu_returns_callback_response(self, mock_bot, mock_call):
        """Тест: ssh_menu возвращает CallbackResponse"""
        with patch("handlers.features.ssh_keys.ssh_menu_kb", return_value=Mock()):
            result = handle_ssh_callback(mock_bot, 111222, mock_call, "ssh_menu")

        assert result.text is None
        assert result.show_alert is False
        mock_bot.answer_callback_query.assert_not_called()

    def test_ssh_list_returns_true(self, mock_bot, mock_call):
        """Тест: data='ssh_list' возвращает True"""
        with patch(
            "handlers.features.ssh_keys.get_ssh_keys_list",
            return_value="🔑 Список ключей",
        ):
            result = handle_ssh_callback(mock_bot, 111222, mock_call, "ssh_list")
            assert result.text == "Загружаю список ключей..."
            assert result.show_alert is False

    def test_ssh_list_calls_get_keys(self, mock_bot, mock_call):
        """Тест: ssh_list вызывает get_ssh_keys_list"""
        with patch(
            "handlers.features.ssh_keys.get_ssh_keys_list", return_value="🔑 Список"
        ) as mock_get:
            handle_ssh_callback(mock_bot, 111222, mock_call, "ssh_list")
            mock_get.assert_called_once()

    def test_ssh_history_returns_true(self, mock_bot, mock_call):
        """Тест: data='ssh_history' возвращает True"""
        with patch(
            "handlers.features.ssh_keys.get_ssh_history", return_value="📋 История"
        ):
            result = handle_ssh_callback(mock_bot, 111222, mock_call, "ssh_history")
            assert result.text == "Загружаю историю..."
            assert result.show_alert is False

    def test_ssh_history_calls_get_history(self, mock_bot, mock_call):
        """Тест: ssh_history вызывает get_ssh_history"""
        with patch(
            "handlers.features.ssh_keys.get_ssh_history", return_value="📋 История"
        ) as mock_history:
            handle_ssh_callback(mock_bot, 111222, mock_call, "ssh_history")
            mock_history.assert_called_once_with(limit=10)

    def test_ssh_delete_returns_true(self, mock_bot, mock_call):
        """Тест: data='ssh_delete' возвращает True"""
        mock_result = Mock()
        mock_result.stdout = "256 SHA256:abc123 HA_Tunnel (ED25519)"
        with (
            patch(
                "handlers.features.ssh_keys.subprocess.run", return_value=mock_result
            ),
            patch("handlers.features.ssh_keys.SSH_KEY_MAP", {}),
        ):
            result = handle_ssh_callback(mock_bot, 111222, mock_call, "ssh_delete")
            assert result.show_alert is False

    def test_ssh_delete_calls_ssh_keygen(self, mock_bot, mock_call):
        """Тест: ssh_delete вызывает subprocess.run с ssh-keygen"""
        mock_result = Mock()
        mock_result.stdout = "256 SHA256:abc123 HA_Tunnel (ED25519)"
        with (
            patch(
                "handlers.features.ssh_keys.subprocess.run", return_value=mock_result
            ) as mock_run,
            patch("handlers.features.ssh_keys.SSH_KEY_MAP", {}),
        ):
            handle_ssh_callback(mock_bot, 111222, mock_call, "ssh_delete")
            mock_run.assert_called_once()
            assert "ssh-keygen" in str(mock_run.call_args)

    def test_ssh_delete_confirm_returns_true(self, mock_bot, mock_call):
        """Тест: data='ssh_delete_confirm_HA_Tunnel' возвращает True"""
        with patch(
            "handlers.features.ssh_keys.SSH_KEY_MAP",
            {"SHA256:abc": {"name": "HA_Tunnel", "emoji": "🔑", "desc": "Туннель"}},
        ):
            result = handle_ssh_callback(
                mock_bot, 111222, mock_call, "ssh_delete_confirm_HA_Tunnel"
            )
            assert result.show_alert is False

    def test_ssh_delete_confirm_calls_edit_message(self, mock_bot, mock_call):
        """Тест: ssh_delete_confirm_ вызывает edit_message_text"""
        with patch(
            "handlers.features.ssh_keys.SSH_KEY_MAP",
            {"SHA256:abc": {"name": "HA_Tunnel", "emoji": "🔑", "desc": "Туннель"}},
        ):
            handle_ssh_callback(
                mock_bot, 111222, mock_call, "ssh_delete_confirm_HA_Tunnel"
            )
            mock_bot.edit_message_text.assert_called_once()

    def test_ssh_delete_final_returns_true(self, mock_bot, mock_call):
        """Тест: data='ssh_delete_final_HA_Tunnel' возвращает True"""
        with patch(
            "handlers.features.ssh_keys.delete_ssh_key",
            return_value=(True, "✅ Ключ удалён"),
        ):
            result = handle_ssh_callback(
                mock_bot, 111222, mock_call, "ssh_delete_final_HA_Tunnel"
            )
            assert result.text == "Удаляю ключ..."
            assert result.show_alert is False

    def test_ssh_delete_final_calls_delete(self, mock_bot, mock_call):
        """Тест: ssh_delete_final_ вызывает delete_ssh_key"""
        with patch(
            "handlers.features.ssh_keys.delete_ssh_key",
            return_value=(True, "✅ Ключ удалён"),
        ) as mock_delete:
            handle_ssh_callback(
                mock_bot, 111222, mock_call, "ssh_delete_final_HA_Tunnel"
            )
            mock_delete.assert_called_once_with("HA_Tunnel")

    def test_ssh_delete_final_logs_action(self, mock_bot, mock_call):
        """Тест: ssh_delete_final_ вызывает log_action при успехе"""
        with (
            patch(
                "handlers.features.ssh_keys.delete_ssh_key",
                return_value=(True, "✅ Ключ удалён"),
            ),
            patch("handlers.features.ssh_keys.log_action") as mock_log,
        ):
            handle_ssh_callback(
                mock_bot, 111222, mock_call, "ssh_delete_final_HA_Tunnel"
            )
            mock_log.assert_called_once()

    def test_ssh_delete_final_no_log_on_failure(self, mock_bot, mock_call):
        """Тест: ssh_delete_final_ не вызывает log_action при ошибке"""
        with (
            patch(
                "handlers.features.ssh_keys.delete_ssh_key",
                return_value=(False, "❌ Ошибка"),
            ),
            patch("handlers.features.ssh_keys.log_action") as mock_log,
        ):
            handle_ssh_callback(
                mock_bot, 111222, mock_call, "ssh_delete_final_HA_Tunnel"
            )
            mock_log.assert_not_called()

    def test_ssh_export_returns_true(self, mock_bot, mock_call):
        """Тест: data='ssh_export' возвращает True"""
        with (
            patch(
                "handlers.features.ssh_keys.get_authorized_keys_path",
                return_value="/root/.ssh/authorized_keys",
            ),
            patch("handlers.features.ssh_keys.os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=b"ssh-ed25519 AAAA...")),
        ):
            result = handle_ssh_callback(mock_bot, 111222, mock_call, "ssh_export")
            assert result.text == "Отправляю файл..."
            assert result.show_alert is False

    def test_ssh_export_sends_document(self, mock_bot, mock_call):
        """Тест: ssh_export отправляет документ"""
        with (
            patch(
                "handlers.features.ssh_keys.get_authorized_keys_path",
                return_value="/root/.ssh/authorized_keys",
            ),
            patch("handlers.features.ssh_keys.os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=b"ssh-ed25519 AAAA...")),
        ):
            handle_ssh_callback(mock_bot, 111222, mock_call, "ssh_export")
            mock_bot.send_document.assert_called_once()

    def test_ssh_export_file_not_found(self, mock_bot, mock_call):
        """Тест: ssh_export с отсутствующим файлом"""
        with (
            patch(
                "handlers.features.ssh_keys.get_authorized_keys_path",
                return_value="/root/.ssh/authorized_keys",
            ),
            patch("handlers.features.ssh_keys.os.path.exists", return_value=False),
        ):
            result = handle_ssh_callback(mock_bot, 111222, mock_call, "ssh_export")
            assert result.text == "Отправляю файл..."
            assert result.show_alert is False
            mock_bot.edit_message_text.assert_called()

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        """Тест: неизвестный data возвращает False"""
        result = handle_ssh_callback(mock_bot, 111222, mock_call, "unknown_action")
        assert result is False


def test_ssh_delete_error_edits_error_message(mock_bot, mock_call):
    with patch(
        "handlers.features.ssh_keys.subprocess.run",
        side_effect=RuntimeError("ssh-keygen failed"),
    ):
        result = handle_ssh_callback(
            mock_bot,
            111222,
            mock_call,
            "ssh_delete",
        )

    assert result.show_alert is False
    mock_bot.edit_message_text.assert_called_once_with(
        "❌ Ошибка: ssh-keygen failed",
        111222,
        67890,
    )


def test_ssh_export_edit_error_is_handled(mock_bot, mock_call):
    mock_bot.edit_message_text.side_effect = RuntimeError("edit failed")

    with (
        patch(
            "handlers.features.ssh_keys.get_authorized_keys_path",
            return_value="/root/.ssh/authorized_keys",
        ),
        patch(
            "handlers.features.ssh_keys.os.path.exists",
            return_value=True,
        ),
        patch(
            "builtins.open",
            mock_open(read_data=b"ssh-ed25519 AAAA..."),
        ),
    ):
        result = handle_ssh_callback(
            mock_bot,
            111222,
            mock_call,
            "ssh_export",
        )

    assert result.show_alert is False


def test_handle_ssh_callback_unexpected_error_returns_false(
    mock_bot,
    mock_call,
):
    with patch(
        "handlers.features.ssh_keys.navigation.current",
        side_effect=RuntimeError("boom"),
    ):
        result = handle_ssh_callback(
            mock_bot,
            111222,
            mock_call,
            "ssh_menu",
        )

    assert result is False


def test_handle_ssh_callback_same_current_screen_returns_notice(
    mock_bot,
    mock_call,
):
    from handlers.features.ssh_keys import handle_ssh_callback

    with (
        patch(
            "handlers.features.ssh_keys.navigation.current",
            return_value="ssh_menu",
        ),
        patch("handlers.features.ssh_keys.navigation.go") as mock_go,
        patch("handlers.features.ssh_keys.navigation.render") as mock_render,
    ):
        result = handle_ssh_callback(
            mock_bot,
            111222,
            mock_call,
            "ssh_menu",
        )

    assert result.show_alert is False
    mock_go.assert_not_called()
    mock_render.assert_not_called()


def test_ssh_export_navigation_error_is_logged(mock_bot, mock_call):
    with (
        patch(
            "handlers.features.ssh_keys.get_authorized_keys_path",
            return_value="/root/.ssh/authorized_keys",
        ),
        patch("handlers.features.ssh_keys.os.path.exists", return_value=True),
        patch(
            "builtins.open",
            mock_open(read_data=b"ssh-ed25519 AAAA..."),
        ),
        patch(
            "handlers.features.ssh_keys.navigation.go",
            side_effect=RuntimeError("navigation failed"),
        ),
        patch("handlers.features.ssh_keys.logger.error") as mock_error,
    ):
        result = handle_ssh_callback(
            mock_bot,
            111222,
            mock_call,
            "ssh_export",
        )

    assert result.show_alert is False
    mock_error.assert_called_once()
    assert mock_error.call_args.args[0] == ("ssh.handler.navigation_failed | error=%s")
    assert str(mock_error.call_args.args[1]) == "navigation failed"


def test_ssh_delete_no_keys_edits_message(mock_bot, mock_call):
    mock_result = Mock()
    mock_result.stdout = ""

    with (
        patch(
            "handlers.features.ssh_keys.subprocess.run",
            return_value=mock_result,
        ),
        patch(
            "handlers.features.ssh_keys.safe_edit_message",
            return_value=True,
        ) as mock_edit,
    ):
        result = handle_ssh_callback(
            mock_bot,
            111222,
            mock_call,
            "ssh_delete",
        )

    assert result.show_alert is False
    mock_edit.assert_called_once()
    assert mock_edit.call_args.args[0] is mock_bot
    assert mock_edit.call_args.args[1] == "🔑 SSH-ключи для удаления не найдены."
    assert mock_edit.call_args.args[2:] == (111222, 67890)
