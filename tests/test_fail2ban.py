from unittest.mock import Mock, patch

from services.fail2ban import (
    get_fail2ban_logs,
    get_fail2ban_status,
    unban_ip,
)


@patch("services.fail2ban.service_is_active", return_value=False)
def test_status_service_inactive(mock_active):
    text = get_fail2ban_status()

    assert "не активен" in text


@patch("services.fail2ban.service_is_active", return_value=True)
@patch("services.fail2ban.subprocess.run")
def test_status_error(mock_run, mock_active):
    mock_run.return_value = Mock(returncode=1, stderr="boom")

    text = get_fail2ban_status()

    assert "Ошибка" in text
    assert "boom" in text


@patch("services.fail2ban.service_is_active", return_value=True)
@patch("services.fail2ban.subprocess.run")
def test_status_success(mock_run, mock_active):
    mock_run.side_effect = [
        Mock(
            returncode=0,
            stdout="""
Status
|- Number of jail: 1
`- Jail list: sshd
""",
        ),
        Mock(
            returncode=0,
            stdout="""
Status for jail: sshd
|- Currently banned: 2
`- Total banned: 15
""",
        ),
    ]

    text = get_fail2ban_status()

    assert "Fail2ban Status" in text
    assert "sshd" in text
    assert "2" in text
    assert "15" in text


@patch("services.fail2ban.service_is_active", side_effect=Exception("boom"))
def test_status_exception(mock_active):
    text = get_fail2ban_status()

    assert "Ошибка" in text


@patch("services.fail2ban.subprocess.run")
def test_logs_from_file(mock_run):
    mock_run.return_value = Mock(
        returncode=0,
        stdout=(
            "2026-06-30 12:45:03,991 fail2ban.actions [449]: "
            "NOTICE [sshd] Ban 1.2.3.4\n"
        ),
    )

    text = get_fail2ban_logs()

    assert "1.2.3.4" in text
    assert "sshd" in text


@patch("services.fail2ban.subprocess.run")
def test_logs_from_journal(mock_run):
    mock_run.side_effect = [
        Mock(returncode=1, stdout=""),
        Mock(
            stdout=(
                "2026-06-30 12:45:03,991 fail2ban.actions [449]: "
                "NOTICE [sshd] Ban 5.6.7.8\n"
            ),
        ),
    ]

    text = get_fail2ban_logs()

    assert "5.6.7.8" in text


@patch("services.fail2ban.subprocess.run")
def test_logs_empty(mock_run):
    mock_run.side_effect = [
        Mock(returncode=1, stdout=""),
        Mock(stdout=""),
    ]

    text = get_fail2ban_logs()

    assert "не найдено" in text


@patch("services.fail2ban.subprocess.run")
def test_logs_bad_line(mock_run):
    mock_run.return_value = Mock(returncode=0, stdout="some broken line\n")

    text = get_fail2ban_logs()

    assert "broken line" in text


def test_unban_invalid_ip():
    ok, msg = unban_ip("abc")

    assert ok is False
    assert "Неверный формат" in msg


@patch("services.fail2ban.subprocess.run")
def test_unban_status_error(mock_run):
    mock_run.return_value = Mock(returncode=1, stderr="boom")

    ok, msg = unban_ip("1.2.3.4")

    assert ok is False
    assert "boom" in msg


@patch("services.fail2ban.subprocess.run")
def test_unban_success(mock_run):
    mock_run.side_effect = [
        Mock(
            returncode=0,
            stdout="""
Status
Jail list: sshd
""",
        ),
        Mock(returncode=0, stdout="1.2.3.4"),
    ]

    ok, msg = unban_ip("1.2.3.4")

    assert ok is True
    assert "разбанен" in msg


@patch("services.fail2ban.subprocess.run")
def test_unban_not_found(mock_run):
    mock_run.side_effect = [
        Mock(
            returncode=0,
            stdout="""
Status
Jail list: sshd
""",
        ),
        Mock(returncode=0, stdout=""),
    ]

    ok, msg = unban_ip("1.2.3.4")

    assert ok is False
    assert "не найден" in msg


@patch("services.fail2ban.subprocess.run")
def test_unban_exception(mock_run):
    mock_run.side_effect = Exception("boom")

    ok, msg = unban_ip("1.2.3.4")

    assert ok is False
    assert "Ошибка" in msg


@patch("services.fail2ban.subprocess.run")
def test_logs_exception(mock_run):
    mock_run.side_effect = RuntimeError("boom")
    result = get_fail2ban_logs()
    assert result.startswith("❌ Ошибка:")
    assert "boom" in result


@patch("services.fail2ban.service_is_active", return_value=True)
@patch("services.fail2ban.subprocess.run")
def test_status_invalid_number_of_jails_logs_warning(mock_run, mock_active):
    mock_run.return_value = Mock(
        returncode=0,
        stdout="""
Status
|- Number of jail: invalid
`- Jail list: sshd
""",
    )

    with patch("services.fail2ban.logger.warning") as mock_warning:
        text = get_fail2ban_status()

    assert "Fail2ban Status" in text
    mock_warning.assert_called_once_with(
        "fail2ban.status.invalid_jail_count | value=%s",
        "invalid",
    )


@patch("services.fail2ban.service_is_active", return_value=True)
@patch("services.fail2ban.subprocess.run")
def test_status_invalid_currently_banned_logs_warning(mock_run, mock_active):
    mock_run.side_effect = [
        Mock(
            returncode=0,
            stdout="""
Status
|- Number of jail: 1
`- Jail list: sshd
""",
        ),
        Mock(
            returncode=0,
            stdout="""
Status for jail: sshd
|- Currently banned: invalid
`- Total banned: 15
""",
        ),
    ]

    with patch("services.fail2ban.logger.warning") as mock_warning:
        text = get_fail2ban_status()

    assert "sshd" in text
    mock_warning.assert_called_once_with(
        "fail2ban.status.invalid_banned_count | "
        "field=currently_banned | value=%s",
        "invalid",
    )


@patch("services.fail2ban.service_is_active", return_value=True)
@patch("services.fail2ban.subprocess.run")
def test_status_invalid_total_banned_logs_warning(mock_run, mock_active):
    mock_run.side_effect = [
        Mock(
            returncode=0,
            stdout="""
Status
|- Number of jail: 1
`- Jail list: sshd
""",
        ),
        Mock(
            returncode=0,
            stdout="""
Status for jail: sshd
|- Currently banned: 2
`- Total banned: invalid
""",
        ),
    ]

    with patch("services.fail2ban.logger.warning") as mock_warning:
        text = get_fail2ban_status()

    assert "sshd" in text
    mock_warning.assert_called_once_with(
        "fail2ban.status.invalid_banned_count | "
        "field=total_banned | value=%s",
        "invalid",
    )
