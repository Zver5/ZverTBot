"""
Тесты services/client_menu.py
"""

from unittest.mock import Mock, patch

import pytest

from ui.client_menu import get_client_account_screen, get_client_menu


def test_client_menu_empty_accounts():
    with (
        patch("ui.client_menu.load_client_bindings", return_value={}),
        patch("ui.client_menu.get_users_list", return_value=[]),
        patch("ui.client_menu.client_accounts_kb", return_value="KB") as kb,
    ):
        result = get_client_menu(100)

        assert result[0] == "KB"
        assert result[1] == "👋 Привет! Выберите аккаунт:"
        assert result[2] is False

        kb.assert_called_once()


def test_client_menu_single_vless_account():

    with (
        patch("ui.client_menu.load_client_bindings", return_value={"100": ["user1"]}),
        patch(
            "ui.client_menu.get_users_list",
            side_effect=lambda proto: ["user1"] if proto == "vless" else [],
        ),
        patch("ui.client_menu.get_client_protocol", return_value="vless"),
        patch("ui.client_menu.get_client_protocol", return_value="vless"),
        patch("ui.client_menu.client_account_kb", return_value="ACCOUNT_KB") as kb,
    ):
        result = get_client_menu(100)

        assert result[0] == "ACCOUNT_KB"
        assert "user1" in result[1]
        assert result[2] is True

        kb.assert_called_once_with("user1", "vless")


def test_client_menu_single_awg_account():

    with (
        patch(
            "ui.client_menu.load_client_bindings", return_value={"100": ["user_awg"]}
        ),
        patch(
            "ui.client_menu.get_users_list",
            side_effect=lambda proto: ["user_awg"] if proto == "awg" else [],
        ),
        patch("ui.client_menu.get_client_protocol", return_value="awg"),
        patch("ui.client_menu.client_account_kb", return_value="ACCOUNT_KB") as kb,
    ):
        result = get_client_menu(100)

        assert result[0] == "ACCOUNT_KB"
        assert result[2] is True

        kb.assert_called_once_with("user_awg", "awg")


def test_client_menu_multiple_accounts():

    with (
        patch(
            "ui.client_menu.load_client_bindings",
            return_value={"100": ["user1", "user2"]},
        ),
        patch(
            "ui.client_menu.get_users_list",
            side_effect=lambda proto: ["user1", "user2"],
        ),
        patch("ui.client_menu.client_accounts_kb", return_value="MULTI_KB") as kb,
    ):
        result = get_client_menu(100)

        assert result[0] == "MULTI_KB"
        assert result[1] == "👋 Привет! Выберите аккаунт:"
        assert result[2] is False

        kb.assert_called_once()


def test_client_menu_single_account_string_format():

    with (
        patch("ui.client_menu.load_client_bindings", return_value={"100": "user1"}),
        patch(
            "ui.client_menu.get_users_list",
            side_effect=lambda proto: ["user1"] if proto == "vless" else [],
        ),
        patch("ui.client_menu.get_client_protocol", return_value="vless"),
        patch("ui.client_menu.client_account_kb", return_value="ACCOUNT_KB") as kb,
    ):
        result = get_client_menu(100)

        assert result[0] == "ACCOUNT_KB"
        assert result[2] is True

        kb.assert_called_once_with("user1", "vless")


def test_client_account_screen_unknown_protocol():
    with patch(
        "ui.client_menu.get_client_protocol",
        return_value=None,
    ):
        result = get_client_account_screen("alice")

        assert result is None


def test_client_account_screen_vless():
    with (
        patch(
            "ui.client_menu.get_client_protocol",
            return_value="vless",
        ),
        patch(
            "ui.client_menu.client_account_kb",
            return_value="ACCOUNT_KB",
        ) as kb,
    ):
        result = get_client_account_screen("alice")

        assert result == (
            "ACCOUNT_KB",
            "👤 Аккаунт: *alice*\n\nВыберите действие:",
            True,
        )

        kb.assert_called_once_with("alice", "vless")


def test_client_account_screen_awg():
    with (
        patch(
            "ui.client_menu.get_client_protocol",
            return_value="awg",
        ),
        patch(
            "ui.client_menu.client_account_kb",
            return_value="ACCOUNT_KB",
        ) as kb,
    ):
        result = get_client_account_screen("bob")

        assert result == (
            "ACCOUNT_KB",
            "👤 Аккаунт: *bob*\n\nВыберите действие:",
            True,
        )

        kb.assert_called_once_with("bob", "awg")


@pytest.fixture
def mock_call():
    call = Mock()
    call.message = Mock()
    call.message.message_id = 67890
    return call


@pytest.fixture
def mock_bot():
    bot = Mock()
    bot.edit_message_text = Mock()
    bot.send_message = Mock()
    bot.send_document = Mock()
    bot.answer_callback_query = Mock()
    bot.delete_message = Mock()
    return bot


class TestClientNavigationCoverage:
    def test_render_account_without_runtime_username(
        self,
        mock_bot,
    ):
        from handlers.client.navigation import (
            _CLIENT_ACCOUNT_USERS,
            _render_client_account,
        )

        _CLIENT_ACCOUNT_USERS.pop(111222, None)

        assert (
            _render_client_account(
                mock_bot,
                111222,
                67890,
            )
            is False
        )

        mock_bot.send_message.assert_called_once_with(
            111222,
            "❌ Клиент не найден.",
        )

    def test_render_account_uses_runtime_username(
        self,
        mock_bot,
    ):
        with (
            patch(
                "handlers.client.navigation._CLIENT_ACCOUNT_USERS",
                {111222: "user1"},
            ),
            patch(
                "handlers.client.navigation.render_client_account",
                return_value=True,
            ) as mock_render,
        ):
            from handlers.client.navigation import _render_client_account

            assert (
                _render_client_account(
                    mock_bot,
                    111222,
                    67890,
                )
                is True
            )

        mock_render.assert_called_once_with(
            mock_bot,
            111222,
            67890,
            "user1",
        )

    def test_render_navigation_screen_success(
        self,
        mock_bot,
    ):
        with patch(
            "handlers.client.navigation.navigation.render",
            return_value=True,
        ) as mock_render:
            from handlers.client.navigation import render_client_navigation_screen

            assert (
                render_client_navigation_screen(
                    mock_bot,
                    111222,
                    67890,
                    "client:home",
                )
                is True
            )

        mock_render.assert_called_once_with(
            "client:home",
            mock_bot,
            111222,
            67890,
        )

    def test_render_navigation_screen_handles_error(
        self,
        mock_bot,
    ):
        with (
            patch(
                "handlers.client.navigation.navigation.render",
                side_effect=RuntimeError("render failed"),
            ),
            patch("handlers.client.navigation.logger.exception") as mock_log,
        ):
            from handlers.client.navigation import render_client_navigation_screen

            assert (
                render_client_navigation_screen(
                    mock_bot,
                    111222,
                    67890,
                    "client:home",
                )
                is False
            )

        mock_log.assert_called_once()

    def test_account_owned_check_uses_client_list(self):
        with patch(
            "ui.client_menu.get_client_list",
            return_value=["user1", "user2"],
        ) as mock_list:
            from handlers.client.navigation import _is_client_account_owned

            assert _is_client_account_owned(111222, "user1") is True
            assert _is_client_account_owned(111222, "unknown") is False

        mock_list.assert_called_with(111222)

    def test_conf_callback_routes_to_handler(
        self,
        mock_bot,
        mock_call,
    ):
        with patch(
            "handlers.client.navigation.handle_client_conf",
            return_value=True,
        ) as mock_conf:
            from handlers.client.navigation import (
                handle_client_navigation_callback,
            )

            result = handle_client_navigation_callback(
                mock_bot,
                111222,
                mock_call,
                "client:conf:user1",
            )

        assert result is True
        mock_conf.assert_called_once_with(
            mock_bot,
            111222,
            mock_call,
            "client:conf:user1",
        )

    def test_navigation_unknown_callback_returns_false(
        self,
        mock_bot,
        mock_call,
    ):
        from handlers.client.navigation import handle_client_navigation_callback

        assert (
            handle_client_navigation_callback(
                mock_bot,
                111222,
                mock_call,
                "client:unknown",
            )
            is False
        )
