"""
Тесты для handlers/admin/tickets.py
Проверяет админскую часть системы тикетов.
"""

from unittest.mock import Mock, patch

import pytest

from core.navigation import NAV_ADMIN_TICKETS_CALLBACK
from handlers.admin.tickets import (
    cmd_admin_tickets,
    handle_admin_close,
    handle_admin_reply,
    handle_admin_tickets,
    show_closed_ticket,
    show_closed_tickets,
    show_new_tickets,
    show_working_tickets,
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
    call.data = "admin_tickets"
    call.message = Mock()
    call.message.message_id = 67890
    call.message.chat.id = 111222
    call.message.text = "Исходный текст"
    return call


class TestCmdAdminTickets:
    def test_not_admin_with_message(self, mock_bot):
        message = Mock()
        message.chat.id = 111222

        with (
            patch("handlers.admin.tickets.is_admin", return_value=False),
            patch("handlers.admin.tickets.bot", mock_bot),
        ):
            cmd_admin_tickets(message)

        mock_bot.send_message.assert_called_once_with(
            111222,
            "⛔ Доступ запрещён.",
        )
        mock_bot.answer_callback_query.assert_not_called()

    def test_no_open_tickets(self, mock_bot):
        message = Mock()
        message.chat.id = 111222

        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value={
                    "abc": {"status": "closed"},
                },
            ),
            patch("handlers.admin.tickets.bot", mock_bot),
        ):
            cmd_admin_tickets(message)

        mock_bot.send_message.assert_any_call(
            111222,
            "🎫 Загрузка тикетов...",
        )
        mock_bot.send_message.assert_any_call(
            111222,
            "✅ Открытых тикетов нет.",
        )
        assert mock_bot.send_message.call_count == 2

    def test_open_and_answered_tickets(self, mock_bot):
        message = Mock()
        message.chat.id = 111222

        tickets = {
            "open123": {
                "username": "user1",
                "topic": "Проблема",
                "status": "open",
                "created_at": "2026-08-21",
            },
            "answered123": {
                "username": "user2",
                "topic": "Вопрос",
                "status": "answered",
                "created_at": "2026-08-20",
            },
            "closed123": {
                "username": "user3",
                "topic": "Закрытый",
                "status": "closed",
                "created_at": "2026-08-19",
            },
        }

        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
            patch("handlers.admin.tickets.bot", mock_bot),
        ):
            cmd_admin_tickets(message)

        assert mock_bot.send_message.call_count == 3

        first_call = mock_bot.send_message.call_args_list[0]
        assert first_call.args == (111222, "🎫 Загрузка тикетов...")

        sent_messages = [
            call.args[1] for call in mock_bot.send_message.call_args_list[1:]
        ]

        assert any("Тикет #open123" in text for text in sent_messages)
        assert any("Тикет #answered123" in text for text in sent_messages)
        assert not any("Тикет #closed123" in text for text in sent_messages)

        open_message = next(text for text in sent_messages if "Тикет #open123" in text)
        answered_message = next(
            text for text in sent_messages if "Тикет #answered123" in text
        )

        assert "🟢 Открыт" in open_message
        assert "🟡 Ожидает ответа клиента" in answered_message


def test_admin_ticket_card_escapes_created_at():
    from handlers.admin.tickets import _admin_ticket_card

    ticket = {
        "username": "user",
        "topic": "Тема",
        "description": "Описание",
        "created_at": "2026_08_24_[12:00]",
    }

    result = _admin_ticket_card("abc123", ticket)

    assert "2026\\_08\\_24\\_\\[12:00\\]" in result


def test_admin_ticket_card_escapes_markdown_fields():
    from handlers.admin.tickets import _admin_ticket_card

    ticket = {
        "username": "user_*[test]",
        "topic": "Тема_*[тест]",
        "description": "Описание_*[тест]",
        "created_at": "2026-08-24 12:00",
    }

    result = _admin_ticket_card("abc123", ticket)

    assert "@user\\_\\*\\[test\\]" in result
    assert "Тема\\_\\*\\[тест\\]" in result
    assert "Описание\\_\\*\\[тест\\]" in result
    assert "2026-08-24 12:00" in result


class TestHandleAdminTickets:
    def test_not_admin(self, mock_bot, mock_call):
        with patch("handlers.admin.tickets.is_admin", return_value=False):
            result = handle_admin_tickets(mock_bot, 111222, mock_call, "admin_tickets")
            assert result.text == "⛔ Доступ запрещён."
            mock_bot.answer_callback_query.assert_not_called()

    def test_show_menu(self, mock_bot, mock_call):
        tickets = {"abc": {"status": "open"}, "def": {"status": "closed"}}
        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
        ):
            result = handle_admin_tickets(mock_bot, 111222, mock_call, "admin_tickets")
            assert result.text is None
            mock_bot.edit_message_text.assert_called_once()

    def test_ticket_history_roles(self, mock_bot, mock_call):
        tickets = {
            "abc123": {
                "chat_id": 999,
                "username": "user1",
                "topic": "История",
                "status": "answered",
                "messages": [
                    {"role": "client", "text": "Сообщение клиента", "time": "10:00"},
                    {"role": "admin", "text": "Ответ администратора", "time": "10:01"},
                    {"role": "system", "text": "Системное сообщение", "time": "10:02"},
                    {"role": "moderator", "text": "Неизвестная роль", "time": "10:03"},
                ],
            }
        }

        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
        ):
            show_working_tickets(
                mock_bot,
                111222,
                None,
                None,
            )

        sent_text = mock_bot.send_message.call_args.args[1]

        assert "💬 *История:*" in sent_text
        assert "👤 Клиент [10:00]:" in sent_text
        assert "Сообщение клиента" in sent_text
        assert "👨‍💼 Админ [10:01]:" in sent_text
        assert "Ответ администратора" in sent_text
        assert "system [10:02]:" in sent_text
        assert "Системное сообщение" in sent_text
        assert "moderator [10:03]:" in sent_text
        assert "Неизвестная роль" in sent_text


class TestShowNewTickets:
    def test_not_admin_with_call(self, mock_bot, mock_call):
        with patch("handlers.admin.tickets.is_admin", return_value=False):
            result = show_new_tickets(mock_bot, 111222, mock_call, "admin_new_tickets")
            assert result.text == "⛔ Доступ запрещён."
            mock_bot.answer_callback_query.assert_not_called()

    def test_not_admin_without_call(self, mock_bot):
        with patch("handlers.admin.tickets.is_admin", return_value=False):
            result = show_new_tickets(mock_bot, 111222)

        assert result.text is None
        mock_bot.send_message.assert_called_once_with(
            111222,
            "⛔ Доступ запрещён.",
        )

    def test_no_new_tickets_without_call(self, mock_bot):
        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value={},
            ),
        ):
            result = show_new_tickets(mock_bot, 111222)

        assert result.text is None
        mock_bot.send_message.assert_called_once_with(
            111222,
            "✅ Новых тикетов нет.",
        )

    def test_no_new_tickets_with_call(self, mock_bot, mock_call):
        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets", return_value={}
            ),
        ):
            result = show_new_tickets(mock_bot, 111222, mock_call, "admin_new_tickets")
            assert result.text == "✅ Новых тикетов нет."
            mock_bot.answer_callback_query.assert_not_called()

    def test_with_new_tickets(self, mock_bot, mock_call):
        tickets = {
            "abc123": {
                "chat_id": 999,
                "username": "u1",
                "topic": "t",
                "status": "open",
                "created_at": "2026",
                "description": "d",
            }
        }
        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
        ):
            result = show_new_tickets(mock_bot, 111222, mock_call, "admin_new_tickets")
            assert result.text is None
            mock_bot.send_message.assert_called_once()


class TestShowWorkingTickets:
    def test_no_working_tickets(self, mock_bot, mock_call):
        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets", return_value={}
            ),
        ):
            result = show_working_tickets(
                mock_bot, 111222, mock_call, "admin_working_tickets"
            )
            assert result.text == "✅ Тикетов в работе нет."

    def test_with_working_tickets(self, mock_bot, mock_call):
        tickets = {
            "abc123": {
                "chat_id": 999,
                "username": "u1",
                "topic": "t",
                "status": "answered",
                "created_at": "2026",
            }
        }
        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
        ):
            result = show_working_tickets(
                mock_bot, 111222, mock_call, "admin_working_tickets"
            )
            assert result.text is None


class TestShowClosedTickets:
    def test_no_closed_tickets(self, mock_bot, mock_call):
        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets", return_value={}
            ),
        ):
            result = show_closed_tickets(
                mock_bot, 111222, mock_call, "admin_closed_tickets"
            )
            assert result.text == "📭 Закрытых тикетов пока нет."

    def test_with_closed_tickets(self, mock_bot, mock_call):
        tickets = {
            "abc123": {
                "chat_id": 999,
                "username": "u1",
                "topic": "t",
                "status": "closed",
                "created_at": "2026",
            }
        }
        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
        ):
            result = show_closed_tickets(
                mock_bot, 111222, mock_call, "admin_closed_tickets"
            )
            assert result.text is None

    def test_shows_only_two_latest_closed_tickets_and_edits_message(
        self, mock_bot, mock_call
    ):
        tickets = {
            "old": {
                "chat_id": 999,
                "username": "user",
                "topic": "Old",
                "description": "Old ticket",
                "status": "closed",
                "created_at": "2026-08-01",
                "closed_at": "2026-08-01 10:00",
            },
            "latest": {
                "chat_id": 999,
                "username": "user",
                "topic": "Latest",
                "description": "Latest ticket",
                "status": "closed",
                "created_at": "2026-08-04",
                "closed_at": "2026-08-04 10:00",
            },
            "middle": {
                "chat_id": 999,
                "username": "user",
                "topic": "Middle",
                "description": "Middle ticket",
                "status": "closed",
                "created_at": "2026-08-03",
                "closed_at": "2026-08-03 10:00",
            },
            "newer": {
                "chat_id": 999,
                "username": "user",
                "topic": "Newer",
                "description": "Newer ticket",
                "status": "closed",
                "created_at": "2026-08-05",
                "closed_at": "2026-08-05 10:00",
            },
        }

        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
        ):
            result = show_closed_tickets(
                mock_bot, 111222, mock_call, "admin_closed_tickets"
            )

        assert result.text is None

        mock_bot.edit_message_text.assert_called_once()
        mock_bot.send_message.assert_not_called()

        edit_kwargs = mock_bot.edit_message_text.call_args.kwargs
        text = edit_kwargs["text"]
        keyboard = edit_kwargs["reply_markup"]

        buttons = [button for row in keyboard.keyboard for button in row]

        assert any(
            button.text == "↩️ Назад"
            and button.callback_data == NAV_ADMIN_TICKETS_CALLBACK
            for button in buttons
        )

        assert "Тикет #latest" in text
        assert "Тикет #newer" in text
        assert "Тикет #middle" not in text
        assert "Тикет #old" not in text

    def test_closed_tickets_pagination_shows_second_page(self, mock_bot, mock_call):
        tickets = {
            f"ticket{i}": {
                "chat_id": 999,
                "username": "user",
                "topic": f"Topic {i}",
                "description": f"Ticket {i}",
                "status": "closed",
                "created_at": f"2026-08-{i:02d}",
                "closed_at": f"2026-08-{i:02d} 10:00",
            }
            for i in range(1, 6)
        }

        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
        ):
            result = show_closed_tickets(
                mock_bot, 111222, mock_call, "admin_closed_page:1"
            )

        assert result.text is None

        edit_kwargs = mock_bot.edit_message_text.call_args.kwargs
        text = edit_kwargs["text"]
        keyboard = edit_kwargs["reply_markup"]

        assert "страница 2/3" in text
        assert "Тикет #ticket3" in text
        assert "Тикет #ticket2" in text
        assert "Тикет #ticket4" not in text
        assert "Тикет #ticket1" not in text
        assert "Тикет #ticket5" not in text

        buttons = [button for row in keyboard.keyboard for button in row]

        assert any(
            button.text == "◀️ Предыдущие"
            and button.callback_data == "admin_closed_page:0"
            for button in buttons
        )
        assert any(
            button.text == "Следующие ▶️"
            and button.callback_data == "admin_closed_page:2"
            for button in buttons
        )

    def test_closed_ticket_opens_full_history_and_edits_message(
        self, mock_bot, mock_call
    ):
        tickets = {
            "abc123": {
                "chat_id": 999,
                "username": "user",
                "topic": "Support",
                "description": "Need help",
                "status": "closed",
                "created_at": "2026-08-01",
                "closed_at": "2026-08-02 10:00",
                "messages": [
                    {
                        "role": "client",
                        "time": "10:00",
                        "text": "Hello",
                    },
                    {
                        "role": "admin",
                        "time": "10:05",
                        "text": "Problem solved",
                    },
                ],
            }
        }

        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
        ):
            result = show_closed_ticket(
                mock_bot,
                111222,
                mock_call,
                "admin_closed_ticket:abc123",
            )

        assert result.text is None
        mock_bot.edit_message_text.assert_called_once()
        mock_bot.send_message.assert_not_called()

        edit_kwargs = mock_bot.edit_message_text.call_args.kwargs
        text = edit_kwargs["text"]
        keyboard = edit_kwargs["reply_markup"]

        assert "Тикет #abc123" in text
        assert "💬 *История:*" in text
        assert "Hello" in text
        assert "Problem solved" in text
        assert keyboard.keyboard[0][0].text == "↩️ Назад"
        assert keyboard.keyboard[0][0].callback_data == "admin_closed_page:0"


class TestHandleAdminReply:
    def test_not_admin(self, mock_bot, mock_call):
        mock_call.data = "admin_reply_ticket:abc123"
        with patch("handlers.admin.tickets.is_admin", return_value=False):
            result = handle_admin_reply(
                mock_bot, 111222, mock_call, "admin_reply_ticket:abc123"
            )
            assert result.text == "⛔ Доступ запрещён."
            mock_bot.answer_callback_query.assert_not_called()

    def test_ticket_not_found(self, mock_bot, mock_call):
        mock_call.data = "admin_reply_ticket:abc123"
        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets", return_value={}
            ),
        ):
            result = handle_admin_reply(
                mock_bot, 111222, mock_call, "admin_reply_ticket:abc123"
            )
            assert result.text == "⚠️ Тикет не найден."
            mock_bot.answer_callback_query.assert_not_called()

    def test_successful_reply_start(self, mock_bot, mock_call):
        mock_call.data = "admin_reply_ticket:abc123"
        tickets = {"abc123": {"chat_id": 999, "username": "u1", "status": "open"}}
        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
        ):
            result = handle_admin_reply(
                mock_bot, 111222, mock_call, "admin_reply_ticket:abc123"
            )
            assert result.text == "Введите текст ответа"
            mock_bot.answer_callback_query.assert_not_called()
            mock_bot.send_message.assert_called_once()
            mock_bot.register_next_step_handler.assert_called_once()


class TestHandleAdminClose:
    def test_not_admin(self, mock_bot, mock_call):
        mock_call.data = "admin_close_ticket:abc123"
        with patch("handlers.admin.tickets.is_admin", return_value=False):
            result = handle_admin_close(
                mock_bot, 111222, mock_call, "admin_close_ticket:abc123"
            )
            assert result.text == "⛔ Доступ запрещён."
            mock_bot.answer_callback_query.assert_not_called()

    def test_ticket_not_found(self, mock_bot, mock_call):
        mock_call.data = "admin_close_ticket:abc123"
        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets", return_value={}
            ),
        ):
            result = handle_admin_close(
                mock_bot, 111222, mock_call, "admin_close_ticket:abc123"
            )
            assert result.text == "⚠️ Тикет не найден."
            mock_bot.answer_callback_query.assert_not_called()

    def test_close_failed(self, mock_bot, mock_call):
        from handlers.admin.tickets import handle_admin_close

        mock_call.data = "admin_close_ticket:abc123"
        tickets = {"abc123": {"chat_id": 999, "username": "u1", "status": "open"}}

        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
            patch(
                "handlers.admin.tickets.ticket_service.close_ticket",
                return_value=None,
            ) as mock_close,
        ):
            result = handle_admin_close(
                mock_bot,
                111222,
                mock_call,
                "admin_close_ticket:abc123",
            )

        mock_close.assert_called_once_with("abc123")
        assert result.text == "⚠️ Не удалось закрыть тикет."
        mock_bot.answer_callback_query.assert_not_called()
        mock_bot.edit_message_text.assert_not_called()
        mock_bot.send_message.assert_not_called()

    def test_successful_close(self, mock_bot, mock_call):
        mock_call.data = "admin_close_ticket:abc123"
        tickets = {"abc123": {"chat_id": 999, "username": "u1", "status": "open"}}
        closed_ticket = {
            **tickets["abc123"],
            "status": "closed",
            "messages": [
                {
                    "role": "system",
                    "text": "System message",
                    "time": "10:00",
                }
            ],
        }

        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
            patch(
                "handlers.admin.tickets.ticket_service.close_ticket",
                return_value=closed_ticket,
            ) as mock_close,
        ):
            handle_admin_close(mock_bot, 111222, mock_call, "admin_close_ticket:abc123")
            mock_close.assert_called_once_with("abc123")
            assert mock_close.return_value["status"] == "closed"
            mock_bot.send_message.assert_called_once()

        text = mock_bot.edit_message_text.call_args.kwargs["text"]
        assert "system [10:00]:" in text
        assert "System message" in text

    def test_successful_close_escapes_markdown_in_username(self, mock_bot, mock_call):
        mock_call.data = "admin_close_ticket:abc123"
        mock_call.message.text = "🎫 *Тикет #abc123*"

        tickets = {
            "abc123": {
                "chat_id": 999,
                "username": "user_524260702",
                "topic": "Не работает интернет",
                "description": "test",
                "created_at": "2026-08-24 12:22:14",
                "status": "open",
                "messages": [
                    {
                        "role": "client",
                        "text": "test",
                        "time": "12:22",
                    },
                    {
                        "role": "admin",
                        "text": "/start",
                        "time": "22:26",
                    },
                ],
            }
        }

        closed_ticket = {
            **tickets["abc123"],
            "status": "closed",
            "closed_at": "2026-08-25 22:26:22",
        }

        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
            patch(
                "handlers.admin.tickets.ticket_service.close_ticket",
                return_value=closed_ticket,
            ),
        ):
            result = handle_admin_close(
                mock_bot,
                111222,
                mock_call,
                "admin_close_ticket:abc123",
            )

        assert result.text == "Тикет закрыт"

        mock_bot.edit_message_text.assert_called_once()
        kwargs = mock_bot.edit_message_text.call_args.kwargs

        assert kwargs["parse_mode"] == "Markdown"
        assert "user\\_524260702" in kwargs["text"]
        assert "Не работает интернет" in kwargs["text"]
        assert "test" in kwargs["text"]
        assert "/start" in kwargs["text"]

        mock_bot.send_message.assert_called_once_with(
            999,
            (
                "✅ *Тикет #abc123 был закрыт администратором.*\n\n"
                "Если проблема осталась, пожалуйста, создайте новый тикет."
            ),
            parse_mode="Markdown",
        )

    def test_client_notification_failure(self, mock_bot):
        from handlers.admin.tickets import handle_admin_close

        call = Mock()
        call.id = "callback-123"
        call.data = "admin_close_ticket:abc123"
        call.from_user.id = 111222
        call.message.chat.id = 111222
        call.message.message_id = 55
        call.message.text = "🎫 Тикет #abc123"

        tickets = {
            "abc123": {
                "chat_id": 999,
                "status": "open",
            }
        }

        mock_bot.send_message.side_effect = RuntimeError("client blocked bot")

        with (
            patch(
                "handlers.admin.tickets.is_admin",
                return_value=True,
            ),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
            patch(
                "handlers.admin.tickets.ticket_service.close_ticket",
                return_value={
                    **tickets["abc123"],
                    "status": "closed",
                },
            ),
            patch(
                "handlers.admin.tickets.logger.error",
            ) as mock_error,
        ):
            result = handle_admin_close(mock_bot, 111222, call, call.data)

        assert result.text == "Тикет закрыт"
        mock_bot.answer_callback_query.assert_not_called()
        mock_bot.edit_message_text.assert_called_once()

        mock_bot.send_message.assert_called_once()
        assert mock_bot.send_message.call_args.args[0] == 999

        mock_error.assert_called_once()

    def test_working_tickets_not_admin_without_call(self, mock_bot):
        with patch("handlers.admin.tickets.is_admin", return_value=False):
            result = show_working_tickets(mock_bot, 111222)

        assert result.text is None
        mock_bot.send_message.assert_called_once_with(
            111222,
            "⛔ Доступ запрещён.",
        )
        mock_bot.answer_callback_query.assert_not_called()

    def test_closed_tickets_not_admin_and_empty_without_call(self, mock_bot):
        with patch("handlers.admin.tickets.is_admin", return_value=False):
            result = show_closed_tickets(mock_bot, 111222)

        assert result.text is None
        mock_bot.send_message.assert_called_once_with(
            111222,
            "⛔ Доступ запрещён.",
        )

        mock_bot.reset_mock()

        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value={},
            ),
        ):
            result = show_closed_tickets(mock_bot, 111222)

        assert result.text is None
        mock_bot.send_message.assert_called_once_with(
            111222,
            "📭 Закрытых тикетов пока нет.",
        )

    def test_closed_ticket_escapes_closed_at_and_message_time(self, mock_bot):
        tickets = {
            "closed_escape": {
                "chat_id": 999,
                "username": "user",
                "topic": "Тема",
                "description": "Описание",
                "created_at": "2026-08-25",
                "status": "closed",
                "messages": [
                    {
                        "role": "client",
                        "text": "Тест",
                        "time": "12_30_[UTC]",
                    }
                ],
            }
        }

        closed_ticket = {
            **tickets["closed_escape"],
            "closed_at": "2026_08_25_[22:30]",
        }

        call = Mock()
        call.data = "admin_close_ticket:closed_escape"
        call.message.chat.id = 111222
        call.message.message_id = 777

        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
            patch(
                "handlers.admin.tickets.ticket_service.close_ticket",
                return_value=closed_ticket,
            ),
        ):
            result = handle_admin_close(
                mock_bot,
                111222,
                call,
                call.data,
            )

        assert result.text == "Тикет закрыт"

        text = mock_bot.edit_message_text.call_args.kwargs["text"]
        assert "2026\\_08\\_25\\_\\[22:30\\]" in text
        assert "12\\_30\\_\\[UTC\\]" in text

    def test_closed_ticket_escapes_markdown_timestamps(self, mock_bot, mock_call):
        from handlers.admin.tickets import show_closed_ticket

        mock_call.message.chat.id = 111222
        mock_call.message.message_id = 777

        tickets = {
            "closed_escape": {
                "chat_id": 999,
                "username": "user",
                "topic": "Тема",
                "description": "Описание",
                "created_at": "2026-08-25",
                "status": "closed",
                "closed_at": "2026_08_25_[22:30]",
                "messages": [
                    {
                        "role": "client",
                        "text": "Тест",
                        "time": "12_30_[UTC]",
                    }
                ],
            }
        }

        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
        ):
            result = show_closed_ticket(
                mock_bot,
                111222,
                mock_call,
                "admin_closed_ticket:closed_escape",
            )

        assert result.text is None

        text = mock_bot.edit_message_text.call_args.kwargs["text"]
        assert "2026\\_08\\_25\\_\\[22:30\\]" in text
        assert "12\\_30\\_\\[UTC\\]" in text
        mock_bot.send_message.assert_not_called()

    def test_closed_ticket_history_roles(self, mock_bot, mock_call):
        from handlers.admin.tickets import show_closed_ticket

        mock_call.message.chat.id = 111222
        mock_call.message.message_id = 777

        tickets = {
            "closed123": {
                "chat_id": 999,
                "username": "user1",
                "topic": "История",
                "status": "closed",
                "closed_at": "2026-08-21 12:00",
                "messages": [
                    {"role": "client", "text": "Сообщение клиента", "time": "10:00"},
                    {"role": "admin", "text": "Ответ администратора", "time": "10:01"},
                    {"role": "system", "text": "Системное сообщение", "time": "10:02"},
                ],
            }
        }

        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
        ):
            result = show_closed_ticket(
                mock_bot,
                111222,
                mock_call,
                "admin_closed_ticket:closed123",
            )

        assert result.text is None
        mock_bot.edit_message_text.assert_called_once()
        mock_bot.send_message.assert_not_called()

        text = mock_bot.edit_message_text.call_args.kwargs["text"]

        assert "🔒 Закрыт: 2026-08-21 12:00" in text
        assert "💬 *История:*" in text
        assert "👤 Клиент [10:00]:" in text
        assert "Сообщение клиента" in text
        assert "👨‍💼 Админ [10:01]:" in text
        assert "Ответ администратора" in text
        assert "system [10:02]:" in text
        assert "Системное сообщение" in text

    def test_callback_access_denied_branches(self, mock_bot, mock_call):
        mock_call.id = "callback-123"
        mock_call.message.chat.id = 111222

        with patch("handlers.admin.tickets.is_admin", return_value=False):
            result = show_new_tickets(mock_bot, 111222, mock_call)
            assert result.text == "⛔ Доступ запрещён."
            mock_bot.answer_callback_query.assert_not_called()

        mock_bot.reset_mock()

        with patch("handlers.admin.tickets.is_admin", return_value=False):
            result = show_working_tickets(mock_bot, 111222, mock_call)
            assert result.text == "⛔ Доступ запрещён."
            mock_bot.answer_callback_query.assert_not_called()

        mock_bot.reset_mock()

        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value={},
            ),
        ):
            result = show_working_tickets(mock_bot, 111222, mock_call)
            assert result.text == "✅ Тикетов в работе нет."
            mock_bot.answer_callback_query.assert_not_called()

        mock_bot.reset_mock()

        with patch("handlers.admin.tickets.is_admin", return_value=False):
            result = show_closed_tickets(mock_bot, 111222, mock_call)
            assert result.text == "⛔ Доступ запрещён."
            mock_bot.answer_callback_query.assert_not_called()

    def test_menu_edit_failure_falls_back_to_send(self, mock_bot, mock_call):
        mock_call.id = "callback-123"
        mock_call.message.chat.id = 111222
        mock_call.message.message_id = 55

        mock_bot.edit_message_text.side_effect = RuntimeError("edit failed")

        with patch("handlers.admin.tickets.is_admin", return_value=True):
            result = handle_admin_tickets(
                mock_bot,
                111222,
                mock_call,
                "admin_tickets",
            )

        assert result.text is None
        mock_bot.edit_message_text.assert_called_once()
        mock_bot.send_message.assert_called_once()
        assert mock_bot.send_message.call_args.args[0] == 111222
        assert "🎫 *Управление тикетами*" in mock_bot.send_message.call_args.args[1]

    def test_working_tickets_empty_without_call(self, mock_bot):
        with (
            patch("handlers.admin.tickets.is_admin", return_value=True),
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value={},
            ),
        ):
            result = show_working_tickets(mock_bot, 111222)

        assert result.text is None
        mock_bot.send_message.assert_called_once_with(
            111222,
            "✅ Тикетов в работе нет.",
        )


class TestProcessAdminReply:
    @pytest.fixture(autouse=True)
    def patch_module_bot(self, mock_bot, monkeypatch):
        monkeypatch.setattr("handlers.admin.tickets.bot", mock_bot)

    def test_cancel(self, mock_bot):
        from handlers.admin.tickets import (
            _admin_reply_drafts,
            process_admin_reply,
        )

        message = Mock()
        message.chat.id = 111222
        message.text = "/cancel"

        _admin_reply_drafts[111222] = "abc123"

        process_admin_reply(message)

        mock_bot.send_message.assert_called_once_with(
            111222,
            "❌ Ответ отменён.",
        )
        mock_bot.clear_step_handler_by_chat_id.assert_called_once_with(111222)
        assert 111222 not in _admin_reply_drafts

    def test_empty_reply(self, mock_bot):
        from handlers.admin.tickets import process_admin_reply

        message = Mock()
        message.chat.id = 111222
        message.text = "   "

        process_admin_reply(message)

        mock_bot.send_message.assert_called_once_with(
            111222,
            "⚠️ Текст ответа не может быть пустым.",
        )
        mock_bot.register_next_step_handler.assert_called_once_with(
            message,
            process_admin_reply,
        )

    def test_missing_ticket_context(self, mock_bot):
        from handlers.admin.tickets import process_admin_reply

        message = Mock()
        message.chat.id = 111222
        message.text = "Ответ администратора"

        with patch(
            "handlers.admin.tickets.ticket_service.get_all_tickets",
            return_value={},
        ):
            process_admin_reply(message)

        mock_bot.send_message.assert_called_once_with(
            111222,
            "⚠️ Ошибка: контекст тикета потерян.",
        )
        mock_bot.clear_step_handler_by_chat_id.assert_called_once_with(111222)

    def test_ticket_deleted(self, mock_bot):
        from handlers.admin.tickets import (
            _admin_reply_drafts,
            process_admin_reply,
        )

        message = Mock()
        message.chat.id = 111222
        message.text = "Ответ администратора"

        _admin_reply_drafts[111222] = "abc123"

        with patch(
            "handlers.admin.tickets.ticket_service.get_all_tickets",
            return_value={},
        ):
            process_admin_reply(message)

        mock_bot.send_message.assert_called_once_with(
            111222,
            "⚠️ Тикет был удалён.",
        )
        mock_bot.clear_step_handler_by_chat_id.assert_called_once_with(111222)
        assert 111222 not in _admin_reply_drafts

    def test_add_message_failed(self, mock_bot):
        from handlers.admin.tickets import (
            _admin_reply_drafts,
            process_admin_reply,
        )

        message = Mock()
        message.chat.id = 111222
        message.text = "Ответ администратора"

        _admin_reply_drafts[111222] = "abc123"

        tickets = {
            "abc123": {
                "chat_id": 999,
                "status": "open",
            }
        }

        with (
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
            patch(
                "handlers.admin.tickets.ticket_service.add_message",
                return_value=None,
            ),
        ):
            process_admin_reply(message)

        mock_bot.send_message.assert_called_once_with(
            111222,
            "⚠️ Не удалось обновить тикет.",
        )
        mock_bot.clear_step_handler_by_chat_id.assert_called_once_with(111222)
        assert 111222 not in _admin_reply_drafts

    def test_successful_reply(self, mock_bot):
        from handlers.admin.tickets import (
            _admin_reply_drafts,
            process_admin_reply,
        )

        message = Mock()
        message.chat.id = 111222
        message.text = "Ответ администратора"

        _admin_reply_drafts[111222] = "abc123"

        tickets = {
            "abc123": {
                "chat_id": 999,
                "status": "open",
            }
        }

        updated_ticket = {
            **tickets["abc123"],
            "status": "answered",
        }

        with (
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
            patch(
                "handlers.admin.tickets.ticket_service.add_message",
                return_value=updated_ticket,
            ) as mock_add,
            patch(
                "handlers.admin.tickets.ticket_service.set_status",
            ) as mock_status,
        ):
            process_admin_reply(message)

        mock_add.assert_called_once_with(
            "abc123",
            "admin",
            "Ответ администратора",
        )
        mock_status.assert_called_once_with("abc123", "answered")

        assert mock_bot.send_message.call_count == 2
        mock_bot.clear_step_handler_by_chat_id.assert_called_once_with(111222)
        assert 111222 not in _admin_reply_drafts

    def test_client_notification_failure(self, mock_bot):
        from handlers.admin.tickets import (
            _admin_reply_drafts,
            process_admin_reply,
        )

        message = Mock()
        message.chat.id = 111222
        message.text = "Ответ администратора"

        _admin_reply_drafts[111222] = "abc123"

        tickets = {
            "abc123": {
                "chat_id": 999,
                "status": "open",
            }
        }

        updated_ticket = {
            **tickets["abc123"],
            "status": "answered",
        }

        def send_message(*args, **kwargs):
            if args and args[0] == 999:
                raise RuntimeError("client blocked bot")

        mock_bot.send_message.side_effect = send_message

        with (
            patch(
                "handlers.admin.tickets.ticket_service.get_all_tickets",
                return_value=tickets,
            ),
            patch(
                "handlers.admin.tickets.ticket_service.add_message",
                return_value=updated_ticket,
            ),
            patch(
                "handlers.admin.tickets.ticket_service.set_status",
            ),
            patch(
                "handlers.admin.tickets.logger.error",
            ) as mock_error,
        ):
            process_admin_reply(message)

        mock_error.assert_called_once()

        assert mock_bot.send_message.call_count == 3
        assert mock_bot.send_message.call_args_list[0].args[0] == 111222
        assert mock_bot.send_message.call_args_list[1].args[0] == 999
        assert mock_bot.send_message.call_args_list[2].args[0] == 111222

        assert 111222 not in _admin_reply_drafts


def test_closed_tickets_invalid_page_defaults_to_first_page(mock_bot, mock_call):
    tickets = {
        "ticket1": {
            "chat_id": 999,
            "username": "user",
            "topic": "Topic",
            "status": "closed",
            "created_at": "2026-08-01",
            "closed_at": "2026-08-01 10:00",
        }
    }

    with (
        patch("handlers.admin.tickets.is_admin", return_value=True),
        patch(
            "handlers.admin.tickets.ticket_service.get_all_tickets",
            return_value=tickets,
        ),
    ):
        result = show_closed_tickets(
            mock_bot,
            111222,
            mock_call,
            "admin_closed_page:not-a-number",
        )

    assert result.text is None
    text = mock_bot.edit_message_text.call_args.kwargs["text"]
    assert "страница 1/1" in text
    assert "Тикет #ticket1" in text


def test_closed_tickets_edit_failure_falls_back_to_send(mock_bot, mock_call):
    tickets = {
        "ticket1": {
            "chat_id": 999,
            "username": "user",
            "topic": "Topic",
            "status": "closed",
            "created_at": "2026-08-01",
            "closed_at": "2026-08-01 10:00",
        }
    }
    mock_bot.edit_message_text.side_effect = RuntimeError("edit failed")

    with (
        patch("handlers.admin.tickets.is_admin", return_value=True),
        patch(
            "handlers.admin.tickets.ticket_service.get_all_tickets",
            return_value=tickets,
        ),
    ):
        result = show_closed_tickets(
            mock_bot,
            111222,
            mock_call,
            "admin_closed_tickets",
        )

    assert result.text is None
    mock_bot.edit_message_text.assert_called_once()
    mock_bot.send_message.assert_called_once()


def test_closed_ticket_edit_failure_falls_back_to_send(mock_bot, mock_call):
    tickets = {
        "abc123": {
            "chat_id": 999,
            "username": "user",
            "topic": "Topic",
            "status": "closed",
            "created_at": "2026-08-01",
            "messages": [],
        }
    }
    mock_bot.edit_message_text.side_effect = RuntimeError("edit failed")

    with (
        patch("handlers.admin.tickets.is_admin", return_value=True),
        patch(
            "handlers.admin.tickets.ticket_service.get_all_tickets",
            return_value=tickets,
        ),
    ):
        result = show_closed_ticket(
            mock_bot,
            111222,
            mock_call,
            "admin_closed_ticket:abc123",
        )

    assert result.text is None
    mock_bot.edit_message_text.assert_called_once()
    mock_bot.send_message.assert_called_once()


def test_show_closed_tickets_without_call_sends_message(mock_bot):
    tickets = {
        "ticket1": {
            "chat_id": 999,
            "username": "user",
            "topic": "Topic",
            "status": "closed",
            "created_at": "2026-08-01",
        }
    }

    with (
        patch("handlers.admin.tickets.is_admin", return_value=True),
        patch(
            "handlers.admin.tickets.ticket_service.get_all_tickets",
            return_value=tickets,
        ),
    ):
        result = show_closed_tickets(
            mock_bot,
            111222,
            None,
            "admin_closed_tickets",
        )

    assert result.text is None
    mock_bot.send_message.assert_called_once()
    mock_bot.edit_message_text.assert_not_called()


def test_show_closed_ticket_rejects_non_admin(mock_bot, mock_call):
    with patch("handlers.admin.tickets.is_admin", return_value=False):
        result = show_closed_ticket(
            mock_bot,
            111222,
            mock_call,
            "admin_closed_ticket:abc123",
        )

    assert result.text == "⛔ Доступ запрещён."
    mock_bot.edit_message_text.assert_not_called()
    mock_bot.send_message.assert_not_called()


def test_show_closed_ticket_rejects_invalid_callback(mock_bot, mock_call):
    with patch("handlers.admin.tickets.is_admin", return_value=True):
        result = show_closed_ticket(
            mock_bot,
            111222,
            mock_call,
            "wrong_callback",
        )

    assert result.text == "⛔ Некорректный тикет."


def test_show_closed_ticket_rejects_missing_or_open_ticket(mock_bot, mock_call):
    with (
        patch("handlers.admin.tickets.is_admin", return_value=True),
        patch(
            "handlers.admin.tickets.ticket_service.get_all_tickets",
            return_value={
                "open1": {
                    "status": "open",
                }
            },
        ),
    ):
        result = show_closed_ticket(
            mock_bot,
            111222,
            mock_call,
            "admin_closed_ticket:open1",
        )

    assert result.text == "📭 Закрытый тикет не найден."


def test_show_closed_ticket_without_call_sends_message(mock_bot):
    tickets = {
        "abc123": {
            "chat_id": 999,
            "username": "user",
            "topic": "Topic",
            "status": "closed",
            "created_at": "2026-08-01",
            "messages": [],
        }
    }

    with (
        patch("handlers.admin.tickets.is_admin", return_value=True),
        patch(
            "handlers.admin.tickets.ticket_service.get_all_tickets",
            return_value=tickets,
        ),
    ):
        result = show_closed_ticket(
            mock_bot,
            111222,
            None,
            "admin_closed_ticket:abc123",
        )

    assert result.text is None
    mock_bot.send_message.assert_called_once()
    mock_bot.edit_message_text.assert_not_called()
