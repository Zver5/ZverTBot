import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services.vps_monitor import (
    CRITICAL_COMPONENTS,
    DATA_COLLECTORS,
    OPTIONAL_COMPONENTS,
    ExternalHttpMonitor,
    MonitorCategory,
    MonitorFailure,
    MonitorResult,
    MonitorState,
    StateTransition,
    check_all,
    check_awg_service,
    check_backup,
    check_external_monitor,
    check_external_monitors,
    check_fail2ban,
    check_long_running_service,
    check_ssh,
    check_stats_http,
    check_xray,
    component_category,
    transition_state,
)


def completed(stdout="", returncode=0):
    return type(
        "Completed",
        (),
        {"stdout": stdout, "returncode": returncode},
    )()


def test_monitoring_classification_is_fixed():
    assert CRITICAL_COMPONENTS == {"zvertbot", "stats-http"}
    assert OPTIONAL_COMPONENTS == {
        "backup",
        "xray",
        "awg",
        "ssh",
        "fail2ban",
    }
    assert DATA_COLLECTORS == {
        "xray-traffic-collect",
        "geoip-collect",
    }


@pytest.mark.parametrize(
    ("name", "category"),
    [
        ("zvertbot", MonitorCategory.CRITICAL),
        ("stats-http", MonitorCategory.CRITICAL),
        ("backup", MonitorCategory.OPTIONAL),
        ("xray", MonitorCategory.OPTIONAL),
        ("awg", MonitorCategory.OPTIONAL),
        ("ssh", MonitorCategory.OPTIONAL),
        ("fail2ban", MonitorCategory.OPTIONAL),
        ("xray-traffic-collect", MonitorCategory.DATA_COLLECTOR),
        ("geoip-collect", MonitorCategory.DATA_COLLECTOR),
    ],
)
def test_component_category(name, category):
    assert component_category(name) == category


def test_unknown_component_is_rejected():
    with pytest.raises(ValueError, match="Unknown monitoring component"):
        component_category("unknown")


@pytest.mark.parametrize(
    ("previous", "healthy", "current", "notify"),
    [
        (MonitorState.UP, True, MonitorState.UP, False),
        (MonitorState.UP, False, MonitorState.DOWN, True),
        (MonitorState.DOWN, False, MonitorState.DOWN, False),
        (MonitorState.DOWN, True, MonitorState.UP, True),
    ],
)
def test_state_transition(previous, healthy, current, notify):
    assert transition_state(previous, healthy) == StateTransition(
        previous,
        current,
        notify,
    )


def test_monitor_result_preserves_details():
    result = MonitorResult(
        name="backup",
        category=MonitorCategory.OPTIONAL,
        healthy=False,
        details="last run failed",
    )

    assert result.name == "backup"
    assert result.category == MonitorCategory.OPTIONAL
    assert result.healthy is False
    assert result.details == "last run failed"


@patch("services.vps_monitor._systemctl")
def test_long_running_active_service_is_healthy(mock_systemctl):
    mock_systemctl.side_effect = [
        completed("stats-http.service enabled\n"),
        completed("active\n"),
    ]

    result = check_long_running_service(
        "stats-http",
        MonitorCategory.CRITICAL,
    )

    assert result.healthy is True
    assert result.details == "active"


@patch("services.vps_monitor._systemctl")
def test_long_running_inactive_critical_service_is_down(mock_systemctl):
    mock_systemctl.side_effect = [
        completed("zvertbot.service enabled\n"),
        completed("inactive\n"),
    ]

    result = check_long_running_service(
        "zvertbot",
        MonitorCategory.CRITICAL,
    )

    assert result.healthy is False
    assert "inactive" in result.details


@patch("services.vps_monitor._systemctl")
def test_missing_optional_service_is_healthy(mock_systemctl):
    mock_systemctl.return_value = completed("")

    result = check_long_running_service(
        "xray",
        MonitorCategory.OPTIONAL,
    )

    assert result.healthy is True
    assert result.details == "service not installed"


@patch("services.vps_monitor._systemctl")
def test_missing_critical_service_is_down(mock_systemctl):
    mock_systemctl.return_value = completed("")

    result = check_long_running_service(
        "stats-http",
        MonitorCategory.CRITICAL,
    )

    assert result.healthy is False
    assert result.details == "service not installed"


@patch("services.vps_monitor._systemctl")
def test_stats_http_checks_http_endpoint(mock_systemctl):
    mock_systemctl.side_effect = [
        completed("stats-http.service enabled\n"),
        completed("active\n"),
    ]

    with patch(
        "services.vps_monitor._http_check",
        return_value=(True, "HTTP 200"),
    ) as mock_http:
        result = check_stats_http()

    assert result.healthy is True
    assert result.details == "HTTP 200"
    mock_http.assert_called_once_with("http://127.0.0.1:8080/vps-status.json")


@patch("services.vps_monitor._systemctl")
def test_stats_http_http_failure_is_down(mock_systemctl):
    mock_systemctl.side_effect = [
        completed("stats-http.service enabled\n"),
        completed("active\n"),
    ]

    with patch(
        "services.vps_monitor._http_check",
        return_value=(False, "connection refused"),
    ):
        result = check_stats_http()

    assert result.healthy is False
    assert "refused" in result.details


def test_external_monitor_http_200_is_healthy(monkeypatch, tmp_path):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monitor = ExternalHttpMonitor(
        key="home_assistant",
        name="Home Assistant",
        icon="🏠",
        url="http://127.0.0.1:8123",
    )

    cache_file = tmp_path / "vps_external_monitor.json"
    monkeypatch.setattr(
        "services.vps_monitor.EXTERNAL_MONITOR_CACHE_FILE",
        cache_file,
    )
    monkeypatch.setattr(
        "services.vps_monitor.urlopen",
        lambda url, timeout: Response(),
    )
    monotonic_values = iter((10.0, 10.042))
    monkeypatch.setattr(
        "services.vps_monitor.time.monotonic",
        lambda: next(monotonic_values),
    )

    result = check_external_monitor(monitor)

    assert result.name == "home_assistant"
    assert result.category == MonitorCategory.OPTIONAL
    assert result.healthy is True
    assert result.details == "HTTP 200 · 42 ms"
    assert result.failure is None

    cache = json.loads(cache_file.read_text(encoding="utf-8"))
    assert cache["home_assistant"]["healthy"] is True
    assert cache["home_assistant"]["details"] == "HTTP 200"
    assert cache["home_assistant"]["latency_ms"] == 42
    assert cache["home_assistant"]["url"] == "http://127.0.0.1:8123"


def test_external_monitor_http_500_is_down(monkeypatch, tmp_path):
    class Response:
        status = 500

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monitor = ExternalHttpMonitor(
        key="qnap",
        name="QNAP",
        icon="🗄️",
        url="http://127.0.0.1:8888",
    )

    monkeypatch.setattr(
        "services.vps_monitor.EXTERNAL_MONITOR_CACHE_FILE",
        tmp_path / "vps_external_monitor.json",
    )
    monkeypatch.setattr(
        "services.vps_monitor.urlopen",
        lambda url, timeout: Response(),
    )
    monotonic_values = iter((20.0, 20.018))
    monkeypatch.setattr(
        "services.vps_monitor.time.monotonic",
        lambda: next(monotonic_values),
    )

    result = check_external_monitor(monitor)

    assert result.healthy is False
    assert result.details == "HTTP 500 · 18 ms"
    assert result.failure == MonitorFailure.HTTP_FAILED


def test_external_monitor_connection_error_is_down(monkeypatch, tmp_path):
    monitor = ExternalHttpMonitor(
        key="home_assistant",
        name="Home Assistant",
        icon="🏠",
        url="http://127.0.0.1:8123",
    )

    monkeypatch.setattr(
        "services.vps_monitor.EXTERNAL_MONITOR_CACHE_FILE",
        tmp_path / "vps_external_monitor.json",
    )

    def raise_connection_error(url, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(
        "services.vps_monitor.urlopen",
        raise_connection_error,
    )

    result = check_external_monitor(monitor)

    assert result.healthy is False
    assert result.details == "connection refused"
    assert result.failure == MonitorFailure.HTTP_FAILED


def test_check_external_monitors_checks_configured_monitors(monkeypatch):
    monitors = (
        ExternalHttpMonitor(
            key="home_assistant",
            name="Home Assistant",
            icon="🏠",
            url="http://127.0.0.1:8123",
        ),
        ExternalHttpMonitor(
            key="qnap",
            name="QNAP",
            icon="🗄️",
            url="http://127.0.0.1:8888",
        ),
    )

    monkeypatch.setattr(
        "services.vps_monitor.EXTERNAL_HTTP_MONITORS",
        monitors,
    )

    results = [
        MonitorResult(
            name=monitor.key,
            category=MonitorCategory.OPTIONAL,
            healthy=True,
        )
        for monitor in monitors
    ]

    with patch(
        "services.vps_monitor.check_external_monitor",
        side_effect=results,
    ) as mock_check:
        actual = check_external_monitors()

    assert [result.name for result in actual] == [
        "home_assistant",
        "qnap",
    ]
    assert mock_check.call_count == 2


@patch("services.vps_monitor._systemctl")
def test_xray_uses_configured_vless_port(mock_systemctl):
    mock_systemctl.side_effect = [
        completed("xray.service enabled\n"),
        completed("active\n"),
    ]

    with (
        patch(
            "services.vps_monitor.load_xray_config",
            return_value={"inbounds": [{"protocol": "vless", "port": 8443}]},
        ),
        patch(
            "services.vps_monitor._tcp_check",
            return_value=True,
        ) as mock_tcp,
    ):
        result = check_xray()

    assert result.healthy is True
    assert "8443" in result.details
    mock_tcp.assert_called_once_with("127.0.0.1", 8443)


@patch("services.vps_monitor._systemctl")
def test_xray_port_failure_is_down(mock_systemctl):
    mock_systemctl.side_effect = [
        completed("xray.service enabled\n"),
        completed("active\n"),
    ]

    with (
        patch(
            "services.vps_monitor.load_xray_config",
            return_value={"inbounds": [{"protocol": "vless", "port": 443}]},
        ),
        patch(
            "services.vps_monitor._tcp_check",
            return_value=False,
        ),
    ):
        result = check_xray()

    assert result.healthy is False
    assert "TCP 443 unreachable" in result.details


@patch("services.vps_monitor._systemctl")
def test_xray_config_failure_is_down(mock_systemctl):
    mock_systemctl.side_effect = [
        completed("xray.service enabled\n"),
        completed("active\n"),
    ]

    with patch(
        "services.vps_monitor.load_xray_config",
        return_value={"inbounds": []},
    ):
        result = check_xray()

    assert result.healthy is False
    assert result.failure.value == "config_failed"


@patch("services.vps_monitor._systemctl")
@patch("services.vps_monitor.discover_awg_units")
@patch("services.vps_monitor.get_listening_port")
def test_awg_active_and_interface_is_healthy(
    mock_port, mock_discover, mock_systemctl
):
    mock_discover.return_value = ["awg-quick@awg1"]
    mock_systemctl.return_value = completed("active\n")
    mock_port.return_value = 58352

    result = check_awg_service()

    assert result.healthy is True
    assert "awg-quick@awg1" in result.details
    assert "58352" in result.details
    mock_port.assert_called_once_with("awg1")


def test_awg_multiple_units_are_all_checked():
    with patch(
        "services.vps_monitor.discover_awg_units",
        return_value=["awg-quick@awg0", "awg-quick@awg1"],
    ), patch(
        "services.vps_monitor._systemctl",
        side_effect=[
            completed("active\n"),
            completed("active\n"),
        ],
    ) as mock_systemctl, patch(
        "services.vps_monitor.get_listening_port",
        side_effect=[58352, 58353],
    ) as mock_port:
        result = check_awg_service()

    assert result.healthy is True
    assert "awg-quick@awg0" in result.details
    assert "awg-quick@awg1" in result.details
    assert "58352" in result.details
    assert "58353" in result.details
    assert mock_systemctl.call_count == 2
    assert mock_port.call_count == 2


def test_awg_one_failed_unit_makes_aggregate_down():
    with patch(
        "services.vps_monitor.discover_awg_units",
        return_value=["awg-quick@awg0", "awg-quick@awg1"],
    ), patch(
        "services.vps_monitor._systemctl",
        side_effect=[
            completed("active\n"),
            completed("failed\n"),
        ],
    ), patch(
        "services.vps_monitor.get_listening_port",
        return_value=58352,
    ):
        result = check_awg_service()

    assert result.healthy is False
    assert "awg-quick@awg0" in result.details
    assert "awg-quick@awg1: failed" in result.details
    assert result.failure == MonitorFailure.SYSTEMD_FAILED


@patch("services.vps_monitor._systemctl")
@patch("services.vps_monitor.discover_awg_units")
@patch("services.vps_monitor.get_listening_port")
def test_awg_interface_failure_is_down(
    mock_port, mock_discover, mock_systemctl
):
    mock_discover.return_value = ["awg-quick@awg2"]
    mock_systemctl.return_value = completed("active\n")
    mock_port.return_value = None

    result = check_awg_service()

    assert result.healthy is False
    assert "unavailable" in result.details


def test_backup_success_and_fresh_is_healthy(tmp_path):
    status_file = tmp_path / "backup.json"
    status_file.write_text(
        json.dumps(
            {
                "status": "success",
                "last_backup": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    with patch(
        "services.vps_monitor.RCLONE_STATUS_JSON",
        str(status_file),
    ):
        result = check_backup()

    assert result.healthy is True
    assert "last backup" in result.details


def test_backup_failed_status_is_down(tmp_path):
    status_file = tmp_path / "backup.json"
    status_file.write_text(
        json.dumps(
            {
                "status": "local_only",
                "last_backup": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    with patch(
        "services.vps_monitor.RCLONE_STATUS_JSON",
        str(status_file),
    ):
        result = check_backup()

    assert result.healthy is False
    assert "local_only" in result.details


def test_backup_stale_is_down(tmp_path):
    status_file = tmp_path / "backup.json"
    old = datetime.now(timezone.utc) - timedelta(seconds=10_000)
    status_file.write_text(
        json.dumps(
            {
                "status": "success",
                "last_backup": old.isoformat(),
            }
        ),
        encoding="utf-8",
    )

    with patch(
        "services.vps_monitor.RCLONE_STATUS_JSON",
        str(status_file),
    ):
        result = check_backup(max_age_seconds=9_000)

    assert result.healthy is False
    assert "old" in result.details


@patch("services.vps_monitor._systemctl")
def test_ssh_requires_tcp_22(mock_systemctl):
    mock_systemctl.side_effect = [
        completed("ssh.service enabled\n"),
        completed("active\n"),
    ]

    with patch(
        "services.vps_monitor._tcp_check",
        return_value=True,
    ):
        result = check_ssh()

    assert result.healthy is True
    assert "22" in result.details


@patch("services.vps_monitor._systemctl")
def test_fail2ban_client_must_respond(mock_systemctl):
    mock_systemctl.side_effect = [
        completed("fail2ban.service enabled\n"),
        completed("active\n"),
    ]

    with patch(
        "services.vps_monitor.subprocess.run",
        return_value=completed("Status\n|- Number of jail: 2\n"),
    ):
        result = check_fail2ban()

    assert result.healthy is True
    assert "fail2ban-client OK" in result.details


@patch("services.vps_monitor._systemctl")
def test_fail2ban_client_failure_is_down(mock_systemctl):
    mock_systemctl.side_effect = [
        completed("fail2ban.service enabled\n"),
        completed("active\n"),
    ]

    with patch(
        "services.vps_monitor.subprocess.run",
        return_value=completed("", 1),
    ):
        result = check_fail2ban()

    assert result.healthy is False
    assert "failed" in result.details


@patch("services.vps_monitor.check_external_monitors")
@patch("services.vps_monitor.check_fail2ban")
@patch("services.vps_monitor.check_ssh")
@patch("services.vps_monitor.check_awg_service")
@patch("services.vps_monitor.check_xray")
@patch("services.vps_monitor.check_backup")
@patch("services.vps_monitor.check_stats_http")
@patch("services.vps_monitor.check_long_running_service")
def test_check_all_contains_only_monitoring_targets(
    mock_service,
    mock_stats,
    mock_backup,
    mock_xray,
    mock_awg,
    mock_ssh,
    mock_fail2ban,
    mock_external,
):
    mock_service.side_effect = [
        MonitorResult(
            name="zvertbot",
            category=MonitorCategory.CRITICAL,
            healthy=True,
        ),
        MonitorResult(
            name="zvertbot-vps-monitor",
            category=MonitorCategory.OPTIONAL,
            healthy=True,
        ),
    ]
    mock_stats.return_value = MonitorResult(
        name="stats-http",
        category=MonitorCategory.CRITICAL,
        healthy=True,
    )
    mock_backup.return_value = MonitorResult(
        name="backup",
        category=MonitorCategory.OPTIONAL,
        healthy=True,
    )
    mock_xray.return_value = MonitorResult(
        name="xray",
        category=MonitorCategory.OPTIONAL,
        healthy=True,
    )
    mock_awg.return_value = MonitorResult(
        name="awg",
        category=MonitorCategory.OPTIONAL,
        healthy=True,
    )
    mock_ssh.return_value = MonitorResult(
        name="ssh",
        category=MonitorCategory.OPTIONAL,
        healthy=True,
    )
    mock_fail2ban.return_value = MonitorResult(
        name="fail2ban",
        category=MonitorCategory.OPTIONAL,
        healthy=True,
    )
    mock_external.return_value = [
        MonitorResult(
            name="home_assistant",
            category=MonitorCategory.OPTIONAL,
            healthy=True,
        ),
        MonitorResult(
            name="qnap",
            category=MonitorCategory.OPTIONAL,
            healthy=True,
        ),
    ]

    results = check_all()

    assert [result.name for result in results] == [
        "zvertbot",
        "zvertbot-vps-monitor",
        "stats-http",
        "backup",
        "xray",
        "awg",
        "ssh",
        "fail2ban",
        "home_assistant",
        "qnap",
    ]
    assert [call.args for call in mock_service.call_args_list] == [
        ("zvertbot", MonitorCategory.CRITICAL),
        ("zvertbot-vps-monitor", MonitorCategory.OPTIONAL),
    ]
    mock_external.assert_called_once_with()
