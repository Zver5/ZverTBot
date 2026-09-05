"""
Тесты клиентской навигации и клиентских обработчиков.

Проверяется новая архитектура:
Telegram callback -> callback_router -> handle_client_navigation_callback
-> renderer / конкретный client handler.

Старый handle_client_functions_callback здесь намеренно не используется.
"""

from unittest.mock import Mock, patch

import pytest

from core import callback_router as router
from core.navigation import navigation
from handlers.client.menu import (
    handle_client_conf,
    handle_client_conf_ru,
    handle_client_stats,
    render_client_account,
    render_client_help,
    render_client_home,
)
from handlers.client.navigation import handle_client_navigation_callback


@pytest.fixture
def mock_bot():
    bot = Mock()
    bot.edit_message_text = Mock()
    bot.send_message = Mock()
    bot.send_document = Mock()
    bot.answer_callback_query = Mock()
    bot.delete_message = Mock()
    return bot


@pytest.fixture
def mock_call():
    call = Mock()
    call.id = "12345"
    call.message = Mock()
    call.message.message_id = 67890
    call.message.id = 67890
    call.message.chat.id = 111222
    call.from_user = Mock()
    call.from_user.username = "testuser"
    call.from_user.first_name = "Test"
    return call


@pytest.fixture(autouse=True)
def clear_navigation():
    navigation.clear(111222)
    yield
    navigation.clear(111222)


def test_handle_client_conf_ru_document_send_error(
    mock_bot,
    mock_call,
    tmp_path,
):
    from handlers.client import menu

    config_file = tmp_path / "rules.conf"
    config_file.write_text("test config")

    with (
        patch.object(menu, "RU_GEO_CONF", str(config_file)),
        patch.object(menu, "send_qr_or_conf"),
        patch.object(
            menu,
            "safe_send_document",
            return_value=False,
        ) as safe_send_document,
    ):
        result = handle_client_conf_ru(
            mock_bot,
            111222,
            mock_call,
            "client:conf_ru:testuser",
        )

    assert result is not None
    safe_send_document.assert_called_once()
    mock_bot.send_document.assert_not_called()


class TestClientHomeCallback:
    def test_client_home_routes_to_navigation_handler(
        self,
        mock_bot,
        mock_call,
    ):
        route = router.resolve("nav:client_home")

        assert route is not None
        assert route.handler is handle_client_navigation_callback
        assert route.access is router.CallbackAccess.CLIENT

        with patch(
            "handlers.client.navigation.render_client_navigation_screen",
            return_value=True,
        ) as mock_render:
            result = handle_client_navigation_callback(
                mock_bot,
                111222,
                mock_call,
                "nav:client_home",
            )

        assert result.text is None
        assert result.show_alert is False
        mock_render.assert_called_once()


class TestClientBackCallback:
    def test_client_back_without_history_opens_home(
        self,
        mock_bot,
        mock_call,
    ):
        with patch(
            "handlers.client.navigation.render_client_navigation_screen",
            return_value=True,
        ) as mock_render:
            result = handle_client_navigation_callback(
                mock_bot,
                111222,
                mock_call,
                "nav:client_back",
            )

        assert result.text is None
        assert result.show_alert is False
        mock_render.assert_called_once()

        screen_id = mock_render.call_args.args[3]
        assert screen_id == "client:home"

    def test_client_back_returns_previous_screen(
        self,
        mock_bot,
        mock_call,
    ):
        navigation.start(111222, "client:home")
        navigation.go(111222, "client:help")

        with patch(
            "handlers.client.navigation.render_client_navigation_screen",
            return_value=True,
        ) as mock_render:
            result = handle_client_navigation_callback(
                mock_bot,
                111222,
                mock_call,
                "nav:client_back",
            )

        assert result.text is None
        assert result.show_alert is False
        mock_render.assert_called_once()
        assert mock_render.call_args.args[3] == "client:home"


class TestClientHelpCallback:
    def test_client_help_opens_help_screen(
        self,
        mock_bot,
        mock_call,
    ):
        with patch(
            "handlers.client.navigation.render_client_navigation_screen",
            return_value=True,
        ) as mock_render:
            result = handle_client_navigation_callback(
                mock_bot,
                111222,
                mock_call,
                "nav:client_help",
            )

        assert result is True
        mock_render.assert_called_once()
        assert mock_render.call_args.args[3] == "client:help"

    def test_render_client_help_vless(
        self,
        mock_bot,
    ):
        with (
            patch(
                "handlers.client.menu.get_client_bindings",
                return_value=["user1"],
            ),
            patch(
                "handlers.client.menu.get_users_list",
                side_effect=lambda proto: ["user1"] if proto == "vless" else [],
            ),
        ):
            result = render_client_help(
                mock_bot,
                111222,
                67890,
            )

        assert result is True
        mock_bot.edit_message_text.assert_called_once()

        text = mock_bot.edit_message_text.call_args.args[0]
        assert "VLESS+Xray" in text
        assert "AmneziaWG" not in text

    def test_render_client_help_vless_and_awg(
        self,
        mock_bot,
    ):
        with (
            patch(
                "handlers.client.menu.get_client_bindings",
                return_value=["user1"],
            ),
            patch(
                "handlers.client.menu.get_users_list",
                return_value=["user1"],
            ),
        ):
            result = render_client_help(
                mock_bot,
                111222,
                67890,
            )

        assert result is True
        mock_bot.edit_message_text.assert_called_once()

        text = mock_bot.edit_message_text.call_args.args[0]
        assert "VLESS+Xray" in text
        assert "AmneziaWG" in text

    def test_render_client_help_awg(
        self,
        mock_bot,
    ):
        with (
            patch(
                "handlers.client.menu.get_client_bindings",
                return_value=["user1"],
            ),
            patch(
                "handlers.client.menu.get_users_list",
                side_effect=lambda proto: ["user1"] if proto == "awg" else [],
            ),
        ):
            result = render_client_help(
                mock_bot,
                111222,
                67890,
            )

        assert result is True
        mock_bot.edit_message_text.assert_called_once()

        text = mock_bot.edit_message_text.call_args.args[0]
        assert "AmneziaWG" in text


class TestClientAccountCallback:
    def test_account_callback_opens_owned_account(
        self,
        mock_bot,
        mock_call,
    ):
        with (
            patch(
                "handlers.client.navigation._is_client_account_owned",
                return_value=True,
            ),
            patch(
                "handlers.client.navigation.render_client_navigation_screen",
                return_value=True,
            ) as mock_render,
        ):
            result = handle_client_navigation_callback(
                mock_bot,
                111222,
                mock_call,
                "client:account:user1",
            )

        assert result is True
        mock_render.assert_called_once()
        assert mock_render.call_args.args[3] == "client:account"

        from handlers.client.navigation import _CLIENT_ACCOUNT_USERS

        assert _CLIENT_ACCOUNT_USERS[111222] == "user1"

    def test_account_callback_rejects_unknown_account(
        self,
        mock_bot,
        mock_call,
    ):
        with patch(
            "handlers.client.navigation._is_client_account_owned",
            return_value=False,
        ):
            result = handle_client_navigation_callback(
                mock_bot,
                111222,
                mock_call,
                "client:account:user1",
            )

        assert result is False
        mock_bot.send_message.assert_called_once_with(
            111222,
            "❌ Клиент не найден.",
        )

    def test_render_client_account_success(
        self,
        mock_bot,
    ):
        with patch(
            "handlers.client.menu.get_client_account_screen",
            return_value=(
                "KB",
                "Account",
                True,
            ),
        ):
            result = render_client_account(
                mock_bot,
                111222,
                67890,
                "user1",
            )

        assert result is True
        mock_bot.edit_message_text.assert_called_once()

    def test_render_client_account_missing(
        self,
        mock_bot,
    ):
        with patch(
            "handlers.client.menu.get_client_account_screen",
            return_value=None,
        ):
            result = render_client_account(
                mock_bot,
                111222,
                67890,
                "user1",
            )

        assert result is False
        mock_bot.send_message.assert_called_once_with(
            111222,
            "❌ Клиент не найден.",
        )


class TestClientStatsCallback:
    def test_stats_callback_routes_to_client_handler(
        self,
        mock_bot,
        mock_call,
    ):
        with patch(
            "handlers.client.navigation.handle_client_stats",
            return_value=True,
        ) as mock_stats:
            result = handle_client_navigation_callback(
                mock_bot,
                111222,
                mock_call,
                "client:stats:user1",
            )

        assert result is True
        mock_stats.assert_called_once_with(
            mock_bot,
            111222,
            mock_call,
            "client:stats:user1",
        )

    def test_stats_unknown_client(
        self,
        mock_bot,
        mock_call,
    ):
        with patch(
            "handlers.client.menu.get_client_protocol",
            return_value=None,
        ):
            result = handle_client_stats(
                mock_bot,
                111222,
                mock_call,
                "client:stats:user1",
            )

        assert result.text == "❌ Клиент не найден"
        assert result.show_alert is False
        mock_bot.answer_callback_query.assert_not_called()

    def test_stats_vless_starts_worker(
        self,
        mock_bot,
        mock_call,
    ):
        with (
            patch(
                "handlers.client.menu.get_client_protocol",
                return_value="vless",
            ),
            patch(
                "handlers.client.menu.get_client_stats_text",
                return_value="Stats",
            ),
            patch(
                "handlers.client.menu.threading.Thread",
            ) as mock_thread,
        ):
            result = handle_client_stats(
                mock_bot,
                111222,
                mock_call,
                "client:stats:user1",
            )

        assert result.text is None
        assert result.show_alert is False
        mock_thread.assert_called_once()

        target = mock_thread.call_args.kwargs["target"]
        target()

        mock_bot.edit_message_text.assert_called_once()


    def test_stats_worker_reports_error(
        self,
        mock_bot,
        mock_call,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "handlers.client.menu.get_client_protocol",
            lambda username: "vless",
        )
        monkeypatch.setattr(
            "handlers.client.menu.get_client_stats_text",
            lambda username, proto: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        class ImmediateThread:
            def __init__(self, target, **kwargs):
                self.target = target

            def start(self):
                self.target()

        monkeypatch.setattr(
            "handlers.client.menu.threading.Thread",
            ImmediateThread,
        )

        result = handle_client_stats(
            mock_bot,
            111222,
            mock_call,
            "client:stats:user1",
        )

        assert result.text is None
        assert mock_bot.edit_message_text.call_count == 1
        assert "❌ Ошибка получения статистики: boom" in (
            mock_bot.edit_message_text.call_args.args[0]
        )


class TestClientConfCallback:
    def test_conf_vless(
        self,
        mock_bot,
        mock_call,
    ):
        with (
            patch(
                "handlers.client.menu.get_client_protocol",
                return_value="vless",
            ),
            patch(
                "handlers.client.menu.send_qr_or_conf",
            ) as mock_send,
        ):
            result = handle_client_conf(
                mock_bot,
                111222,
                mock_call,
                "client:conf:user1",
            )

        assert result.text is None
        assert result.show_alert is False
        mock_send.assert_called_once_with(
            mock_bot,
            111222,
            "user1",
            "vless",
        )

    def test_conf_awg(
        self,
        mock_bot,
        mock_call,
    ):
        with (
            patch(
                "handlers.client.menu.get_client_protocol",
                return_value="awg",
            ),
            patch(
                "handlers.client.menu.send_qr_or_conf",
            ) as mock_send,
        ):
            result = handle_client_conf(
                mock_bot,
                111222,
                mock_call,
                "client:conf:user1",
            )

        assert result.text is None
        assert result.show_alert is False
        mock_send.assert_called_once_with(
            mock_bot,
            111222,
            "user1",
            "awg",
        )

    def test_conf_unknown_client(
        self,
        mock_bot,
        mock_call,
    ):
        with patch(
            "handlers.client.menu.get_client_protocol",
            return_value=None,
        ):
            result = handle_client_conf(
                mock_bot,
                111222,
                mock_call,
                "client:conf:user1",
            )

        assert result.text is None
        assert result.show_alert is False
        mock_bot.send_message.assert_called_once_with(
            111222,
            "❌ Клиент не найден.",
        )


class TestClientConfRuCallback:
    def test_conf_ru_routes_to_handler(
        self,
        mock_bot,
        mock_call,
    ):
        with patch(
            "handlers.client.navigation.handle_client_conf_ru",
            return_value=True,
        ) as mock_conf_ru:
            result = handle_client_navigation_callback(
                mock_bot,
                111222,
                mock_call,
                "client:conf_ru:user1",
            )

        assert result is True
        mock_conf_ru.assert_called_once_with(
            mock_bot,
            111222,
            mock_call,
            "client:conf_ru:user1",
        )

    def test_conf_ru_sends_config(
        self,
        mock_bot,
        mock_call,
    ):
        with (
            patch(
                "handlers.client.menu.os.path.exists",
                return_value=False,
            ),
            patch(
                "handlers.client.menu.send_qr_or_conf",
            ) as mock_send,
        ):
            result = handle_client_conf_ru(
                mock_bot,
                111222,
                mock_call,
                "client:conf_ru:user1",
            )

        assert result.text is None
        assert result.show_alert is False
        mock_send.assert_called_once_with(
            mock_bot,
            111222,
            "user1",
            "vless",
            config_only=True,
        )


class TestUnknownClientCallback:
    def test_unknown_callback_returns_false(
        self,
        mock_bot,
        mock_call,
    ):
        result = handle_client_navigation_callback(
            mock_bot,
            111222,
            mock_call,
            "client:unknown:user1",
        )

        assert result is False


class TestClientRouteRegistry:
    @pytest.mark.parametrize(
        "callback,expected_prefix",
        [
            ("nav:client_home", False),
            ("nav:client_back", False),
            ("nav:client_help", False),
            ("client:account:user1", True),
            ("client:stats:user1", True),
            ("client:conf:user1", True),
            ("client:conf_ru:user1", True),
        ],
    )
    def test_client_route(
        self,
        callback,
        expected_prefix,
    ):
        route = router.resolve(callback)

        assert route is not None
        assert route.handler is handle_client_navigation_callback
        assert route.access is router.CallbackAccess.CLIENT
        assert route.prefix is expected_prefix


class TestClientHomeRenderer:
    def test_render_client_home(self, mock_bot):
        with patch(
            "handlers.client.menu.get_client_menu",
            return_value=("keyboard", "🏠 Главное меню", "screen"),
        ):
            result = render_client_home(
                mock_bot,
                111222,
                67890,
            )

        assert result is True
        mock_bot.edit_message_text.assert_called_once_with(
            "🏠 Главное меню",
            111222,
            67890,
            parse_mode="Markdown",
            reply_markup="keyboard",
        )


class TestClientHelpRendererEdgeCases:
    def test_render_client_help_with_single_binding_string(self, mock_bot):
        with (
            patch(
                "handlers.client.menu.get_client_bindings",
                return_value="user1",
            ),
            patch(
                "handlers.client.menu.get_users_list",
                side_effect=lambda proto: ["user1"] if proto == "awg" else [],
            ),
        ):
            result = render_client_help(
                mock_bot,
                111222,
                67890,
            )

        assert result is True
        text = mock_bot.edit_message_text.call_args.args[0]
        assert "AmneziaWG" in text
        assert "VLESS+Xray" not in text


class TestClientRequestBindCoverage:
    def test_request_bind_rejects_admin(self, mock_bot, mock_call):
        with patch("handlers.client.menu.is_admin", return_value=True):
            result = __import__(
                "handlers.client.menu",
                fromlist=["handle_request_bind"],
            ).handle_request_bind(mock_bot, 111222, mock_call, "client:request_bind")

        assert result.text == "Вы администратор!"
        mock_bot.send_message.assert_not_called()

    def test_request_bind_rejects_already_bound_client(
        self,
        mock_bot,
        mock_call,
    ):
        with (
            patch("handlers.client.menu.is_admin", return_value=False),
            patch("handlers.client.menu.is_client", return_value=True),
        ):
            result = __import__(
                "handlers.client.menu",
                fromlist=["handle_request_bind"],
            ).handle_request_bind(mock_bot, 111222, mock_call, "client:request_bind")

        assert result.text == "Вы уже привязаны!"
        mock_bot.send_message.assert_called_once_with(
            111222,
            "✅ Ваш chat_id: 111222\nВы уже привязаны к клиенту.",
        )

    def test_request_bind_creates_pending_request(
        self,
        mock_bot,
        mock_call,
    ):
        with (
            patch("handlers.client.menu.is_admin", return_value=False),
            patch("handlers.client.menu.is_client", return_value=False),
            patch("handlers.client.menu.add_pending_binding") as mock_add,
            patch(
                "handlers.client.menu.get_pending_bindings",
                return_value={"111222": {"time": "25.08 12:00"}},
            ),
            patch(
                "handlers.client.menu.ADMIN_CHATS",
                [999001, 999002],
            ),
            patch(
                "handlers.client.menu.escape_md",
                side_effect=lambda value: value,
            ),
            patch("handlers.client.menu.datetime") as mock_datetime,
        ):
            mock_datetime.now.return_value.strftime.return_value = "25.08 12:00"

            result = __import__(
                "handlers.client.menu",
                fromlist=["handle_request_bind"],
            ).handle_request_bind(mock_bot, 111222, mock_call, "client:request_bind")

        assert result.text == "Заявка отправлена администратору!"
        mock_add.assert_called_once_with(
            "111222",
            "@testuser",
            "25.08 12:00",
        )
        assert mock_bot.send_message.call_count == 3

        admin_calls = mock_bot.send_message.call_args_list[:2]
        assert admin_calls[0].args[0] == 999001
        assert admin_calls[1].args[0] == 999002

        final_call = mock_bot.send_message.call_args_list[2]
        assert final_call.args[0] == 111222
        assert "Заявка на привязку отправлена администратору." in final_call.args[1]


class TestClientConfRuCoverage:
    def test_conf_ru_sends_geo_rules_when_file_exists(
        self,
        mock_bot,
        mock_call,
    ):
        with (
            patch("handlers.client.menu.send_qr_or_conf") as mock_send,
            patch(
                "handlers.client.menu.os.path.exists",
                return_value=True,
            ),
            patch(
                "handlers.client.menu.open",
                create=True,
            ) as mock_open,
        ):
            mock_file = Mock()
            mock_open.return_value.__enter__.return_value = mock_file

            result = __import__(
                "handlers.client.menu",
                fromlist=["handle_client_conf_ru"],
            ).handle_client_conf_ru(
                mock_bot,
                111222,
                mock_call,
                "client:conf_ru:user1",
            )

        assert result.text is None
        mock_bot.delete_message.assert_called_once_with(111222, 67890)
        mock_send.assert_called_once_with(
            mock_bot,
            111222,
            "user1",
            "vless",
            config_only=True,
        )
        mock_bot.send_document.assert_called_once()
        assert mock_bot.send_document.call_args.args[:2] == (
            111222,
            mock_file,
        )

    def test_conf_ru_handles_send_error(
        self,
        mock_bot,
        mock_call,
    ):
        with (
            patch(
                "handlers.client.menu.send_qr_or_conf",
                side_effect=RuntimeError("send failed"),
            ),
            patch("handlers.client.menu.logger.exception") as mock_log,
        ):
            result = __import__(
                "handlers.client.menu",
                fromlist=["handle_client_conf_ru"],
            ).handle_client_conf_ru(
                mock_bot,
                111222,
                mock_call,
                "client:conf_ru:user1",
            )

        assert result.text is None
        mock_log.assert_called_once()
        mock_bot.send_message.assert_called_once_with(
            111222,
            "❌ Ошибка отправки конфигурации.",
        )
