"""
Тесты для handlers/client/tickets.py
Проверяет клиентскую часть системы тикетов: создание, ответы, обработку описаний.
"""

from unittest.mock import Mock, patch

import pytest

from handlers.client.tickets import (
    _ticket_drafts,
    handle_create_ticket,
    handle_ticket_reply,
    handle_ticket_reply_cancel,
    process_ticket_description,
    process_ticket_reply,
)


@pytest.fixture
def mock_bot():
    bot = Mock()
    bot.edit_message_text = Mock()
    bot.send_message = Mock()
    bot.answer_callback_query = Mock()
    bot.edit_message_reply_markup = Mock()
    bot.register_next_step_handler = Mock()
    bot.clear_step_handler_by_chat_id = Mock()
    return bot


@pytest.fixture
def mock_call():
    call = Mock()
    call.id = "12345"
    call.message = Mock()
    call.message.message_id = 67890
    call.message.chat.id = 111222
    call.from_user = Mock()
    call.from_user.username = "testuser"
    return call


class TestHandleCreateTicket:
    """Тесты для handle_create_ticket"""

    def test_ticket_cancel(self, mock_bot, mock_call):
        """Тест: отмена создания тикета"""
        result = handle_create_ticket(mock_bot, 111222, mock_call, "ticket_cancel")
        assert result.text == "Создание тикета отменено."
        assert result.show_alert is False
        mock_bot.answer_callback_query.assert_not_called()
        mock_bot.edit_message_text.assert_called_once()
        mock_bot.clear_step_handler_by_chat_id.assert_called_once()

    def test_not_bound_to_account(self, mock_bot, mock_call):
        """Тест: пользователь не привязан к аккаунту"""
        with patch("handlers.client.tickets.get_client_bindings", return_value=[]):
            result = handle_create_ticket(mock_bot, 111222, mock_call, "create_ticket")
            assert result.text == "⚠️ Вы не привязаны к аккаунту!"
            assert result.show_alert is False

    def test_active_ticket_exists(self, mock_bot, mock_call):
        """Тест: у пользователя уже есть активный тикет"""
        with (
            patch(
                "handlers.client.tickets.get_client_bindings",
                return_value=["user1"],
            ),
            patch(
                "handlers.client.tickets.ticket_service.get_client_active_ticket",
                return_value=("abc123", {"chat_id": 111222, "status": "open"}),
            ),
        ):
            result = handle_create_ticket(mock_bot, 111222, mock_call, "create_ticket")
            assert result.text == "У вас уже есть активный тикет #abc123."
            assert result.show_alert is True

    def test_select_topic_internet(self, mock_bot, mock_call):
        """Тест: выбор темы 'Не работает интернет'"""
        prompt = Mock()
        prompt.message_id = 54321

        mock_bot.send_message.return_value = prompt

        with (
            patch(
                "handlers.client.tickets.get_client_bindings",
                return_value=["user1"],
            ),
            patch(
                "handlers.client.tickets.ticket_service.get_client_active_ticket",
                return_value=None,
            ),
        ):
            result = handle_create_ticket(
                mock_bot, 111222, mock_call, "ticket_topic_internet"
            )
            assert result.text is None
            assert result.show_alert is False
            mock_bot.answer_callback_query.assert_not_called()
            mock_bot.send_message.assert_not_called()
            mock_bot.edit_message_text.assert_called_once()

            edited_text = mock_bot.edit_message_text.call_args[0][0]
            assert "Создание тикета" in edited_text
            assert "Не работает интернет" in edited_text
            assert "Опишите вашу проблему одним сообщением" in edited_text

            from handlers.client.tickets import _ticket_drafts

            assert _ticket_drafts[111222]["topic"] == "Не работает интернет"
            assert _ticket_drafts[111222]["prompt_message_id"] == 67890

            mock_bot.register_next_step_handler.assert_called_once_with(
                mock_call.message,
                process_ticket_description,
            )

    def test_select_topic_vpn(self, mock_bot, mock_call):
        """Тест: выбор темы 'Не подключается VPN'"""
        from handlers.client.tickets import _ticket_drafts

        _ticket_drafts.pop(111222, None)

        with (
            patch(
                "handlers.client.tickets.get_client_bindings",
                return_value=["user1"],
            ),
            patch(
                "handlers.client.tickets.ticket_service.get_client_active_ticket",
                return_value=None,
            ),
        ):
            result = handle_create_ticket(
                mock_bot, 111222, mock_call, "ticket_topic_vpn"
            )

        assert result.text is None
        assert result.show_alert is False
        mock_bot.send_message.assert_not_called()
        mock_bot.edit_message_text.assert_called_once()

        edited_text = mock_bot.edit_message_text.call_args[0][0]
        assert "Создание тикета" in edited_text
        assert "Не подключается VPN" in edited_text
        assert "Опишите вашу проблему одним сообщением" in edited_text

        assert _ticket_drafts[111222]["topic"] == "Не подключается VPN"
        assert _ticket_drafts[111222]["prompt_message_id"] == 67890

        mock_bot.register_next_step_handler.assert_called_once_with(
            mock_call.message,
            process_ticket_description,
        )

    def test_first_screen(self, mock_bot, mock_call):
        """Тест: первый экран создания тикета"""
        with (
            patch(
                "handlers.client.tickets.get_client_bindings",
                return_value=["user1"],
            ),
            patch(
                "handlers.client.tickets.ticket_service.get_client_active_ticket",
                return_value=None,
            ),
        ):
            result = handle_create_ticket(mock_bot, 111222, mock_call, "create_ticket")
            assert result.text == "Создание тикета"
            assert result.show_alert is False
            mock_bot.answer_callback_query.assert_not_called()
            mock_bot.edit_message_text.assert_called_once()
            assert "Выберите тему" in mock_bot.edit_message_text.call_args[0][0]


class TestHandleTicketReply:
    """Тесты для handle_ticket_reply"""

    def test_ticket_not_found(self, mock_bot, mock_call):
        """Тест: тикет не найден"""
        with patch(
            "handlers.client.tickets.ticket_service.get_all_tickets", return_value={}
        ):
            result = handle_ticket_reply(
                mock_bot, 111222, mock_call, "ticket_reply:abc123"
            )
            assert "не найден" in result.text
            assert result.show_alert is True

    def test_ticket_access_denied(self, mock_bot, mock_call):
        """Тест: доступ к чужому тикету запрещён"""
        with patch(
            "handlers.client.tickets.ticket_service.get_ticket",
            return_value={"chat_id": 999999, "status": "open"},
        ):
            result = handle_ticket_reply(
                mock_bot, 111222, mock_call, "ticket_reply:abc123"
            )
            assert "недоступен" in result.text
            assert result.show_alert is True

    def test_ticket_closed(self, mock_bot, mock_call):
        """Тест: тикет уже закрыт"""
        with patch(
            "handlers.client.tickets.ticket_service.get_all_tickets",
            return_value={"abc123": {"chat_id": 111222, "status": "closed"}},
        ):
            result = handle_ticket_reply(
                mock_bot, 111222, mock_call, "ticket_reply:abc123"
            )
            assert "Тикет не найден" in result.text
            assert result.show_alert is True

    def test_successful_reply_start(self, mock_bot, mock_call):
        """Тест: успешное начало ответа в тикет"""
        with patch(
            "handlers.client.tickets.ticket_service.get_ticket",
            return_value={"chat_id": 111222, "status": "open"},
        ):
            result = handle_ticket_reply(
                mock_bot, 111222, mock_call, "ticket_reply:abc123"
            )
            assert result.text is None
            assert result.show_alert is False
            mock_bot.send_message.assert_called_once()
            mock_bot.register_next_step_handler.assert_called_once()


class TestProcessTicketReply:
    """Тесты для process_ticket_reply"""

    def test_cancel_reply(self, mock_bot):
        """Тест: отмена ответа кнопкой."""
        from handlers.client.tickets import _ticket_reply_drafts

        _ticket_reply_drafts[111222] = {
            "ticket_id": "abc123",
            "prompt_message_id": 54321,
        }

        call = Mock()
        call.message.chat.id = 111222

        result = handle_ticket_reply_cancel(
            mock_bot,
            111222,
            call,
            "ticket_reply_cancel:abc123",
        )

        assert result.text is None
        assert result.show_alert is False
        mock_bot.send_message.assert_not_called()
        mock_bot.clear_step_handler_by_chat_id.assert_called_once()
        mock_bot.edit_message_text.assert_called_once_with(
            "❌ Ответ отменён.",
            111222,
            54321,
        )
        assert 111222 not in _ticket_reply_drafts

    def test_empty_message(self, mock_bot):
        """Тест: пустое сообщение"""
        message = Mock()
        message.chat.id = 111222
        message.text = "   "

        from handlers.client.tickets import _ticket_reply_drafts

        _ticket_reply_drafts[111222] = "abc123"

        with patch("handlers.client.tickets.bot", mock_bot):
            process_ticket_reply(message)
            mock_bot.send_message.assert_called_once()
            assert "не может быть пустым" in mock_bot.send_message.call_args[0][1]
            mock_bot.register_next_step_handler.assert_called_once()

    def test_ticket_not_found_in_reply(self, mock_bot):
        """Тест: тикет удалён во время ответа"""
        message = Mock()
        message.chat.id = 111222
        message.text = "Тестовое сообщение"

        from handlers.client.tickets import _ticket_reply_drafts

        _ticket_reply_drafts[111222] = "abc123"

        with (
            patch("handlers.client.tickets.bot", mock_bot),
            patch(
                "handlers.client.tickets.ticket_service.get_all_tickets",
                return_value={},
            ),
        ):
            process_ticket_reply(message)
            assert "не найден" in mock_bot.send_message.call_args[0][1]

    def test_successful_reply(self, mock_bot):
        """Тест: успешное сохранение ответа"""
        message = Mock()
        message.chat.id = 111222
        message.text = "Тестовое сообщение"
        message.from_user.username = "testuser"

        from handlers.client.tickets import _ticket_reply_drafts

        _ticket_reply_drafts[111222] = "abc123"

        tickets = {"abc123": {"chat_id": 111222, "status": "answered", "messages": []}}

        with (
            patch("handlers.client.tickets.bot", mock_bot),
            patch(
                "handlers.client.tickets.ticket_service.get_ticket",
                return_value=tickets["abc123"],
            ),
            patch(
                "handlers.client.tickets.ticket_service.add_message",
                return_value=tickets["abc123"],
            ) as mock_add_message,
            patch(
                "handlers.client.tickets.ticket_service.set_status"
            ) as mock_set_status,
            patch("handlers.client.tickets.ADMIN_CHATS", [999888]),
        ):
            process_ticket_reply(message)

            # Проверяем передачу изменения в ticket_service
            mock_add_message.assert_called_once_with(
                "abc123",
                "client",
                "Тестовое сообщение",
            )
            mock_set_status.assert_called_once_with("abc123", "open")
            # Изменение данных выполняет ticket_service.
            # Здесь проверяем только контракт обработчика с сервисом.

            # Проверяем уведомление клиента
            assert "отправлен" in mock_bot.send_message.call_args_list[0][0][1]

            # Проверяем уведомление админа
            assert mock_bot.send_message.call_count == 2


class TestProcessTicketDescription:
    """Тесты для process_ticket_description"""

    def test_cancel_description(self, mock_bot):
        """Тест: отмена создания тикета через /cancel"""
        message = Mock()
        message.chat.id = 111222
        message.text = "/cancel"

        _ticket_drafts[111222] = {"topic": "Тест", "prompt_message_id": 12345}

        with patch("handlers.client.tickets.bot", mock_bot):
            process_ticket_description(message)
            mock_bot.send_message.assert_not_called()
            mock_bot.edit_message_text.assert_called_once_with(
                "❌ Создание тикета отменено.",
                111222,
                12345,
            )
            mock_bot.clear_step_handler_by_chat_id.assert_called_once()
            assert 111222 not in _ticket_drafts

    def test_empty_description(self, mock_bot):
        """Тест: пустое описание"""
        message = Mock()
        message.chat.id = 111222
        message.text = "   "

        _ticket_drafts[111222] = {"topic": "Тест"}

        with patch("handlers.client.tickets.bot", mock_bot):
            process_ticket_description(message)
            mock_bot.send_message.assert_called_once()
            assert "не может быть пустым" in mock_bot.send_message.call_args[0][1]
            mock_bot.register_next_step_handler.assert_called_once()

    def test_active_ticket_exists_during_creation(self, mock_bot):
        """Тест: активный тикет появился во время создания"""
        message = Mock()
        message.chat.id = 111222
        message.text = "Описание проблемы"
        message.from_user.username = "testuser"

        _ticket_drafts[111222] = {"topic": "Тест"}

        tickets = {"existing": {"chat_id": 111222, "status": "open"}}

        with (
            patch("handlers.client.tickets.bot", mock_bot),
            patch(
                "handlers.client.tickets.ticket_service.create_ticket",
                return_value=None,
            ),
            patch(
                "handlers.client.tickets.ticket_service.get_client_active_ticket",
                return_value=("existing", tickets["existing"]),
            ),
        ):
            process_ticket_description(message)
            assert mock_bot.send_message.call_count == 1
            assert "уже есть активный тикет" in mock_bot.send_message.call_args[0][1]
            assert 111222 not in _ticket_drafts

    def test_successful_ticket_creation(self, mock_bot):
        """Тест: успешное создание тикета"""
        message = Mock()
        message.chat.id = 111222
        message.text = "Описание проблемы"
        message.from_user.username = "testuser"

        _ticket_drafts[111222] = {
            "topic": "Не работает интернет",
            "prompt_message_id": 12345,
        }

        created_ticket = {
            "id": "test1234",
            "chat_id": 111222,
            "username": "testuser",
            "topic": "Не работает интернет",
            "description": "Описание проблемы",
            "status": "open",
            "messages": [],
        }

        with (
            patch("handlers.client.tickets.bot", mock_bot),
            patch(
                "handlers.client.tickets.ticket_service.create_ticket",
                return_value=created_ticket,
            ) as mock_create_ticket,
            patch("handlers.client.tickets.ADMIN_CHATS", [999888]),
        ):
            process_ticket_description(message)

            # Проверяем передачу создания тикета в ticket_service
            mock_create_ticket.assert_called_once_with(
                chat_id=111222,
                username="testuser",
                topic="Не работает интернет",
                description="Описание проблемы",
            )

            # Проверяем данные созданного тикета
            assert created_ticket["id"] == "test1234"
            assert created_ticket["topic"] == "Не работает интернет"
            assert created_ticket["description"] == "Описание проблемы"
            assert created_ticket["status"] == "open"

            # Проверяем уведомление клиента
            assert "создан" in mock_bot.send_message.call_args_list[0][0][1]

            # Проверяем уведомление админа
            assert mock_bot.send_message.call_count == 2
            assert 111222 not in _ticket_drafts


def test_handle_ticket_reply_closed_ticket_exact_branch(mock_bot, mock_call):
    with patch(
        "handlers.client.tickets.ticket_service.get_ticket",
        return_value={"chat_id": 111222, "status": "closed"},
    ):
        result = handle_ticket_reply(mock_bot, 111222, mock_call, "ticket_reply:abc123")

    assert result.text == "⚠️ Тикет уже закрыт."
    assert result.show_alert is True


def test_handle_ticket_reply_cancel_edit_exception(mock_bot, mock_call):
    from handlers.client.tickets import _ticket_reply_drafts

    _ticket_reply_drafts[111222] = {
        "ticket_id": "abc123",
        "prompt_message_id": 54321,
    }

    mock_bot.edit_message_text.side_effect = RuntimeError("edit failed")

    with patch("handlers.client.tickets.logger.warning") as mock_warning:
        result = handle_ticket_reply_cancel(
            mock_bot,
            111222,
            mock_call,
            "ticket_reply_cancel:abc123",
        )

    assert result.text is None
    assert result.show_alert is False
    mock_warning.assert_called_once()
    assert mock_warning.call_args.args[0] == (
        "ticket.reply.cancel_message_update_failed | "
        "chat_id=%s | error=%s"
    )
    assert mock_warning.call_args.args[1] == 111222
    assert str(mock_warning.call_args.args[2]) == "edit failed"
    assert 111222 not in _ticket_reply_drafts


def test_process_ticket_reply_cancel_command(mock_bot):
    message = Mock()
    message.chat.id = 111222
    message.text = "/cancel"

    from handlers.client.tickets import _ticket_reply_drafts

    _ticket_reply_drafts[111222] = "abc123"

    with patch("handlers.client.tickets.bot", mock_bot):
        process_ticket_reply(message)

    mock_bot.send_message.assert_called_once_with(
        111222,
        "❌ Ответ отменён.",
    )
    mock_bot.clear_step_handler_by_chat_id.assert_called_once_with(111222)
    assert 111222 not in _ticket_reply_drafts


def test_process_ticket_reply_add_message_failed(mock_bot):
    message = Mock()
    message.chat.id = 111222
    message.text = "Тестовое сообщение"

    from handlers.client.tickets import _ticket_reply_drafts

    _ticket_reply_drafts[111222] = "abc123"

    with (
        patch("handlers.client.tickets.bot", mock_bot),
        patch(
            "handlers.client.tickets.ticket_service.get_ticket",
            return_value={
                "chat_id": 111222,
                "status": "open",
                "messages": [],
            },
        ),
        patch(
            "handlers.client.tickets.ticket_service.add_message",
            return_value=None,
        ),
    ):
        process_ticket_reply(message)

    mock_bot.send_message.assert_called_once_with(
        111222,
        "⚠️ Не удалось сохранить ответ в тикет.",
    )
    mock_bot.clear_step_handler_by_chat_id.assert_called_once_with(111222)
    assert 111222 not in _ticket_reply_drafts


def test_process_ticket_reply_admin_notification_exception(mock_bot):
    message = Mock()
    message.chat.id = 111222
    message.text = "Тестовое сообщение"
    message.from_user.username = "testuser"

    from handlers.client.tickets import _ticket_reply_drafts

    _ticket_reply_drafts[111222] = "abc123"

    mock_bot.send_message.side_effect = [
        None,
        RuntimeError("admin notification failed"),
    ]

    with (
        patch("handlers.client.tickets.bot", mock_bot),
        patch(
            "handlers.client.tickets.ticket_service.get_ticket",
            return_value={
                "chat_id": 111222,
                "status": "open",
                "messages": [],
            },
        ),
        patch(
            "handlers.client.tickets.ticket_service.add_message",
            return_value={"id": "abc123"},
        ),
        patch("handlers.client.tickets.ticket_service.set_status"),
        patch("handlers.client.tickets.ADMIN_CHATS", [999888]),
        patch("handlers.client.tickets.logger.error") as mock_error,
    ):
        process_ticket_reply(message)

    mock_error.assert_called_once()
    assert mock_error.call_args.args[0] == (
        "ticket.reply.notification_failed | ticket_id=%s | "
        "admin_id=%s | error=%s"
    )
    assert mock_error.call_args.args[1] == "abc123"
    assert mock_error.call_args.args[2] == 999888
    assert str(mock_error.call_args.args[3]) == "admin notification failed"
    assert 111222 not in _ticket_reply_drafts


def test_process_ticket_description_cancel_edit_exception(mock_bot):
    message = Mock()
    message.chat.id = 111222
    message.text = "/cancel"

    _ticket_drafts[111222] = {
        "topic": "Тест",
        "prompt_message_id": 12345,
    }

    mock_bot.edit_message_text.side_effect = RuntimeError("edit failed")

    with (
        patch("handlers.client.tickets.bot", mock_bot),
        patch("handlers.client.tickets.logger.warning") as mock_warning,
    ):
        process_ticket_description(message)

    mock_warning.assert_called_once()
    assert mock_warning.call_args.args[0] == (
        "ticket.creation.cancel_message_update_failed | "
        "chat_id=%s | error=%s"
    )
    assert mock_warning.call_args.args[1] == 111222
    assert str(mock_warning.call_args.args[2]) == "edit failed"
    mock_bot.clear_step_handler_by_chat_id.assert_called_once_with(111222)
    assert 111222 not in _ticket_drafts


class TestClientTicketsEdgeCases:
    """Дополнительные тесты для непокрытых веток"""

    def test_process_ticket_reply_no_context(self, mock_bot):
        """Тест: контекст тикета потерян (строки 215-220)"""
        message = Mock()
        message.chat.id = 111222
        message.text = "Тестовое сообщение"

        # Очищаем черновики
        from handlers.client.tickets import _ticket_reply_drafts

        _ticket_reply_drafts.clear()

        with patch("handlers.client.tickets.bot", mock_bot):
            process_ticket_reply(message)
            mock_bot.send_message.assert_called_once()
            assert "Контекст тикета потерян" in mock_bot.send_message.call_args[0][1]
            mock_bot.clear_step_handler_by_chat_id.assert_called_once()

    def test_process_ticket_reply_wrong_chat_id(self, mock_bot):
        """Тест: попытка ответить в чужой тикет (строки 249-252)"""
        message = Mock()
        message.chat.id = 111222
        message.text = "Тестовое сообщение"

        from handlers.client.tickets import _ticket_reply_drafts

        _ticket_reply_drafts[111222] = "abc123"

        tickets = {
            "abc123": {
                "chat_id": 999999,  # Другой chat_id
                "status": "open",
                "messages": [],
            }
        }

        with (
            patch("handlers.client.tickets.bot", mock_bot),
            patch(
                "handlers.client.tickets.ticket_service.get_ticket",
                return_value=tickets["abc123"],
            ),
        ):
            process_ticket_reply(message)
            mock_bot.send_message.assert_called_once()
            assert "недоступен" in mock_bot.send_message.call_args[0][1]
            assert 111222 not in _ticket_reply_drafts

    def test_process_ticket_reply_closed_ticket(self, mock_bot):
        """Тест: попытка ответить в закрытый тикет (строки 255-262)"""
        message = Mock()
        message.chat.id = 111222
        message.text = "Тестовое сообщение"

        from handlers.client.tickets import _ticket_reply_drafts

        _ticket_reply_drafts[111222] = "abc123"

        tickets = {"abc123": {"chat_id": 111222, "status": "closed", "messages": []}}

        with (
            patch("handlers.client.tickets.bot", mock_bot),
            patch(
                "handlers.client.tickets.ticket_service.get_ticket",
                return_value=tickets["abc123"],
            ),
        ):
            process_ticket_reply(message)
            mock_bot.send_message.assert_called_once()
            assert "уже закрыт" in mock_bot.send_message.call_args[0][1]
            assert 111222 not in _ticket_reply_drafts

    def test_process_ticket_description_edit_markup_exception(self, mock_bot):
        """Тест: обработка исключения при удалении кнопок после создания.

        Проверяет строки 420-421.
        """
        message = Mock()
        message.chat.id = 111222
        message.text = "Описание проблемы"
        message.from_user.username = "testuser"

        _ticket_drafts[111222] = {"topic": "Тест", "prompt_message_id": 12345}

        mock_bot.edit_message_reply_markup.side_effect = Exception("Message not found")

        created_ticket = {
            "id": "test1234",
            "chat_id": 111222,
            "username": "testuser",
            "topic": "Тест",
            "description": "Описание проблемы",
            "status": "open",
            "messages": [],
        }

        with (
            patch("handlers.client.tickets.bot", mock_bot),
            patch(
                "handlers.client.tickets.ticket_service.create_ticket",
                return_value=created_ticket,
            ) as _,
            patch("handlers.client.tickets.ADMIN_CHATS", [999888]),
        ):
            process_ticket_description(message)

            # Должно продолжить работу несмотря на исключение
            mock_bot.send_message.assert_called()
            assert 111222 not in _ticket_drafts

    def test_admin_notification_exception(self, mock_bot):
        """Тест: обработка исключения при уведомлении админа (строки 458-459)"""
        message = Mock()
        message.chat.id = 111222
        message.text = "Описание проблемы"
        message.from_user.username = "testuser"

        _ticket_drafts[111222] = {"topic": "Тест", "prompt_message_id": 12345}

        # Первое сообщение клиенту проходит, второе админу падает
        mock_bot.send_message.side_effect = [
            Mock(),
            Exception("Admin notification failed"),
        ]

        created_ticket = {
            "id": "test1234",
            "chat_id": 111222,
            "username": "testuser",
            "topic": "Тест",
            "description": "Описание проблемы",
            "status": "open",
            "messages": [],
        }

        with (
            patch("handlers.client.tickets.bot", mock_bot),
            patch(
                "handlers.client.tickets.ticket_service.create_ticket",
                return_value=created_ticket,
            ) as _,
            patch("handlers.client.tickets.ADMIN_CHATS", [999888]),
        ):
            process_ticket_description(message)

            # Тикет должен быть создан несмотря на ошибку уведомления
            assert 111222 not in _ticket_drafts


def test_process_ticket_description_logs_markup_exception(mock_bot):
    message = Mock()
    message.chat.id = 111222
    message.text = "Описание проблемы"
    message.from_user.username = "testuser"

    _ticket_drafts[111222] = {
        "topic": "Тест",
        "prompt_message_id": 12345,
    }

    created_ticket = {
        "id": "test1234",
        "chat_id": 111222,
        "username": "testuser",
        "topic": "Тест",
        "description": "Описание проблемы",
        "status": "open",
        "messages": [],
    }

    with (
        patch("handlers.client.tickets.bot", mock_bot),
        patch(
            "handlers.client.tickets.ticket_service.create_ticket",
            return_value=created_ticket,
        ),
        patch(
            "handlers.client.tickets.safe_edit_message_reply_markup",
            side_effect=RuntimeError("markup failed"),
        ),
        patch("handlers.client.tickets.ADMIN_CHATS", []),
        patch("handlers.client.tickets.logger.warning") as mock_warning,
    ):
        process_ticket_description(message)

    mock_warning.assert_called_once()
    assert mock_warning.call_args.args[0] == (
        "ticket.creation.cleanup_message_failed | "
        "ticket_id=%s | chat_id=%s | error=%s"
    )
    assert mock_warning.call_args.args[1] == "test1234"
    assert mock_warning.call_args.args[2] == 111222
    assert str(mock_warning.call_args.args[3]) == "markup failed"
    assert 111222 not in _ticket_drafts


def test_process_ticket_description_admin_keyboard_exception_is_logged(mock_bot):
    message = Mock()
    message.chat.id = 111222
    message.text = "Описание проблемы"
    message.from_user.username = "testuser"

    _ticket_drafts[111222] = {
        "topic": "Тест",
        "prompt_message_id": 12345,
    }

    created_ticket = {
        "id": "test1234",
        "chat_id": 111222,
        "username": "testuser",
        "topic": "Тест",
        "description": "Описание проблемы",
        "status": "open",
        "messages": [],
    }

    with (
        patch("handlers.client.tickets.bot", mock_bot),
        patch(
            "handlers.client.tickets.ticket_service.create_ticket",
            return_value=created_ticket,
        ),
        patch("handlers.client.tickets.ADMIN_CHATS", [999888]),
        patch(
            "handlers.client.tickets.types.InlineKeyboardMarkup",
            side_effect=RuntimeError("keyboard failed"),
        ),
        patch("handlers.client.tickets.logger.error") as mock_error,
    ):
        process_ticket_description(message)

    mock_error.assert_called_once()
    assert mock_error.call_args.args[0] == (
        "ticket.creation.notification_failed | "
        "ticket_id=%s | admin_id=%s | error=%s"
    )
    assert mock_error.call_args.args[1] == "test1234"
    assert mock_error.call_args.args[2] == 999888
    assert str(mock_error.call_args.args[3]) == "keyboard failed"
    assert 111222 not in _ticket_drafts
