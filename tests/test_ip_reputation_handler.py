"""
Тесты для handlers/features/ip_reputation.py
Проверяют canonical navigation flow:
callback -> navigation.go -> navigation.render.
"""

from unittest.mock import Mock, patch

import pytest

from handlers.features.ip_reputation import (
    handle_ip_reputation_callback,
    render_ip_reputation,
)


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


class TestHandleIPReputationCallback:
    """Тесты navigation callback."""

    def test_ip_reputation_returns_true(self, mock_bot, mock_call):
        with patch("handlers.features.ip_reputation.navigation") as mock_navigation:
            mock_navigation.current.return_value = "some_screen"

            result = handle_ip_reputation_callback(
                mock_bot, 111222, mock_call, "ip_reputation"
            )

            assert result.text == "Проверяю репутацию IP..."
            assert result.show_alert is False
            mock_navigation.go.assert_called_once_with(111222, "ip_reputation")
            mock_navigation.render.assert_called_once_with(
                "ip_reputation", mock_bot, 111222, 67890
            )

    def test_ip_reputation_does_not_go_if_already_current(self, mock_bot, mock_call):
        with patch("handlers.features.ip_reputation.navigation") as mock_navigation:
            mock_navigation.current.return_value = "ip_reputation"

            result = handle_ip_reputation_callback(
                mock_bot, 111222, mock_call, "ip_reputation"
            )

            assert result.text == "Проверяю репутацию IP..."
            assert result.show_alert is False
            mock_navigation.go.assert_not_called()
            mock_navigation.render.assert_called_once_with(
                "ip_reputation", mock_bot, 111222, 67890
            )

    def test_ip_reputation_returns_callback_response(self, mock_bot, mock_call):
        with patch("handlers.features.ip_reputation.navigation"):
            result = handle_ip_reputation_callback(
                mock_bot, 111222, mock_call, "ip_reputation"
            )

        assert result.text == "Проверяю репутацию IP..."
        assert result.show_alert is False
        mock_bot.answer_callback_query.assert_not_called()

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        result = handle_ip_reputation_callback(
            mock_bot, 111222, mock_call, "unknown_action"
        )

        assert result is False


class TestRenderIPReputation:
    """Тесты renderer."""

    def test_render_success(self, mock_bot):
        result = {
            "ip": "1.2.3.4",
            "country": "RU",
            "isp": "Test ISP",
            "usageType": "Data Center",
            "abuseConfidenceScore": 0,
            "totalReports": 0,
            "isWhitelisted": False,
            "lastReportedAt": "Нет данных",
        }

        with patch(
            "handlers.features.ip_reputation.check_ip_reputation",
            return_value=result,
        ):
            render_ip_reputation(mock_bot, 111222, 67890)

        mock_bot.edit_message_text.assert_called_once()

    def test_render_error(self, mock_bot):
        with patch(
            "handlers.features.ip_reputation.check_ip_reputation",
            return_value={"error": "API unavailable"},
        ):
            result = render_ip_reputation(mock_bot, 111222, 67890)

        assert result is not None
        mock_bot.edit_message_text.assert_called_once()
        assert "API unavailable" in mock_bot.edit_message_text.call_args.args[0]


@pytest.mark.parametrize(
    ("score", "status", "emoji"),
    [
        (10, "⚠️ Низкий риск", "🟡"),
        (25, "⚠️ Средний риск", "🟠"),
        (50, "🚨 Высокий риск", "🔴"),
    ],
)
def test_render_risk_levels(mock_bot, score, status, emoji):
    result = {
        "ip": "1.2.3.4",
        "abuseConfidenceScore": score,
        "totalReports": 1,
        "isWhitelisted": False,
    }

    with patch(
        "handlers.features.ip_reputation.check_ip_reputation",
        return_value=result,
    ):
        render_ip_reputation(mock_bot, 111222, 67890)

    text = mock_bot.edit_message_text.call_args.args[0]
    assert f"{emoji} **Статус:** {status}" in text


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (25, "Умеренный риск"),
        (50, "Высокий риск блокировки"),
    ],
)
def test_render_risk_recommendation(mock_bot, score, expected):
    result = {
        "ip": "1.2.3.4",
        "abuseConfidenceScore": score,
        "totalReports": 1,
        "isWhitelisted": False,
    }

    with patch(
        "handlers.features.ip_reputation.check_ip_reputation",
        return_value=result,
    ):
        render_ip_reputation(mock_bot, 111222, 67890)

    text = mock_bot.edit_message_text.call_args.args[0]
    assert expected in text


def test_render_whitelisted_overrides_status(mock_bot):
    result = {
        "ip": "1.2.3.4",
        "abuseConfidenceScore": 80,
        "totalReports": 20,
        "isWhitelisted": True,
    }

    with patch(
        "handlers.features.ip_reputation.check_ip_reputation",
        return_value=result,
    ):
        render_ip_reputation(mock_bot, 111222, 67890)

    text = mock_bot.edit_message_text.call_args.args[0]
    assert "🟢 **Статус:** ✅ В белом списке" in text
