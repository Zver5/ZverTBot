import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services.vps_monitor import (
    CRITICAL_COMPONENTS,
    DATA_COLLECTORS,
    OPTIONAL_COMPONENTS,
    MonitorCategory,
    MonitorResult,
    MonitorState,
    StateTransition,
    check_all,
    check_awg_service,
    check_backup,
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
    mock_http.assert_called_once_with(
        "http://127.0.0.1:8080/vps-status.json"
    )


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


@patch("services.vps_monitor._systemctl")
def test_xray_requires_tcp_443(mock_systemctl):
    mock_systemctl.side_effect = [
        completed("xray.service enabled\n"),
        completed("active\n"),
    ]

    with patch(
        "services.vps_monitor._tcp_check",
        return_value=True,
    ):
        result = check_xray()

    assert result.healthy is True
    assert "443" in result.details


@patch("services.vps_monitor._systemctl")
def test_xray_port_failure_is_down(mock_systemctl):
    mock_systemctl.side_effect = [
        completed("xray.service enabled\n"),
        completed("active\n"),
    ]

    with patch(
        "services.vps_monitor._tcp_check",
        return_value=False,
    ):
        result = check_xray()

    assert result.healthy is False
    assert "unreachable" in result.details


@patch("services.vps_monitor._systemctl")
def test_awg_active_and_interface_is_healthy(mock_systemctl):
    mock_systemctl.side_effect = [
        completed("awg-quick@awg0.service enabled\n"),
        completed("active\n"),
    ]

    with patch(
        "services.vps_monitor.subprocess.run",
        return_value=completed(
            "interface: awg0\n"
            "  listening port: 58352\n"
        ),
    ):
        result = check_awg_service()

    assert result.healthy is True
    assert "58352" in result.details


@patch("services.vps_monitor._systemctl")
def test_awg_interface_failure_is_down(mock_systemctl):
    mock_systemctl.side_effect = [
        completed("awg-quick@awg0.service enabled\n"),
        completed("active\n"),
    ]

    with patch(
        "services.vps_monitor.subprocess.run",
        return_value=completed("", 1),
    ):
        result = check_awg_service()

    assert result.healthy is False
    assert "unavailable" in result.details


def test_backup_success_and_fresh_is_healthy(tmp_path):
    status_file = tmp_path / "backup.json"
    status_file.write_text(
        json.dumps(
            {
                "status": "success",
                "last_backup": datetime.now(
                    timezone.utc
                ).isoformat(),
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
                "last_backup": datetime.now(
                    timezone.utc
                ).isoformat(),
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
):
    mock_service.return_value = MonitorResult(
        name="zvertbot",
        category=MonitorCategory.CRITICAL,
        healthy=True,
    )
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

    results = check_all()

    assert [result.name for result in results] == [
        "zvertbot",
        "stats-http",
        "backup",
        "xray",
        "awg",
        "ssh",
        "fail2ban",
    ]
