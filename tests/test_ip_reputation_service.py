"""
Тесты services/network/ip_reputation.py.
"""

from unittest.mock import Mock, patch

import requests

from services.network.ip_reputation import check_ip_reputation


class TestCheckIPReputation:
    """Тесты проверки репутации IP."""

    def test_returns_error_when_api_key_is_not_configured(self):
        with (
            patch(
                "services.network.ip_reputation.ABUSEIPDB_API_KEY",
                "",
            ),
            patch(
                "services.network.ip_reputation.logger.error",
            ) as mock_error,
        ):
            result = check_ip_reputation("1.2.3.4")

        assert result == {"error": "API ключ не настроен"}
        mock_error.assert_called_once_with("ip_reputation.config.api_key_missing")

    def test_uses_explicit_ip_and_returns_parsed_result(self):
        response = Mock()
        response.json.return_value = {
            "data": {
                "ipAddress": "8.8.8.8",
                "countryCode": "US",
                "isp": "Google LLC",
                "usageType": "Data Center/Web/Transit",
                "abuseConfidenceScore": 5,
                "totalReports": 2,
                "isWhitelisted": False,
                "lastReportedAt": "2026-08-20T12:00:00+00:00",
            }
        }

        with (
            patch(
                "services.network.ip_reputation.ABUSEIPDB_API_KEY",
                "test-api-key",
            ),
            patch(
                "services.network.ip_reputation.requests.get",
                return_value=response,
            ) as mock_get,
            patch(
                "services.network.ip_reputation.logger.info",
            ) as mock_info,
        ):
            result = check_ip_reputation("8.8.8.8")

        mock_get.assert_called_once_with(
            "https://api.abuseipdb.com/api/v2/check",
            headers={
                "Accept": "application/json",
                "Key": "test-api-key",
            },
            params={
                "ipAddress": "8.8.8.8",
                "maxAgeInDays": "90",
            },
            timeout=10,
        )
        response.raise_for_status.assert_called_once_with()

        assert result == {
            "ip": "8.8.8.8",
            "country": "US",
            "isp": "Google LLC",
            "usageType": "Data Center/Web/Transit",
            "abuseConfidenceScore": 5,
            "totalReports": 2,
            "isWhitelisted": False,
            "lastReportedAt": "2026-08-20T12:00:00+00:00",
        }

        mock_info.assert_called_once_with(
            "ip_reputation.check.completed | ip=%s | score=%s | reports=%s",
            "8.8.8.8",
            5,
            2,
        )

    def test_uses_server_ip_when_ip_is_not_provided(self):
        response = Mock()
        response.json.return_value = {
            "data": {
                "ipAddress": "203.0.113.10",
            }
        }

        with (
            patch(
                "services.network.ip_reputation.ABUSEIPDB_API_KEY",
                "test-api-key",
            ),
            patch(
                "services.network.ip_reputation.SERVER_IP",
                "203.0.113.10",
            ),
            patch(
                "services.network.ip_reputation.requests.get",
                return_value=response,
            ) as mock_get,
        ):
            result = check_ip_reputation()

        assert result["ip"] == "203.0.113.10"
        assert mock_get.call_args.kwargs["params"]["ipAddress"] == "203.0.113.10"

    def test_returns_error_on_request_exception(self):
        error = requests.exceptions.Timeout("request timed out")

        with (
            patch(
                "services.network.ip_reputation.ABUSEIPDB_API_KEY",
                "test-api-key",
            ),
            patch(
                "services.network.ip_reputation.requests.get",
                side_effect=error,
            ),
            patch(
                "services.network.ip_reputation.logger.error",
            ) as mock_error,
        ):
            result = check_ip_reputation("1.2.3.4")

        assert result == {"error": "request timed out"}
        mock_error.assert_called_once_with(
            "ip_reputation.check.failed | ip=%s | error=%s",
            "1.2.3.4",
            error,
        )

    def test_uses_defaults_for_missing_optional_response_fields(self):
        response = Mock()
        response.json.return_value = {
            "data": {
                "ipAddress": "1.2.3.4",
            }
        }

        with (
            patch(
                "services.network.ip_reputation.ABUSEIPDB_API_KEY",
                "test-api-key",
            ),
            patch(
                "services.network.ip_reputation.requests.get",
                return_value=response,
            ),
        ):
            result = check_ip_reputation("1.2.3.4")

        assert result == {
            "ip": "1.2.3.4",
            "country": None,
            "isp": None,
            "usageType": None,
            "abuseConfidenceScore": 0,
            "totalReports": 0,
            "isWhitelisted": False,
            "lastReportedAt": None,
        }
