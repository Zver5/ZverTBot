"""
Проверка прав доступа.

Централизованные функции проверки ролей пользователей.
"""

from config.secrets import ADMIN_CHATS
from data.storage import load_client_bindings
from services.bindings import normalize_bindings_list


def get_client_accounts(chat_id):
    """
    Возвращает список всех аккаунтов пользователя.
    """
    bindings = load_client_bindings()
    return normalize_bindings_list(bindings.get(str(chat_id)))


def is_admin(chat_id):
    """
    Проверка администратора.
    """
    return str(chat_id) in [str(x) for x in ADMIN_CHATS]


def is_client(chat_id):
    """
    Есть ли хотя бы один привязанный аккаунт.
    """
    return bool(get_client_accounts(chat_id))
