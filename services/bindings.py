"""
Бизнес-логика привязок клиентов к Telegram.
"""

from data.storage import (
    load_client_bindings,
    save_client_bindings,
)
from utils.client_operation_lock import client_operation_lock

MAX_CLIENT_BINDINGS = 4


def get_pending_bindings() -> dict:
    """Получить все ожидающие заявки на привязку."""
    from data.storage import load_pending_bindings

    return load_pending_bindings()


@client_operation_lock
def add_pending_binding(chat_id: str, name: str, time: str) -> None:
    """Добавить или обновить заявку на привязку."""
    from data.storage import load_pending_bindings, save_pending_bindings

    pending = load_pending_bindings()
    pending[str(chat_id)] = {
        "name": name,
        "time": time,
    }
    save_pending_bindings(pending)


@client_operation_lock
def remove_pending_binding(chat_id: str) -> bool:
    """Удалить ожидающую заявку на привязку."""
    from data.storage import load_pending_bindings, save_pending_bindings

    pending = load_pending_bindings()
    chat_id = str(chat_id)

    if chat_id not in pending:
        return False

    del pending[chat_id]
    save_pending_bindings(pending)
    return True


def normalize_bindings_list(value) -> list:
    """Привести значение привязок одного chat_id к списку."""
    if isinstance(value, list):
        return value
    return [value] if value else []


def get_client_bindings(chat_id: str) -> list:
    """Получить список клиентов, привязанных к chat_id."""
    bindings = load_client_bindings()
    return normalize_bindings_list(bindings.get(str(chat_id), []))


def get_all_client_bindings() -> dict:
    """Получить все привязки клиентов к Telegram chat_id."""
    return load_client_bindings()


@client_operation_lock
def add_client_binding(chat_id: str, username: str) -> str:
    """
    Добавить клиента к Telegram chat_id.

    Возвращает:
        "added"     — клиент добавлен;
        "duplicate" — клиент уже привязан;
        "limit"     — достигнут лимит привязок.
    """
    chat_id = str(chat_id)
    bindings = load_client_bindings()
    current_list = normalize_bindings_list(bindings.get(chat_id, []))

    if username in current_list:
        return "duplicate"

    if len(current_list) >= MAX_CLIENT_BINDINGS:
        return "limit"

    current_list.append(username)
    bindings[chat_id] = current_list
    save_client_bindings(bindings)

    return "added"


@client_operation_lock
def remove_client_from_all_bindings(username: str) -> int:
    """Удалить клиента из всех Telegram-привязок.

    Возвращает количество chat_id, из которых клиент удалён.
    """
    bindings = load_client_bindings()
    removed = 0

    for chat_id, value in list(bindings.items()):
        clients = normalize_bindings_list(value)

        if username not in clients:
            continue

        clients = [client for client in clients if client != username]
        removed += 1

        if clients:
            bindings[chat_id] = clients
        else:
            del bindings[chat_id]

    if removed:
        save_client_bindings(bindings)

    return removed


@client_operation_lock
def remove_client_binding(chat_id: str, username: str) -> bool:
    """
    Удалить конкретную привязку клиента к Telegram chat_id.

    Возвращает:
        True — привязка удалена;
        False — привязка не найдена.
    """
    chat_id = str(chat_id)
    bindings = load_client_bindings()

    if chat_id not in bindings:
        return False

    clients = normalize_bindings_list(bindings[chat_id])

    if username not in clients:
        return False

    clients.remove(username)

    if clients:
        bindings[chat_id] = clients
    else:
        del bindings[chat_id]

    save_client_bindings(bindings)
    return True
