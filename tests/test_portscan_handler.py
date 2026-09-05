"""
Тесты для handlers/features/portscan.py
Проверяют canonical navigation flow:
callback -> navigation.go -> navigation.render.
"""

from unittest.mock import Mock, patch

import pytest

from handlers.features.portscan import handle_portscan_callback, render_port_scan


@pytest.fixture
def mock_bot():
    bot = Mock()
    bot.edit_message_text = Mock()
    bot.answer_callback_query = Mock()
    return bot


@pytest.fixture
def mock_call():
    call = Mock()
    call.id = "12345"
    call.message = Mock()
    call.message.message_id = 67890
    call.message.chat.id = 111222
    return call


class TestHandlePortscanCallback:
    """Тесты navigation callback."""

    def test_port_scan_returns_true(self, mock_bot, mock_call):
        with patch("handlers.features.portscan.navigation") as mock_navigation:
            mock_navigation.current.return_value = "some_screen"

            result = handle_portscan_callback(mock_bot, 111222, mock_call, "port_scan")

            assert result.text == "Сканирую порты..."
            assert result.show_alert is False
            mock_navigation.go.assert_called_once_with(111222, "port_scan")
            mock_navigation.render.assert_called_once_with(
                "port_scan", mock_bot, 111222, 67890
            )

    def test_port_scan_does_not_go_if_already_current(self, mock_bot, mock_call):
        with patch("handlers.features.portscan.navigation") as mock_navigation:
            mock_navigation.current.return_value = "port_scan"

            result = handle_portscan_callback(mock_bot, 111222, mock_call, "port_scan")

            assert result.text == "Сканирую порты..."
            assert result.show_alert is False
            mock_navigation.go.assert_not_called()
            mock_navigation.render.assert_called_once_with(
                "port_scan", mock_bot, 111222, 67890
            )

    def test_port_scan_returns_callback_response(self, mock_bot, mock_call):
        with patch("handlers.features.portscan.navigation"):
            result = handle_portscan_callback(mock_bot, 111222, mock_call, "port_scan")

        assert result.text == "Сканирую порты..."
        assert result.show_alert is False
        mock_bot.answer_callback_query.assert_not_called()

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        result = handle_portscan_callback(mock_bot, 111222, mock_call, "unknown_action")

        assert result is False


class TestRenderPortScan:
    """Тесты renderer."""

    def test_render_calls_scan(self, mock_bot):
        with patch(
            "handlers.features.portscan.scan_open_ports",
            return_value="📊 Результаты",
        ) as mock_scan:
            render_port_scan(mock_bot, 111222, 67890)

        mock_scan.assert_called_once()
        mock_bot.edit_message_text.assert_called_once()

    def test_render_uses_message_id(self, mock_bot):
        with patch(
            "handlers.features.portscan.scan_open_ports",
            return_value="📊 Результаты",
        ):
            render_port_scan(mock_bot, 111222, 67890)

        args = mock_bot.edit_message_text.call_args.args
        assert args[0] == "📊 Результаты"
        assert args[1] == 111222
        assert args[2] == 67890

    def test_render_handles_message_not_modified(self, mock_bot):
        mock_bot.edit_message_text.side_effect = Exception("message is not modified")

        with patch(
            "handlers.features.portscan.scan_open_ports",
            return_value="📊 Результаты",
        ):
            result = render_port_scan(mock_bot, 111222, 67890)

        assert result is True

    def test_render_logs_other_exception(self, mock_bot):
        mock_bot.edit_message_text.side_effect = Exception("Other error")

        with (
            patch(
                "handlers.features.portscan.scan_open_ports",
                return_value="📊 Результаты",
            ),
            patch("handlers.features.portscan.logger") as mock_logger,
        ):
            result = render_port_scan(mock_bot, 111222, 67890)

        assert result is True
        mock_logger.error.assert_called_once()
