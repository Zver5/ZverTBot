"""
Тесты управления systemd-сервисами.
"""

from unittest.mock import Mock, patch

import pytest

from utils.service_control import (
    get_service_state,
    get_service_uptime_seconds,
    list_service_units,
    restart_service,
    restart_service_detached,
    service_exists,
    service_is_active,
)


@patch("utils.service_control.subprocess.run")
def test_service_exists_when_unit_exists(mock_run):
    mock_run.return_value = Mock(returncode=0)

    assert service_exists("xray") is True

    mock_run.assert_called_once_with(
        ["systemctl", "cat", "xray"],
        capture_output=True,
        text=True,
        timeout=5,
    )


@patch("utils.service_control.subprocess.run")
def test_service_exists_when_unit_missing(mock_run):
    mock_run.return_value = Mock(returncode=1)

    assert service_exists("xray") is False


@patch("utils.service_control.subprocess.run")
def test_service_exists_when_systemctl_fails(mock_run):
    mock_run.side_effect = Exception("systemctl error")

    assert service_exists("xray") is False


@patch("utils.service_control.subprocess.run")
def test_service_is_active_when_active(mock_run):
    mock_run.return_value = Mock(
        returncode=0,
        stdout="active\n",
    )

    assert service_is_active("xray") is True


@patch("utils.service_control.subprocess.run")
def test_service_is_active_when_inactive(mock_run):
    mock_run.return_value = Mock(
        returncode=3,
        stdout="inactive\n",
    )

    assert service_is_active("xray") is False


@patch("utils.service_control.subprocess.run")
def test_service_is_active_when_wrong_state(mock_run):
    mock_run.return_value = Mock(
        returncode=0,
        stdout="failed\n",
    )

    assert service_is_active("xray") is False


@patch("utils.service_control.subprocess.run")
def test_service_is_active_when_exception(mock_run):
    mock_run.side_effect = Exception("systemctl error")

    assert service_is_active("xray") is False


@patch("utils.service_control.subprocess.run")
def test_get_service_state_returns_active(mock_run):
    mock_run.return_value = Mock(returncode=0, stdout="active\n")

    assert get_service_state("xray") == "active"

    mock_run.assert_called_once_with(
        ["systemctl", "is-active", "xray"],
        capture_output=True,
        text=True,
        timeout=5,
    )


@patch("utils.service_control.subprocess.run")
def test_get_service_state_returns_unknown_when_output_is_empty(mock_run):
    mock_run.return_value = Mock(returncode=3, stdout="")

    assert get_service_state("xray") == "unknown"


@patch("utils.service_control.subprocess.run")
def test_get_service_state_returns_unknown_on_exception(mock_run):
    mock_run.side_effect = Exception("systemctl error")

    assert get_service_state("xray") == "unknown"


@patch("utils.service_control.get_service_state")
def test_service_is_active_uses_service_state(mock_state):
    mock_state.return_value = "active"

    assert service_is_active("xray") is True

    mock_state.assert_called_once_with("xray")


@patch("utils.service_control.get_service_state")
def test_service_is_active_is_false_for_other_states(mock_state):
    mock_state.return_value = "failed"

    assert service_is_active("xray") is False


@patch("utils.service_control.subprocess.run")
def test_list_service_units_returns_service_names(mock_run):
    mock_run.return_value = Mock(
        stdout=(
            "xray.service loaded active running Xray\n"
            "stats-http.service loaded active running Stats\n"
            "zvertbot.service loaded inactive dead Bot\n"
        )
    )

    assert list_service_units() == ["xray", "stats-http", "zvertbot"]

    mock_run.assert_called_once_with(
        [
            "systemctl",
            "list-units",
            "--type=service",
            "--all",
            "--no-legend",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )


@patch("utils.service_control.subprocess.run")
def test_list_service_units_returns_empty_on_exception(mock_run):
    mock_run.side_effect = Exception("systemctl error")

    assert list_service_units() == []


@patch("utils.service_control.subprocess.run")
def test_get_service_uptime_seconds(mock_run):
    mock_run.side_effect = [
        Mock(stdout="ActiveEnterTimestampMonotonic=120000000\n"),
        Mock(stdout="125.5 0.0\n"),
    ]

    assert get_service_uptime_seconds("xray") == 5


@patch("utils.service_control.subprocess.run")
def test_get_service_uptime_seconds_returns_none_for_invalid_timestamp(mock_run):
    mock_run.return_value = Mock(stdout="ActiveEnterTimestampMonotonic=\n")

    assert get_service_uptime_seconds("xray") is None


@patch("utils.service_control.subprocess.run")
def test_get_service_uptime_seconds_returns_none_on_exception(mock_run):
    mock_run.side_effect = Exception("systemctl error")

    assert get_service_uptime_seconds("xray") is None


@patch("utils.service_control.subprocess.Popen")
def test_restart_service_detached(mock_popen):
    restart_service_detached("zvertbot")

    mock_popen.assert_called_once_with(
        ["systemctl", "restart", "zvertbot"],
        stdout=__import__("subprocess").DEVNULL,
        stderr=__import__("subprocess").DEVNULL,
        start_new_session=True,
    )


@patch("utils.service_control.subprocess.run")
def test_restart_service_success(mock_run):
    restart_result = Mock()
    restart_result.returncode = 0

    active_result = Mock()
    active_result.returncode = 0
    active_result.stdout = "active\n"

    mock_run.side_effect = [restart_result, active_result]

    with (
        patch("utils.service_control.time.sleep") as mock_sleep,
        patch("utils.service_control.logger.info") as mock_info,
    ):
        restart_service("zvertbot", wait=3)

    mock_run.assert_any_call(
        ["systemctl", "restart", "zvertbot"],
        check=True,
        timeout=15,
    )
    mock_run.assert_any_call(
        ["systemctl", "is-active", "zvertbot"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    mock_sleep.assert_called_once_with(3)
    mock_info.assert_called_once_with(
        "service.restart.completed | service=%s",
        "zvertbot",
    )


@patch("utils.service_control.subprocess.run")
def test_restart_service_raises_when_service_is_not_active(mock_run):
    restart_result = Mock()
    restart_result.returncode = 0

    active_result = Mock()
    active_result.returncode = 0
    active_result.stdout = "failed\n"

    mock_run.side_effect = [restart_result, active_result]

    with (
        patch("utils.service_control.time.sleep"),
        patch("utils.service_control.logger.error") as mock_error,
    ):
        with pytest.raises(RuntimeError, match="zvertbot не активен после рестарта"):
            restart_service("zvertbot")

    mock_error.assert_called_once()


@patch("utils.service_control.subprocess.run")
def test_restart_service_raises_when_restart_fails(mock_run):
    mock_run.side_effect = RuntimeError("systemctl failed")

    with patch("utils.service_control.logger.error") as mock_error:
        with pytest.raises(RuntimeError, match="systemctl failed"):
            restart_service("zvertbot")

    mock_error.assert_called_once()


@patch("utils.service_control.subprocess.Popen")
def test_restart_service_detached_raises_when_popen_fails(mock_popen):
    mock_popen.side_effect = RuntimeError("Popen failed")

    with patch("utils.service_control.logger.error") as mock_error:
        with pytest.raises(RuntimeError, match="Popen failed"):
            restart_service_detached("zvertbot")

    mock_error.assert_called_once()
