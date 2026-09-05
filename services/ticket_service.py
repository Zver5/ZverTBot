"""
Бизнес-логика тикетов поддержки.

Handlers не должны напрямую изменять структуру тикета.
Этот модуль является владельцем операций над тикетами,
а data.storage отвечает только за физическое хранение.
"""

import uuid
from datetime import datetime

from data.storage import load_tickets, save_tickets
from utils.client_operation_lock import client_operation_lock

ACTIVE_TICKET_STATUSES = ("open", "answered")


def get_all_tickets():
    """Возвращает все тикеты."""
    return load_tickets()


def get_ticket(ticket_id):
    """Возвращает тикет по ID или None."""
    tickets = load_tickets()
    return tickets.get(ticket_id)


def get_client_active_ticket(chat_id):
    """
    Возвращает первый активный тикет клиента:
    (ticket_id, ticket) или None.
    """
    tickets = load_tickets()

    return next(
        (
            (ticket_id, ticket)
            for ticket_id, ticket in tickets.items()
            if ticket.get("chat_id") == chat_id
            and ticket.get("status") in ACTIVE_TICKET_STATUSES
        ),
        None,
    )


@client_operation_lock
def create_ticket(chat_id, username, topic, description):
    """
    Создаёт новый тикет.

    Возвращает созданный тикет.
    Если у клиента уже есть активный тикет — возвращает None.
    """
    tickets = load_tickets()

    active_ticket = next(
        (
            (ticket_id, ticket)
            for ticket_id, ticket in tickets.items()
            if ticket.get("chat_id") == chat_id
            and ticket.get("status") in ACTIVE_TICKET_STATUSES
        ),
        None,
    )

    if active_ticket:
        return None

    ticket_id = str(uuid.uuid4())[:8]
    now = datetime.now()

    ticket = {
        "id": ticket_id,
        "chat_id": chat_id,
        "username": username,
        "topic": topic,
        "description": description,
        "status": "open",
        "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "messages": [
            {
                "role": "client",
                "text": description,
                "time": now.strftime("%H:%M"),
            }
        ],
    }

    tickets[ticket_id] = ticket
    save_tickets(tickets)

    return ticket


@client_operation_lock
def add_message(ticket_id, role, text):
    """
    Добавляет сообщение в существующий тикет.

    Возвращает обновлённый тикет или None,
    если тикет не найден.
    """
    tickets = load_tickets()

    ticket = tickets.get(ticket_id)

    if ticket is None:
        return None

    ticket.setdefault("messages", []).append(
        {
            "role": role,
            "text": text,
            "time": datetime.now().strftime("%H:%M"),
        }
    )

    save_tickets(tickets)

    return ticket


@client_operation_lock
def set_status(ticket_id, status):
    """Изменяет статус тикета."""
    tickets = load_tickets()

    ticket = tickets.get(ticket_id)

    if ticket is None:
        return None

    ticket["status"] = status
    save_tickets(tickets)

    return ticket


@client_operation_lock
def close_ticket(ticket_id):
    """Закрывает тикет."""
    return set_status(ticket_id, "closed")
