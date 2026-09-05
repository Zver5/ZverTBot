"""
Тесты для core/access.py — проверка прав доступа.
"""

from core import access

# Тестовые chat_id администраторов
ADMIN_TEST_CHAT = "ADMIN_TEST_CHAT"
ADMIN_TEST_CHAT_2 = "ADMIN_TEST_CHAT_2"


# ==========================================================
# is_admin
# ==========================================================


def test_is_admin_true(monkeypatch):
    """Админский chat_id должен возвращать True"""
    monkeypatch.setattr(access, "ADMIN_CHATS", [ADMIN_TEST_CHAT, ADMIN_TEST_CHAT_2])

    assert access.is_admin(ADMIN_TEST_CHAT) is True


def test_is_admin_second_admin(monkeypatch):
    """Второй админ тоже должен иметь доступ"""
    monkeypatch.setattr(access, "ADMIN_CHATS", [ADMIN_TEST_CHAT, ADMIN_TEST_CHAT_2])

    assert access.is_admin(ADMIN_TEST_CHAT_2) is True


def test_is_admin_false(monkeypatch):
    """Обычный chat_id должен возвращать False"""
    monkeypatch.setattr(access, "ADMIN_CHATS", [ADMIN_TEST_CHAT, ADMIN_TEST_CHAT_2])

    assert access.is_admin(999999) is False


def test_is_admin_string_comparison(monkeypatch):
    """ADMIN_CHATS сравнивается как строки"""
    monkeypatch.setattr(access, "ADMIN_CHATS", [ADMIN_TEST_CHAT])

    assert access.is_admin("ADMIN_TEST_CHAT") is True


# ==========================================================
# is_client
# ==========================================================


def test_is_client_true(monkeypatch):
    """Привязанный клиент должен возвращать True"""
    fake_bindings = {"123456": ["user1"]}
    monkeypatch.setattr(access, "load_client_bindings", lambda: fake_bindings)
    assert access.is_client(123456) is True


def test_is_client_false(monkeypatch):
    """Непривязанный клиент должен возвращать False"""
    fake_bindings = {"123456": ["user1"]}
    monkeypatch.setattr(access, "load_client_bindings", lambda: fake_bindings)
    assert access.is_client(999999) is False


def test_is_client_empty_bindings(monkeypatch):
    """Пустые bindings должны возвращать False"""
    monkeypatch.setattr(access, "load_client_bindings", dict)
    assert access.is_client(123456) is False


def test_is_client_string_key(monkeypatch):
    """Ключ в bindings — строка (chat_id как строка)"""
    fake_bindings = {"123456": ["user1"]}
    monkeypatch.setattr(access, "load_client_bindings", lambda: fake_bindings)
    assert access.is_client("123456") is True


def test_get_client_accounts_single_account(monkeypatch):
    """Одиночный аккаунт должен быть преобразован в список."""
    monkeypatch.setattr(
        access,
        "load_client_bindings",
        lambda: {"123456": "user1"},
    )

    assert access.get_client_accounts(123456) == ["user1"]
