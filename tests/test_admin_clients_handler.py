"""
Тесты для handlers/admin/clients.py
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

import handlers.admin.clients as clients_module
from handlers.admin.clients import (
    handle_create_client_callback,
    handle_lists_delete_callback,
    handle_qr_config_callback,
    handle_search_callback,
    process_rename_menu,
    process_search_input,
)
from handlers.admin.management import handle_management_part4_callback


@pytest.fixture
def mock_bot():
    bot = Mock()
    bot.edit_message_text = Mock()
    bot.send_message = Mock()
    bot.answer_callback_query = Mock()
    bot.send_photo = Mock()
    bot.send_document = Mock()
    bot.reply_to = Mock()
    bot.register_next_step_handler = Mock()
    return bot


@pytest.fixture
def mock_call():
    call = Mock()
    call.id = "12345"
    call.message = Mock()
    call.message.message_id = 67890
    call.message.chat.id = 111222
    return call


class TestClientsMarkdownEscaping:
    def test_delete_confirmation_escapes_username(self, mock_bot, mock_call):
        handle_lists_delete_callback(
            mock_bot,
            111222,
            mock_call,
            "ask_del:vless:user_test",
        )

        text = mock_bot.edit_message_text.call_args.args[0]
        assert "`user\\_test`" in text

    def test_delete_progress_escapes_username(self, mock_bot, mock_call):
        with patch("handlers.admin.clients.threading.Thread"):
            handle_lists_delete_callback(
                mock_bot,
                111222,
                mock_call,
                "confirm_del:vless:user_test",
            )

        text = mock_bot.edit_message_text.call_args.args[0]
        assert "`user\\_test`" in text

    def test_rename_progress_escapes_names(self, mock_bot):
        message = Mock()
        message.chat.id = 111222
        message.text = "old_test new_test"

        with (
            patch("handlers.admin.clients.bot", mock_bot),
            patch("handlers.admin.clients.is_admin", return_value=True),
            patch("handlers.admin.clients.INPUT_REQUEST_MSGS", {}),
            patch("handlers.admin.clients.safe_delete"),
            patch("handlers.admin.clients.validate_username", return_value=True),
            patch(
                "handlers.admin.clients.get_users_list",
                side_effect=lambda proto: ["old_test"] if proto == "vless" else [],
            ),
            patch("handlers.admin.clients.rename_client"),
            patch("handlers.admin.clients.log_action"),
        ):
            clients_module.process_rename_menu(message)

        text = mock_bot.send_message.call_args_list[0].args[1]
        assert "`old\\_test`" in text
        assert "`new\\_test`" in text


class TestHandleListsDeleteCallback:
    def test_ask_del_confirmation(self, mock_bot, mock_call):
        result = handle_lists_delete_callback(
            mock_bot, 111222, mock_call, "ask_del:vless:user1"
        )
        assert result.text is None
        assert result.show_alert is False
        mock_bot.edit_message_text.assert_called_once()

    def test_confirm_del_vless(self, mock_bot, mock_call):
        with (
            patch("handlers.admin.clients.threading.Thread") as mock_thread,
            patch("handlers.admin.clients.get_users_list", return_value=[]),
            patch("handlers.admin.clients.protocol_list_kb", return_value="KB"),
        ):
            result = handle_lists_delete_callback(
                mock_bot, 111222, mock_call, "confirm_del:vless:user1"
            )
            assert result.text == "⏳ Удаляю..."
            mock_bot.answer_callback_query.assert_not_called()
            mock_thread.assert_called_once()

    def test_confirm_del_awg(self, mock_bot, mock_call):
        with (
            patch("handlers.admin.clients.threading.Thread") as mock_thread,
            patch("handlers.admin.clients.get_users_list", return_value=[]),
            patch("handlers.admin.clients.protocol_list_kb", return_value="KB"),
        ):
            result = handle_lists_delete_callback(
                mock_bot, 111222, mock_call, "confirm_del:awg:user1"
            )
            assert result.text == "⏳ Удаляю..."
            mock_bot.answer_callback_query.assert_not_called()
            mock_thread.assert_called_once()

    def test_client_stats(self, mock_bot, mock_call):
        with patch("handlers.admin.clients.threading.Thread") as mock_thread:
            result = handle_management_part4_callback(
                mock_bot, 111222, mock_call, "stats_vless_user1"
            )
            assert result.text is None
            assert result.show_alert is False
            mock_thread.assert_called_once()

    def test_conf_vless_with_link(self, mock_bot, mock_call):
        with patch(
            "services.client_service.xray_get_link",
            return_value="vless://test@server:443",
        ):
            result = handle_qr_config_callback(
                mock_bot, 111222, mock_call, "conf:vless:user1"
            )

        assert result.text == "📄 Отправляю конфиг для user1"
        mock_bot.answer_callback_query.assert_not_called()
        mock_bot.send_message.assert_called_once()
        assert "vless://test@server:443" in mock_bot.send_message.call_args[0][1]

    def test_conf_vless_no_link(self, mock_bot, mock_call):
        with (
            patch(
                "services.client_service.xray_get_link",
                return_value=None,
            ),
            pytest.raises(ValueError, match="Link not found"),
        ):
            handle_qr_config_callback(mock_bot, 111222, mock_call, "conf:vless:user1")

    def test_conf_awg(self, mock_bot, mock_call):
        with (
            patch(
                "services.client_service.awg_get_config",
                return_value="AWG TEST CONFIG",
            ),
            patch(
                "services.client_service.load_awg_registry",
                return_value={"user1": {"ip": "10.66.66.10"}},
            ),
            patch(
                "services.client_service.subprocess.run",
                side_effect=lambda *args, **kwargs: Path(
                    args[0][args[0].index("-o") + 1]
                ).write_bytes(b"fake qr"),
            ),
            patch(
                "services.client_service.os.path.exists",
                side_effect=lambda path: Path(path).exists(),
            ),
            patch("services.client_service.os.remove"),
        ):
            result = handle_qr_config_callback(
                mock_bot, 111222, mock_call, "conf:awg:user1"
            )

        assert result.text == "📄 Отправляю конфиг для user1"
        mock_bot.answer_callback_query.assert_not_called()
        mock_bot.send_photo.assert_called_once()
        mock_bot.send_document.assert_called_once()

    def test_search_vless(self, mock_bot, mock_call):
        result = handle_search_callback(
            mock_bot,
            111222,
            mock_call,
            "nav:clients_search_vless",
        )
        assert result.text is None
        assert result.show_alert is False
        mock_bot.edit_message_text.assert_called_once()
        mock_bot.register_next_step_handler.assert_called_once()

    def test_search_awg(self, mock_bot, mock_call):
        result = handle_search_callback(
            mock_bot,
            111222,
            mock_call,
            "nav:clients_search_awg",
        )
        assert result.text is None
        assert result.show_alert is False
        mock_bot.edit_message_text.assert_called_once()
        mock_bot.register_next_step_handler.assert_called_once()


class TestHandleCreateClientCallback:
    def test_add_vless(self, mock_bot, mock_call):
        result = handle_create_client_callback(mock_bot, 111222, mock_call, "add_vless")
        assert result.text is None
        assert result.show_alert is False
        mock_bot.edit_message_text.assert_called_once()
        mock_bot.register_next_step_handler.assert_called_once()

    def test_add_awg(self, mock_bot, mock_call):
        result = handle_create_client_callback(mock_bot, 111222, mock_call, "add_awg")
        assert result.text is None
        assert result.show_alert is False
        mock_bot.edit_message_text.assert_called_once()


class TestHandleQrConfigCallback:
    def test_qr_vless(self, mock_bot, mock_call):
        with patch("handlers.admin.clients.send_qr_or_conf") as mock_send:
            result = handle_qr_config_callback(
                mock_bot, 111222, mock_call, "qr:vless:user1"
            )
            assert result.text == "📤 Отправляю для user1"
            mock_bot.answer_callback_query.assert_not_called()
            mock_send.assert_called_once()

    def test_qr_awg(self, mock_bot, mock_call):
        with patch("handlers.admin.clients.send_qr_or_conf") as mock_send:
            result = handle_qr_config_callback(
                mock_bot, 111222, mock_call, "qr:awg:user1"
            )
            assert result.text == "📤 Отправляю для user1"
            mock_bot.answer_callback_query.assert_not_called()
            mock_send.assert_called_once()

    def test_qr_select_both(self, mock_bot, mock_call):
        with (
            patch(
                "handlers.admin.clients.xray_get_link_for_port",
                return_value="vless://test",
            ),
            patch(
                "handlers.admin.clients.get_vless_inbounds",
                return_value=[
                    {"port": 443},
                    {"port": 2096},
                ],
            ),
            patch("handlers.admin.clients.load_xray_config", return_value={}),
            patch("handlers.admin.clients.subprocess.run"),
            patch("handlers.admin.clients.os.remove"),
            patch("builtins.open", MagicMock()),
        ):
            result = handle_qr_config_callback(
                mock_bot, 111222, mock_call, "qr_select_user1_both"
            )
            assert result.text is None
            assert result.show_alert is False
            assert mock_bot.send_photo.call_count == 2

    def test_qr_select_single_port(self, mock_bot, mock_call):
        with (
            patch(
                "handlers.admin.clients.xray_get_link_for_port",
                return_value="vless://test",
            ),
            patch(
                "handlers.admin.clients.get_vless_inbounds",
                return_value=[
                    {"port": 443},
                    {"port": 2096},
                ],
            ),
            patch("handlers.admin.clients.load_xray_config", return_value={}),
            patch("handlers.admin.clients.subprocess.run"),
            patch("handlers.admin.clients.os.remove"),
            patch("builtins.open", MagicMock()),
        ):
            result = handle_qr_config_callback(
                mock_bot, 111222, mock_call, "qr_select_user1*443"
            )
            assert result.text is None
            assert result.show_alert is False
            mock_bot.send_photo.assert_called_once()


class TestVlessLinkParsing:
    def test_conf_vless_with_port_443(self, mock_bot, mock_call):
        fake_link = "vless://none:123@server.com:443?type=tcp#test"
        with (
            patch("services.client_service.xray_get_link", return_value=fake_link),
        ):
            result = handle_qr_config_callback(
                mock_bot, 111222, mock_call, "conf:vless:user1"
            )
            assert result.text == "📄 Отправляю конфиг для user1"
            mock_bot.answer_callback_query.assert_not_called()
            call_args = mock_bot.send_message.call_args[0][1]
            assert "📱 VLESS 443" in call_args
            assert fake_link in call_args

    def test_conf_vless_with_port_2096(self, mock_bot, mock_call):
        fake_link = "vless://none:123@server.com:2096?type=tcp#test"
        with (
            patch("services.client_service.xray_get_link", return_value=fake_link),
        ):
            result = handle_qr_config_callback(
                mock_bot, 111222, mock_call, "conf:vless:user1"
            )
            assert result.text == "📄 Отправляю конфиг для user1"
            mock_bot.answer_callback_query.assert_not_called()
            call_args = mock_bot.send_message.call_args[0][1]
            assert "📱 VLESS 2096" in call_args
            assert fake_link in call_args

    def test_conf_vless_with_unknown_port(self, mock_bot, mock_call):
        fake_link = "vless://uuid@server.com:8443?type=tcp#test"
        with (
            patch("services.client_service.xray_get_link", return_value=fake_link),
        ):
            result = handle_qr_config_callback(
                mock_bot, 111222, mock_call, "conf:vless:user1"
            )
            assert result.text == "📄 Отправляю конфиг для user1"
            mock_bot.answer_callback_query.assert_not_called()
            call_args = mock_bot.send_message.call_args[0][1]
            assert "VLESS 8443" in call_args
            assert fake_link in call_args
            assert fake_link in call_args

    def test_conf_vless_with_invalid_base64(self, mock_bot, mock_call):
        fake_link = "vless://uuid@server.com:443?type=tcp#test"
        with (
            patch("services.client_service.xray_get_link", return_value=fake_link),
        ):
            result = handle_qr_config_callback(
                mock_bot, 111222, mock_call, "conf:vless:user1"
            )
            assert result.text == "📄 Отправляю конфиг для user1"
            mock_bot.answer_callback_query.assert_not_called()
            call_args = mock_bot.send_message.call_args[0][1]
            assert "📱 VLESS 443" in call_args
            assert fake_link in call_args
            assert fake_link in call_args


class TestProcessRename:
    def _patch_bot(self, mock_bot):

        self._original_bot = clients_module.bot
        clients_module.bot = mock_bot

    def _unpatch_bot(self):

        clients_module.bot = self._original_bot

    def test_process_rename_wrong_format(self, mock_bot):
        message = Mock()
        message.chat.id = 111222
        message.text = "only_one_arg"
        self._patch_bot(mock_bot)
        try:
            with (
                patch("handlers.admin.clients.is_admin", return_value=True),
                patch("handlers.admin.clients.INPUT_REQUEST_MSGS", {}),
                patch("handlers.admin.clients.safe_delete"),
            ):
                process_rename_menu(message)
                mock_bot.reply_to.assert_called_once()
                assert "Формат" in mock_bot.reply_to.call_args[0][1]
        finally:
            self._unpatch_bot()

    def test_process_rename_invalid_username(self, mock_bot):
        message = Mock()
        message.chat.id = 111222
        message.text = "old new@invalid"
        self._patch_bot(mock_bot)
        try:
            with (
                patch("handlers.admin.clients.is_admin", return_value=True),
                patch("handlers.admin.clients.INPUT_REQUEST_MSGS", {}),
                patch("handlers.admin.clients.safe_delete"),
                patch("handlers.admin.clients.validate_username", return_value=False),
            ):
                process_rename_menu(message)
                mock_bot.reply_to.assert_called_once()
                assert "только латиница" in mock_bot.reply_to.call_args[0][1]
        finally:
            self._unpatch_bot()

    def test_process_rename_old_not_found(self, mock_bot):
        message = Mock()
        message.chat.id = 111222
        message.text = "old new"
        self._patch_bot(mock_bot)
        try:
            with (
                patch("handlers.admin.clients.is_admin", return_value=True),
                patch("handlers.admin.clients.INPUT_REQUEST_MSGS", {}),
                patch("handlers.admin.clients.safe_delete"),
                patch("handlers.admin.clients.validate_username", return_value=True),
                patch("handlers.admin.clients.get_users_list", return_value=[]),
            ):
                process_rename_menu(message)
                mock_bot.reply_to.assert_called_once()
                assert "не найден" in mock_bot.reply_to.call_args[0][1]
        finally:
            self._unpatch_bot()

    def test_process_rename_new_already_exists(self, mock_bot):
        message = Mock()
        message.chat.id = 111222
        message.text = "old new"
        self._patch_bot(mock_bot)
        try:
            with (
                patch("handlers.admin.clients.is_admin", return_value=True),
                patch("handlers.admin.clients.INPUT_REQUEST_MSGS", {}),
                patch("handlers.admin.clients.safe_delete"),
                patch("handlers.admin.clients.validate_username", return_value=True),
                patch("handlers.admin.clients.get_users_list") as mock_cache,
            ):
                mock_cache.side_effect = lambda proto: (
                    ["old", "new"] if proto == "vless" else []
                )
                process_rename_menu(message)
                mock_bot.reply_to.assert_called_once()
                assert "уже занято" in mock_bot.reply_to.call_args[0][1]
        finally:
            self._unpatch_bot()

    def test_process_rename_success(self, mock_bot):
        message = Mock()
        message.chat.id = 111222
        message.text = "old new"
        self._patch_bot(mock_bot)
        try:
            with (
                patch("handlers.admin.clients.is_admin", return_value=True),
                patch("handlers.admin.clients.INPUT_REQUEST_MSGS", {}),
                patch("handlers.admin.clients.safe_delete"),
                patch("handlers.admin.clients.validate_username", return_value=True),
                patch("handlers.admin.clients.get_users_list") as mock_cache,
                patch("handlers.admin.clients.rename_client", return_value=None),
                patch("handlers.admin.clients.log_action") as mock_log,
                patch("handlers.admin.clients.main_menu_kb", return_value="KB"),
                patch(
                    "handlers.admin.navigation.render_navigation_screen",
                    return_value=True,
                ) as mock_render,
            ):
                mock_cache.side_effect = lambda proto: (
                    ["old"] if proto == "vless" else []
                )

                input_messages = {
                    111222: 67890,
                }

                with patch(
                    "handlers.admin.clients.INPUT_REQUEST_MSGS",
                    input_messages,
                ):
                    process_rename_menu(message)

                mock_bot.reply_to.assert_not_called()

                # 1. Progress отправляется отдельным сообщением.
                assert mock_bot.send_message.call_count == 2
                assert "Переименовываю" in mock_bot.send_message.call_args_list[0][0][1]

                # 2. Старое окно ввода превращается в SUCCESS.
                mock_bot.edit_message_text.assert_called_once_with(
                    "✅ Успешно переименовано: old → new",
                    111222,
                    67890,
                )

                # 3. После SUCCESS отправляется новое меню.
                menu_call = mock_bot.send_message.call_args_list[1]
                assert menu_call[0][1] == "👥 *Клиенты*"
                assert menu_call[1]["parse_mode"] == "Markdown"

                mock_log.assert_called_once()

                mock_render.assert_not_called()
                assert input_messages == {}
        finally:
            self._unpatch_bot()

    def test_process_rename_with_errors(self, mock_bot):
        message = Mock()
        message.chat.id = 111222
        message.text = "old new"
        self._patch_bot(mock_bot)
        try:
            with (
                patch("handlers.admin.clients.is_admin", return_value=True),
                patch("handlers.admin.clients.INPUT_REQUEST_MSGS", {}),
                patch("handlers.admin.clients.safe_delete"),
                patch("handlers.admin.clients.validate_username", return_value=True),
                patch("handlers.admin.clients.get_users_list") as mock_cache,
                patch(
                    "handlers.admin.clients.rename_client",
                    return_value=["Ошибка 1", "Ошибка 2"],
                ),
            ):
                mock_cache.side_effect = lambda proto: (
                    ["old"] if proto == "vless" else []
                )
                process_rename_menu(message)
                mock_bot.reply_to.assert_not_called()
                assert mock_bot.send_message.call_count == 2
                assert "Переименовываю" in mock_bot.send_message.call_args_list[0][0][1]
                assert "Частично" in mock_bot.send_message.call_args_list[1][0][1]
        finally:
            self._unpatch_bot()


def test_qr_select_invalid_port_raises(mock_bot, mock_call):
    with pytest.raises(ValueError, match="Invalid QR port"):
        handle_qr_config_callback(
            mock_bot,
            111222,
            mock_call,
            "qr_select_user1*abc",
        )


def test_qr_callback_invalid_format(mock_bot, mock_call):
    result = handle_qr_config_callback(
        mock_bot,
        111222,
        mock_call,
        "qr:vless",
    )

    assert result.text == "❌ Некорректный QR callback"
    mock_bot.answer_callback_query.assert_not_called()


def test_qr_callback_unknown_protocol(mock_bot, mock_call):
    result = handle_qr_config_callback(
        mock_bot,
        111222,
        mock_call,
        "qr:unknown:user1",
    )

    assert result.text == "❌ Неизвестный протокол"
    mock_bot.answer_callback_query.assert_not_called()


def test_conf_callback_invalid_format(mock_bot, mock_call):
    result = handle_qr_config_callback(
        mock_bot,
        111222,
        mock_call,
        "conf:vless",
    )

    assert result.text == "❌ Некорректный config callback"
    mock_bot.answer_callback_query.assert_not_called()


def test_conf_callback_unknown_protocol(mock_bot, mock_call):
    result = handle_qr_config_callback(
        mock_bot,
        111222,
        mock_call,
        "conf:unknown:user1",
    )

    assert result.text == "❌ Неизвестный протокол"
    mock_bot.answer_callback_query.assert_not_called()


def test_confirm_delete_handles_service_error(mock_bot, mock_call):
    def make_thread(*args, **kwargs):
        thread = Mock()
        thread.start.side_effect = kwargs["target"]
        return thread

    with (
        patch(
            "handlers.admin.clients.delete_client_service",
            side_effect=RuntimeError("delete failed"),
        ),
        patch(
            "handlers.admin.clients.threading.Thread",
            side_effect=make_thread,
        ),
    ):
        result = handle_lists_delete_callback(
            mock_bot,
            111222,
            mock_call,
            "confirm_del:vless:user1",
        )

    assert result.text == "⏳ Удаляю..."
    mock_bot.answer_callback_query.assert_not_called()
    mock_bot.edit_message_text.assert_any_call(
        "❌ delete failed",
        111222,
        mock_call.message.message_id,
    )


def test_confirm_delete_success(mock_bot, mock_call):
    def make_thread(*args, **kwargs):
        thread = Mock()
        thread.start.side_effect = kwargs["target"]
        return thread

    with (
        patch(
            "handlers.admin.clients.delete_client_service",
        ),
        patch(
            "handlers.admin.clients.get_users_list",
            return_value=["user2"],
        ),
        patch(
            "handlers.admin.clients.protocol_list_kb",
            return_value="CLIENTS_KB",
        ),
        patch(
            "handlers.admin.clients.log_action",
        ),
        patch(
            "handlers.admin.clients.threading.Thread",
            side_effect=make_thread,
        ),
    ):
        result = handle_lists_delete_callback(
            mock_bot,
            111222,
            mock_call,
            "confirm_del:vless:user1",
        )

    assert result.text == "⏳ Удаляю..."
    mock_bot.answer_callback_query.assert_not_called()
    mock_bot.edit_message_text.assert_any_call(
        "✅ `user1` успешно удалён",
        111222,
        mock_call.message.message_id,
        parse_mode="Markdown",
        reply_markup="CLIENTS_KB",
    )


def test_handle_lists_delete_callback_returns_false_for_unknown_data(
    mock_bot, mock_call
):
    result = handle_lists_delete_callback(
        mock_bot,
        111222,
        mock_call,
        "unknown_callback",
    )

    assert result is False


def test_render_vless_screen_delegates_to_protocol_renderer(mock_bot):
    with patch(
        "handlers.admin.clients.render_protocol_screen",
        return_value="VLESS_SCREEN",
    ) as render:
        result = clients_module._render_vless_screen(mock_bot, 111222, 67890)

    assert result == "VLESS_SCREEN"
    render.assert_called_once_with(mock_bot, 111222, 67890, "vless")


def test_render_awg_screen_delegates_to_protocol_renderer(mock_bot):
    with patch(
        "handlers.admin.clients.render_protocol_screen",
        return_value="AWG_SCREEN",
    ) as render:
        result = clients_module._render_awg_screen(mock_bot, 111222, 67890)

    assert result == "AWG_SCREEN"
    render.assert_called_once_with(mock_bot, 111222, 67890, "awg")


def test_handle_search_callback_returns_false_for_unknown_data(mock_bot, mock_call):
    result = handle_search_callback(
        mock_bot,
        111222,
        mock_call,
        "unknown_callback",
    )

    assert result is False


def test_process_search_input_ignores_non_admin(mock_bot):
    import handlers.admin.clients as clients_module

    message = Mock()
    message.chat.id = 111222

    with patch("handlers.admin.clients.is_admin", return_value=False):
        clients_module.bot = mock_bot
        process_search_input(message, "vless")

    mock_bot.send_message.assert_not_called()


def test_process_search_input_sends_filtered_clients(mock_bot):
    import handlers.admin.clients as clients_module

    message = Mock()
    message.chat.id = 111222
    message.text = "USER"

    with (
        patch("handlers.admin.clients.is_admin", return_value=True),
        patch(
            "handlers.admin.clients.get_users_list",
            return_value=["user1", "other", "testuser"],
        ),
        patch(
            "handlers.admin.clients.protocol_list_kb",
            return_value="CLIENTS_KB",
        ),
        patch(
            "handlers.admin.clients.safe_delete",
        ) as safe_delete,
    ):
        clients_module.bot = mock_bot
        clients_module.INPUT_REQUEST_MSGS[111222] = 999
        process_search_input(message, "vless")

    safe_delete.assert_called_once_with(mock_bot, 111222, 999)
    mock_bot.send_message.assert_called_once_with(
        111222,
        "🔍 Найдено 2 клиентов:",
        reply_markup="CLIENTS_KB",
    )


def test_process_search_input_sends_not_found_message(mock_bot):
    import handlers.admin.clients as clients_module

    message = Mock()
    message.chat.id = 111222
    message.text = "missing"

    with (
        patch("handlers.admin.clients.is_admin", return_value=True),
        patch(
            "handlers.admin.clients.get_users_list",
            return_value=["user1", "other"],
        ),
    ):
        clients_module.bot = mock_bot
        process_search_input(message, "vless")

    mock_bot.send_message.assert_called_once()
    args = mock_bot.send_message.call_args.args
    assert args[0] == 111222
    assert "❌ Клиенты не найдены по запросу 'missing'" in args[1]


def test_process_search_input_handles_delete_error_and_no_results(mock_bot):
    message = Mock()
    message.chat.id = 111222
    message.text = "missing"

    with (
        patch("handlers.admin.clients.is_admin", return_value=True),
        patch(
            "handlers.admin.clients.get_users_list",
            return_value=[],
        ),
        patch(
            "handlers.admin.clients.safe_delete",
            side_effect=RuntimeError("delete failed"),
        ),
        patch("handlers.admin.clients.logger.exception") as log_exception,
    ):
        clients_module.bot = mock_bot
        clients_module.INPUT_REQUEST_MSGS[111222] = 999

        process_search_input(message, "vless")

    log_exception.assert_called_once()
    mock_bot.send_message.assert_called_once()
    assert "❌ Клиенты не найдены" in mock_bot.send_message.call_args[0][1]


def test_handle_create_client_callback_returns_false_for_unknown_data(
    mock_bot, mock_call
):
    result = handle_create_client_callback(
        mock_bot,
        111222,
        mock_call,
        "unknown_callback",
    )

    assert result is False


def test_qr_select_default_covers_missing_link_extra_port_and_cleanup(
    mock_bot, mock_call
):
    links = {
        443: "vless://first",
        2096: None,
        8443: "vless://third",
    }

    with (
        patch(
            "handlers.admin.clients.xray_get_link_for_port",
            side_effect=lambda username, port: links[port],
        ),
        patch(
            "handlers.admin.clients.get_vless_inbounds",
            return_value=[
                {"port": 443},
                {"port": 2096},
                {"port": 8443},
            ],
        ),
        patch("handlers.admin.clients.load_xray_config", return_value={}),
        patch("handlers.admin.clients.subprocess.run") as run,
        patch(
            "handlers.admin.clients.os.path.exists",
            return_value=True,
        ),
        patch("handlers.admin.clients.os.remove") as remove,
        patch("builtins.open", MagicMock()),
    ):
        result = handle_qr_config_callback(
            mock_bot,
            111222,
            mock_call,
            "qr_select_user1",
        )

    assert result.text is None
    assert result.show_alert is False
    assert run.call_count == 2
    assert remove.call_count == 2
    assert mock_bot.send_photo.call_count == 2

    captions = [call.kwargs["caption"] for call in mock_bot.send_photo.call_args_list]

    assert "📱 Оператор: MTS/Megafon/Tele2" in captions[0]
    assert "📱 VLESS:8443" in captions[1]


def test_handle_qr_config_callback_returns_false_for_unknown_data(mock_bot, mock_call):
    result = handle_qr_config_callback(
        mock_bot,
        111222,
        mock_call,
        "unknown_callback",
    )

    assert result is False
