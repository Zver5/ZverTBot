"""
Тесты для handlers/admin/bindings.py
Проверяет callback'и привязок: approve_bind_, reject_bind_, unbind_*,
bindings_menu/pending/active
"""

from unittest.mock import Mock, patch

import pytest

from handlers.admin.bindings import (
    handle_bind_existing_callback,
    handle_bindings_part1_callback,
    handle_bindings_part2_callback,
    handle_bindings_part3_callback,
    render_bindings_active,
    render_bindings_menu,
    render_bindings_pending,
)


@pytest.fixture
def mock_bot():
    """Фикстура: мок бота"""
    bot = Mock()
    bot.edit_message_text = Mock()
    bot.send_message = Mock()
    bot.answer_callback_query = Mock()
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


class TestHandleBindingsPart1Callback:
    """Тесты для handle_bindings_part1_callback.

    Проверяет approve_bind_, reject_bind_ и do_bind_.
    """

    def test_approve_bind_returns_true(self, mock_bot, mock_call):
        """Тест: data='approve_bind_123' возвращает True"""
        with (
            patch(
                "handlers.admin.bindings.get_pending_bindings",
                return_value={"123": {"name": "Test", "time": "2026-07-08"}},
            ),
            patch("handlers.admin.bindings.get_users_list", return_value=["client1"]),
            patch("handlers.admin.bindings.get_all_client_bindings", return_value={}),
        ):
            result = handle_bindings_part1_callback(
                mock_bot, 111222, mock_call, "approve_bind_123"
            )
            assert result.text is None
            assert result.show_alert is False

    def test_approve_bind_calls_edit_message(self, mock_bot, mock_call):
        """Тест: approve_bind_ вызывает edit_message_text"""
        with (
            patch(
                "handlers.admin.bindings.get_pending_bindings",
                return_value={"123": {"name": "Test", "time": "2026-07-08"}},
            ),
            patch("handlers.admin.bindings.get_users_list", return_value=["client1"]),
            patch("handlers.admin.bindings.get_all_client_bindings", return_value={}),
        ):
            handle_bindings_part1_callback(
                mock_bot, 111222, mock_call, "approve_bind_123"
            )
            mock_bot.edit_message_text.assert_called_once()

    def test_approve_bind_missing_pending_returns_response(self, mock_bot, mock_call):
        """Тест: approve_bind_ с отсутствующей заявкой возвращает CallbackResponse."""
        with patch("handlers.admin.bindings.get_pending_bindings", return_value={}):
            result = handle_bindings_part1_callback(
                mock_bot, 111222, mock_call, "approve_bind_999"
            )
            assert result.text == "Заявка уже обработана или удалена."
            assert result.show_alert is False

    def test_reject_bind_returns_response(self, mock_bot, mock_call):
        """Тест: reject_bind_123 возвращает CallbackResponse."""
        with (
            patch(
                "handlers.admin.bindings.get_pending_bindings",
                return_value={"123": {"name": "Test"}},
            ),
            patch("handlers.admin.bindings.remove_pending_binding"),
            patch("handlers.admin.bindings.render_bindings_pending"),
        ):
            result = handle_bindings_part1_callback(
                mock_bot, 111222, mock_call, "reject_bind_123"
            )
            assert result.text == "Заявка отклонена."
            assert result.show_alert is False

    def test_reject_bind_calls_save(self, mock_bot, mock_call):
        """Тест: reject_bind_ вызывает save_pending_bindings"""
        with (
            patch(
                "handlers.admin.bindings.get_pending_bindings",
                return_value={"123": {"name": "Test"}},
            ),
            patch("handlers.admin.bindings.remove_pending_binding") as mock_remove,
            patch("handlers.admin.bindings.render_bindings_pending"),
        ):
            handle_bindings_part1_callback(
                mock_bot, 111222, mock_call, "reject_bind_123"
            )
            mock_remove.assert_called_once_with("123")

    def test_reject_bind_missing_pending_returns_empty_callback_response(
        self, mock_bot, mock_call
    ):
        """Отклонение отсутствующей заявки возвращает пустой CallbackResponse."""
        with patch(
            "handlers.admin.bindings.get_pending_bindings",
            return_value={},
        ):
            result = handle_bindings_part1_callback(
                mock_bot, 111222, mock_call, "reject_bind_999"
            )

        assert result.text is None

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        """Тест: неизвестный data возвращает False"""
        result = handle_bindings_part1_callback(
            mock_bot, 111222, mock_call, "unknown_action"
        )
        assert result is False

    def test_do_bind_success_returns_true_and_adds_binding(self, mock_bot, mock_call):
        """Тест: успешный do_bind_ вызывает add_client_binding."""
        with (
            patch(
                "handlers.admin.bindings.add_client_binding",
                return_value="added",
            ) as mock_add,
            patch(
                "handlers.admin.bindings.get_all_client_bindings",
                return_value={"123": ["client1"]},
            ),
            patch(
                "handlers.admin.bindings.remove_pending_binding",
            ) as mock_remove_pending,
            patch(
                "handlers.admin.bindings.get_users_list",
                side_effect=[["client1", "client2"], ["client1", "client2"]],
            ),
        ):
            result = handle_bindings_part1_callback(
                mock_bot,
                111222,
                mock_call,
                "do_bind_123_client1",
            )

        assert result.text == "✅ client1 добавлен!"
        mock_add.assert_called_once_with("123", "client1")
        mock_remove_pending.assert_called_once_with("123")

    def test_do_bind_duplicate_returns_true(self, mock_bot, mock_call):
        """Тест: duplicate при do_bind_ обрабатывается без продолжения."""
        with patch(
            "handlers.admin.bindings.add_client_binding",
            return_value="duplicate",
        ) as mock_add:
            result = handle_bindings_part1_callback(
                mock_bot,
                111222,
                mock_call,
                "do_bind_123_client1",
            )

        assert result.text == "Уже привязан!"
        mock_add.assert_called_once_with("123", "client1")

    def test_do_bind_limit_returns_true(self, mock_bot, mock_call):
        """Тест: limit при do_bind_ обрабатывается без продолжения."""
        with patch(
            "handlers.admin.bindings.add_client_binding",
            return_value="limit",
        ) as mock_add:
            result = handle_bindings_part1_callback(
                mock_bot,
                111222,
                mock_call,
                "do_bind_123_client1",
            )

        assert result.text == "Лимит: 4 аккаунта на чат!"
        mock_add.assert_called_once_with("123", "client1")


class TestHandleBindExistingCallback:
    """Тесты для handle_bind_existing_callback (bind_existing_)."""

    def test_bind_existing_returns_response_and_shows_unbound_clients(
        self, mock_bot, mock_call
    ):
        """Тест: bind_existing_ открывает выбор непривязанного клиента."""
        with (
            patch(
                "handlers.admin.bindings.get_all_client_bindings",
                return_value={"123": ["client1"]},
            ),
            patch(
                "handlers.admin.bindings.get_users_list",
                side_effect=[["client1", "client2"], ["client1", "client3"]],
            ),
        ):
            result = handle_bind_existing_callback(
                mock_bot,
                111222,
                mock_call,
                "bind_existing_123",
            )

        assert result.text is None
        assert result.show_alert is False
        mock_bot.edit_message_text.assert_called_once()

        _, kwargs = mock_bot.edit_message_text.call_args
        keyboard = kwargs["reply_markup"]

        callbacks = [
            button.callback_data for row in keyboard.keyboard for button in row
        ]

        assert "do_bind_123_client2" in callbacks
        assert "do_bind_123_client3" in callbacks
        assert "nav:back" in callbacks

    def test_bind_existing_limit_returns_response(self, mock_bot, mock_call):
        """Тест: bind_existing_ не позволяет превысить лимит."""
        with patch(
            "handlers.admin.bindings.get_all_client_bindings",
            return_value={"123": ["c1", "c2", "c3", "c4"]},
        ):
            result = handle_bind_existing_callback(
                mock_bot,
                111222,
                mock_call,
                "bind_existing_123",
            )

        assert result.text == "Лимит: 4 аккаунта на чат!"
        assert result.show_alert is False

    def test_bind_existing_unknown_data_returns_false(self, mock_bot, mock_call):
        """Тест: bind_existing_ игнорирует чужой callback."""
        result = handle_bind_existing_callback(
            mock_bot,
            111222,
            mock_call,
            "unknown_action",
        )

        assert result is False


class TestHandleBindingsPart2Callback:
    """Тесты для handle_bindings_part2_callback.

    Проверяет bindings_menu, bindings_pending, bindings_active.
    """

    def test_bindings_menu_returns_response(self, mock_bot, mock_call):
        """Тест: bindings_menu возвращает CallbackResponse."""
        with patch("handlers.admin.bindings.get_pending_bindings", return_value={}):
            result = handle_bindings_part2_callback(
                mock_bot, 111222, mock_call, "bindings_menu"
            )
            assert result.text is None
            assert result.show_alert is False

    def test_bindings_menu_calls_edit_message(self, mock_bot, mock_call):
        """Тест: bindings_menu обновляет текущее сообщение"""
        with patch("handlers.admin.bindings.get_pending_bindings", return_value={}):
            handle_bindings_part2_callback(mock_bot, 111222, mock_call, "bindings_menu")
            mock_bot.edit_message_text.assert_called_once()

    def test_bindings_menu_shows_active_count(self, mock_bot):
        """Тест: меню показывает общее количество активных привязок."""
        with (
            patch(
                "handlers.admin.bindings.get_all_client_bindings",
                return_value={
                    "111": ["client1", "client2"],
                    "222": "client3",
                    "333": [],
                },
            ),
            patch("handlers.admin.bindings.get_pending_bindings", return_value={}),
        ):
            result = render_bindings_menu(mock_bot, 111222, 67890)

        assert result is True

        reply_markup = mock_bot.edit_message_text.call_args.kwargs["reply_markup"]
        buttons = [button for row in reply_markup.keyboard for button in row]

        assert any(button.text == "✅ Активные (3)" for button in buttons)
        assert any(button.text == "⏳ Ожидающие (0)" for button in buttons)

    def test_bindings_pending_returns_true(self, mock_bot, mock_call):
        """Тест: data='bindings_pending' возвращает True"""
        with (
            patch(
                "handlers.admin.bindings.get_pending_bindings",
                return_value={"123": {"name": "Test", "time": "2026-07-08"}},
            ),
            patch("handlers.admin.bindings.get_all_client_bindings", return_value={}),
        ):
            result = handle_bindings_part2_callback(
                mock_bot, 111222, mock_call, "bindings_pending"
            )
            assert result is not False

    def test_bindings_pending_empty_returns_response(self, mock_bot, mock_call):
        """Тест: bindings_pending с пустым списком возвращает CallbackResponse."""
        with patch("handlers.admin.bindings.get_pending_bindings", return_value={}):
            result = handle_bindings_part2_callback(
                mock_bot, 111222, mock_call, "bindings_pending"
            )
            assert result.text is None
            assert result.show_alert is False
            mock_bot.edit_message_text.assert_called_once()

    def test_bindings_active_returns_response(self, mock_bot, mock_call):
        """Тест: bindings_active возвращает CallbackResponse."""
        with patch(
            "handlers.admin.bindings.get_all_client_bindings",
            return_value={"123": ["client1"]},
        ):
            result = handle_bindings_part2_callback(
                mock_bot, 111222, mock_call, "bindings_active"
            )
            assert result.text is None
            assert result.show_alert is False

    def test_bindings_active_empty_returns_response(self, mock_bot, mock_call):
        """Тест: bindings_active с пустым списком возвращает CallbackResponse."""
        with patch("handlers.admin.bindings.get_all_client_bindings", return_value={}):
            result = handle_bindings_part2_callback(
                mock_bot, 111222, mock_call, "bindings_active"
            )
            assert result is not False
            mock_bot.edit_message_text.assert_called_once()

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        """Тест: неизвестный data возвращает False"""
        result = handle_bindings_part2_callback(
            mock_bot, 111222, mock_call, "unknown_menu"
        )
        assert result is False


class TestHandleBindingsPart3Callback:
    """Тесты для handle_bindings_part3_callback (unbind_select_, unbind_confirm_)"""

    def test_unbind_confirm_failure_returns_true(self, mock_bot, mock_call):
        """Тест: несуществующая привязка корректно обрабатывается."""
        with patch(
            "handlers.admin.bindings.remove_client_binding",
            return_value=False,
        ) as mock_remove:
            result = handle_bindings_part3_callback(
                mock_bot,
                111222,
                mock_call,
                "unbind_confirm_123_client1",
            )

        assert result is not False
        mock_remove.assert_called_once_with("123", "client1")
        assert result.text == "Клиент не найден в привязках"
        assert result.show_alert is False

    def test_unbind_confirm_success_returns_response_and_sends_notification(
        self, mock_bot, mock_call
    ):
        """Тест: успешная отвязка возвращает CallbackResponse и уведомляет пользователя.
        """
        with (
            patch(
                "handlers.admin.bindings.remove_client_binding",
                return_value=True,
            ) as mock_remove,
            patch(
                "handlers.admin.bindings.get_client_bindings",
                return_value=[],
            ),
        ):
            result = handle_bindings_part3_callback(
                mock_bot,
                111222,
                mock_call,
                "unbind_confirm_123_client1",
            )

        assert result.text == "✅ client1 отвязан!"
        assert result.show_alert is False
        mock_remove.assert_called_once_with("123", "client1")
        mock_bot.send_message.assert_called_once_with(
            "123",
            "❌ Ваш аккаунт `client1` отвязан администратором.",
            parse_mode="Markdown",
        )

    def test_unbind_select_returns_response(self, mock_bot, mock_call):
        """Тест: unbind_select_123 возвращает CallbackResponse."""
        with patch(
            "handlers.admin.bindings.get_client_bindings",
            return_value=["client1"],
        ):
            result = handle_bindings_part3_callback(
                mock_bot, 111222, mock_call, "unbind_select_123"
            )
            assert result.text is None
            assert result.show_alert is False

    def test_unbind_select_calls_edit_message(self, mock_bot, mock_call):
        """Тест: unbind_select_ обновляет текущее сообщение"""
        with patch(
            "handlers.admin.bindings.get_client_bindings",
            return_value=["client1"],
        ):
            handle_bindings_part3_callback(
                mock_bot, 111222, mock_call, "unbind_select_123"
            )
            mock_bot.send_message.assert_called_once()

    def test_unbind_select_empty_returns_response(self, mock_bot, mock_call):
        """Тест: unbind_select_ с пустым списком возвращает сообщение об ошибке."""
        with patch("handlers.admin.bindings.get_client_bindings", return_value=[]):
            result = handle_bindings_part3_callback(
                mock_bot, 111222, mock_call, "unbind_select_123"
            )
            assert result.text == "Нет привязанных клиентов"
            assert result.show_alert is False

    def test_unbind_confirm_returns_response(self, mock_bot, mock_call):
        """Тест: unbind_confirm_123_client1 возвращает CallbackResponse."""
        with (
            patch(
                "handlers.admin.bindings.get_all_client_bindings",
                return_value={"123": ["client1"]},
            ),
            patch("handlers.admin.bindings.remove_client_binding", return_value=True),
        ):
            result = handle_bindings_part3_callback(
                mock_bot, 111222, mock_call, "unbind_confirm_123_client1"
            )
            assert result.text == "✅ client1 отвязан!"
            assert result.show_alert is False

    def test_unbind_confirm_calls_remove(self, mock_bot, mock_call):
        """Тест: unbind_confirm_ вызывает remove_client_binding"""
        with (
            patch(
                "handlers.admin.bindings.get_all_client_bindings",
                return_value={"123": ["client1"]},
            ),
            patch(
                "handlers.admin.bindings.remove_client_binding",
                return_value=True,
            ) as mock_remove,
        ):
            handle_bindings_part3_callback(
                mock_bot, 111222, mock_call, "unbind_confirm_123_client1"
            )
            mock_remove.assert_called_once_with("123", "client1")

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        """Тест: неизвестный data возвращает False"""
        result = handle_bindings_part3_callback(
            mock_bot, 111222, mock_call, "unknown_action"
        )
        assert result is False


class TestBindingsMarkdownEscaping:
    def test_pending_renderer_escapes_dynamic_fields(self, mock_bot):
        with (
            patch(
                "handlers.admin.bindings.get_pending_bindings",
                return_value={
                    "123": {
                        "name": "user_test",
                        "time": "2026-08-25 12:34_test",
                    }
                },
            ),
            patch(
                "handlers.admin.bindings.get_all_client_bindings",
                return_value={"123": ["client_one", "client.two"]},
            ),
        ):
            result = render_bindings_pending(
                mock_bot,
                111222,
                67890,
            )

        assert result is True
        text = mock_bot.edit_message_text.call_args.args[0]
        assert "user\\_test" in text
        assert "client\\_one, client.two" in text
        assert "2026-08-25 12:34\\_test" in text

    def test_bind_notification_escapes_username(self, mock_bot, mock_call):
        with (
            patch(
                "handlers.admin.bindings.get_all_client_bindings",
                return_value={},
            ),
            patch(
                "handlers.admin.bindings.get_users_list",
                return_value=["client_test"],
            ),
            patch(
                "handlers.admin.bindings.add_client_binding",
                return_value="success",
            ),
            patch(
                "handlers.admin.bindings.remove_pending_binding",
            ),
        ):
            result = handle_bindings_part1_callback(
                mock_bot,
                111222,
                mock_call,
                "do_bind_123_client_test",
            )

        assert result.text == "✅ client_test добавлен!"
        assert result.show_alert is False
        mock_bot.send_message.assert_called_once_with(
            "123",
            "✅ Аккаунт `client\\_test` успешно привязан!",
            parse_mode="Markdown",
        )

    def test_unbind_notification_escapes_username(self, mock_bot, mock_call):
        with (
            patch(
                "handlers.admin.bindings.remove_client_binding",
                return_value=True,
            ),
            patch(
                "handlers.admin.bindings.get_client_bindings",
                return_value=[],
            ),
        ):
            result = handle_bindings_part3_callback(
                mock_bot,
                111222,
                mock_call,
                "unbind_confirm_123_client_test",
            )

        assert result is not False
        mock_bot.send_message.assert_called_once_with(
            "123",
            "❌ Ваш аккаунт `client\\_test` отвязан администратором.",
            parse_mode="Markdown",
        )


class TestBindingsRendererErrors:
    def test_bindings_menu_renderer_error(self, mock_bot):
        with patch(
            "handlers.admin.bindings.get_pending_bindings",
            return_value={},
        ):
            mock_bot.edit_message_text.side_effect = RuntimeError("render failed")
            result = render_bindings_menu(
                mock_bot,
                111222,
                67890,
            )

        assert result is False

    def test_bindings_active_renderer_error(self, mock_bot):
        with patch(
            "handlers.admin.bindings.get_all_client_bindings",
            return_value={},
        ):
            mock_bot.edit_message_text.side_effect = RuntimeError("render failed")
            result = render_bindings_active(
                mock_bot,
                111222,
                67890,
            )

        assert result is False

    def test_bindings_pending_renderer_error(self, mock_bot):
        with patch(
            "handlers.admin.bindings.get_pending_bindings",
            return_value={},
        ):
            mock_bot.edit_message_text.side_effect = RuntimeError("render failed")
            result = render_bindings_pending(
                mock_bot,
                111222,
                67890,
            )

        assert result is False


class TestBindingsNoUnboundClients:
    def test_approve_bind_without_unbound_clients_returns_response(
        self,
        mock_bot,
        mock_call,
    ):
        with (
            patch(
                "handlers.admin.bindings.get_pending_bindings",
                return_value={"123": {"name": "Test"}},
            ),
            patch(
                "handlers.admin.bindings.get_all_client_bindings",
                return_value={},
            ),
            patch(
                "handlers.admin.bindings.get_users_list",
                return_value=[],
            ),
        ):
            result = handle_bindings_part1_callback(
                mock_bot,
                111222,
                mock_call,
                "approve_bind_123",
            )

        assert result.text == "Нет непривязанных клиентов!"
        assert result.show_alert is False

    def test_do_bind_without_unbound_clients(
        self,
        mock_bot,
        mock_call,
    ):
        with (
            patch(
                "handlers.admin.bindings.get_all_client_bindings",
                return_value={},
            ),
            patch(
                "handlers.admin.bindings.get_users_list",
                return_value=[],
            ),
        ):
            result = handle_bind_existing_callback(
                mock_bot,
                111222,
                mock_call,
                "bind_existing_123",
            )

        assert result.text == "Нет непривязанных клиентов!"
        assert result.show_alert is False


class TestBindingsNotificationErrors:
    def test_do_bind_send_message_error(
        self,
        mock_bot,
        mock_call,
    ):
        mock_bot.send_message.side_effect = RuntimeError("send failed")

        with (
            patch(
                "handlers.admin.bindings.get_all_client_bindings",
                return_value={},
            ),
            patch(
                "handlers.admin.bindings.get_users_list",
                return_value=["client1"],
            ),
            patch(
                "handlers.admin.bindings.add_client_binding",
            ),
        ):
            result = handle_bindings_part1_callback(
                mock_bot,
                111222,
                mock_call,
                "do_bind_123_client1",
            )

        assert result.text == "✅ client1 добавлен!"
        assert result.show_alert is False

    def test_reject_bind_send_message_error(
        self,
        mock_bot,
        mock_call,
    ):
        mock_bot.send_message.side_effect = RuntimeError("send failed")

        with (
            patch(
                "handlers.admin.bindings.get_pending_bindings",
                return_value={"123": {"name": "Test"}},
            ),
            patch(
                "handlers.admin.bindings.remove_pending_binding",
            ),
            patch("handlers.admin.bindings.render_bindings_pending"),
        ):
            result = handle_bindings_part1_callback(
                mock_bot,
                111222,
                mock_call,
                "reject_bind_123",
            )

        assert result.text == "Заявка отклонена."
        assert result.show_alert is False


class TestBindingsUnbindNotificationError:
    def test_unbind_notification_error(self, mock_bot, mock_call):
        with (
            patch(
                "handlers.admin.bindings.get_all_client_bindings",
                return_value={"111222": ["client1"]},
            ),
            patch(
                "handlers.admin.bindings.remove_client_binding",
                return_value=True,
            ),
            patch(
                "handlers.admin.bindings.get_client_bindings",
                return_value=["client1"],
            ),
            patch(
                "handlers.admin.bindings.safe_delete",
            ),
            patch(
                "handlers.admin.bindings.safe_send_message",
                return_value=False,
            ) as mock_safe_send,
        ):
            result = handle_bindings_part3_callback(
                mock_bot,
                111222,
                mock_call,
                "unbind_confirm_111222_client1",
            )

        assert result is not False
        mock_safe_send.assert_called_once_with(
            mock_bot,
            "111222",
            "❌ Ваш аккаунт `client1` отвязан администратором.",
            parse_mode="Markdown",
        )
