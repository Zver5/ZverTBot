"""
Unit-тесты бизнес-логики services.ticket_service.
"""

from unittest.mock import patch

from services import ticket_service


class TestGetAllTickets:
    def test_returns_all_tickets(self):
        tickets = {"abc": {"status": "open"}}

        with patch(
            "services.ticket_service.load_tickets",
            return_value=tickets,
        ) as mock_load:
            result = ticket_service.get_all_tickets()

        assert result == tickets
        mock_load.assert_called_once()


class TestGetTicket:
    def test_returns_existing_ticket(self):
        ticket = {"id": "abc", "status": "open"}

        with patch(
            "services.ticket_service.load_tickets",
            return_value={"abc": ticket},
        ):
            assert ticket_service.get_ticket("abc") == ticket

    def test_returns_none_for_missing_ticket(self):
        with patch(
            "services.ticket_service.load_tickets",
            return_value={},
        ):
            assert ticket_service.get_ticket("missing") is None


class TestGetClientActiveTicket:
    def test_returns_first_active_ticket(self):
        tickets = {
            "closed": {"chat_id": "123", "status": "closed"},
            "open": {"chat_id": "123", "status": "open"},
            "answered": {"chat_id": "123", "status": "answered"},
        }

        with patch(
            "services.ticket_service.load_tickets",
            return_value=tickets,
        ):
            result = ticket_service.get_client_active_ticket("123")

        assert result == ("open", tickets["open"])

    def test_ignores_other_client(self):
        tickets = {
            "abc": {"chat_id": "999", "status": "open"},
        }

        with patch(
            "services.ticket_service.load_tickets",
            return_value=tickets,
        ):
            assert ticket_service.get_client_active_ticket("123") is None

    def test_returns_none_without_active_ticket(self):
        tickets = {
            "abc": {"chat_id": "123", "status": "closed"},
        }

        with patch(
            "services.ticket_service.load_tickets",
            return_value=tickets,
        ):
            assert ticket_service.get_client_active_ticket("123") is None


class TestCreateTicket:
    def test_creates_ticket(self):
        tickets = {}

        with (
            patch(
                "services.ticket_service.load_tickets",
                return_value=tickets,
            ),
            patch("services.ticket_service.save_tickets") as mock_save,
            patch(
                "services.ticket_service.uuid.uuid4",
                return_value="12345678-aaaa-bbbb-cccc-dddddddddddd",
            ),
            patch("services.ticket_service.datetime") as mock_datetime,
        ):
            now = mock_datetime.now.return_value
            now.strftime.side_effect = lambda fmt: {
                "%Y-%m-%d %H:%M:%S": "2026-08-14 01:10:00",
                "%H:%M": "01:10",
            }[fmt]

            result = ticket_service.create_ticket(
                "123",
                "testuser",
                "Не работает интернет",
                "Интернет не работает",
            )

        assert result is not None
        assert result["id"] == "12345678"
        assert result["chat_id"] == "123"
        assert result["username"] == "testuser"
        assert result["topic"] == "Не работает интернет"
        assert result["description"] == "Интернет не работает"
        assert result["status"] == "open"
        assert result["created_at"] == "2026-08-14 01:10:00"
        assert result["messages"] == [
            {
                "role": "client",
                "text": "Интернет не работает",
                "time": "01:10",
            }
        ]

        assert tickets["12345678"] == result
        mock_save.assert_called_once_with(tickets)

    def test_does_not_create_when_active_ticket_exists(self):
        tickets = {
            "abc123": {
                "chat_id": "123",
                "status": "open",
            }
        }

        with (
            patch(
                "services.ticket_service.load_tickets",
                return_value=tickets,
            ),
            patch("services.ticket_service.save_tickets") as mock_save,
        ):
            result = ticket_service.create_ticket(
                "123",
                "testuser",
                "Тема",
                "Описание",
            )

        assert result is None
        mock_save.assert_not_called()
        assert tickets == {
            "abc123": {
                "chat_id": "123",
                "status": "open",
            }
        }

    def test_closed_ticket_does_not_block_creation(self):
        tickets = {
            "old": {
                "chat_id": "123",
                "status": "closed",
            }
        }

        with (
            patch(
                "services.ticket_service.load_tickets",
                return_value=tickets,
            ),
            patch("services.ticket_service.save_tickets") as mock_save,
            patch(
                "services.ticket_service.uuid.uuid4",
                return_value="abcdefgh-aaaa-bbbb-cccc-dddddddddddd",
            ),
            patch("services.ticket_service.datetime") as mock_datetime,
        ):
            now = mock_datetime.now.return_value
            now.strftime.side_effect = lambda fmt: {
                "%Y-%m-%d %H:%M:%S": "2026-08-14 01:11:00",
                "%H:%M": "01:11",
            }[fmt]

            result = ticket_service.create_ticket(
                "123",
                "testuser",
                "Новая тема",
                "Новое описание",
            )

        assert result["id"] == "abcdefgh"
        assert result["status"] == "open"
        mock_save.assert_called_once_with(tickets)


class TestAddMessage:
    def test_adds_message(self):
        ticket = {
            "id": "abc",
            "messages": [],
        }
        tickets = {"abc": ticket}

        with (
            patch(
                "services.ticket_service.load_tickets",
                return_value=tickets,
            ),
            patch("services.ticket_service.save_tickets") as mock_save,
            patch("services.ticket_service.datetime") as mock_datetime,
        ):
            now = mock_datetime.now.return_value
            now.strftime.return_value = "01:20"

            result = ticket_service.add_message(
                "abc",
                "admin",
                "Ответ администратора",
            )

        assert result is ticket
        assert ticket["messages"] == [
            {
                "role": "admin",
                "text": "Ответ администратора",
                "time": "01:20",
            }
        ]
        mock_save.assert_called_once_with(tickets)

    def test_adds_message_when_messages_key_missing(self):
        ticket = {
            "id": "abc",
        }
        tickets = {"abc": ticket}

        with (
            patch(
                "services.ticket_service.load_tickets",
                return_value=tickets,
            ),
            patch("services.ticket_service.save_tickets"),
            patch("services.ticket_service.datetime") as mock_datetime,
        ):
            mock_datetime.now.return_value.strftime.return_value = "01:21"

            result = ticket_service.add_message(
                "abc",
                "client",
                "Новое сообщение",
            )

        assert result is ticket
        assert ticket["messages"] == [
            {
                "role": "client",
                "text": "Новое сообщение",
                "time": "01:21",
            }
        ]

    def test_returns_none_for_missing_ticket(self):
        with patch(
            "services.ticket_service.load_tickets",
            return_value={},
        ):
            assert (
                ticket_service.add_message(
                    "missing",
                    "client",
                    "text",
                )
                is None
            )


class TestSetStatus:
    def test_sets_status(self):
        ticket = {
            "id": "abc",
            "status": "open",
        }
        tickets = {"abc": ticket}

        with (
            patch(
                "services.ticket_service.load_tickets",
                return_value=tickets,
            ),
            patch("services.ticket_service.save_tickets") as mock_save,
        ):
            result = ticket_service.set_status("abc", "answered")

        assert result is ticket
        assert ticket["status"] == "answered"
        mock_save.assert_called_once_with(tickets)

    def test_returns_none_for_missing_ticket(self):
        with patch(
            "services.ticket_service.load_tickets",
            return_value={},
        ):
            assert ticket_service.set_status("missing", "closed") is None


class TestCloseTicket:
    def test_closes_ticket(self):
        ticket = {"id": "abc", "status": "open"}

        with patch(
            "services.ticket_service.set_status",
            return_value=ticket,
        ) as mock_set:
            result = ticket_service.close_ticket("abc")

        assert result is ticket
        mock_set.assert_called_once_with("abc", "closed")
