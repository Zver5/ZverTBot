from unittest.mock import mock_open, patch

from services.backup import get_backup_history_text


@patch("services.backup.subprocess.run")
def test_backup_history_empty(mock_run):
    mock_run.return_value.stdout = ""

    with patch("builtins.open", side_effect=FileNotFoundError):
        text = get_backup_history_text()

    assert "История бэкапов" in text
    assert "Локальные (0 шт.)" in text
    assert "Статус недоступен" in text


@patch("services.backup.subprocess.run")
def test_backup_history_success(mock_run):
    mock_run.return_value.stdout = (
        "-rw-r--r-- 1 root root 120M Jul 1 10:00 vps-backup-1.tar.gz\n"
        "-rw-r--r-- 1 root root 130M Jul 2 10:00 vps-backup-2.tar.gz\n"
    )

    status_json = """
{
    "last_backup": "2026-07-04T03:00:00+00:00",
    "size_mb": 130,
    "status": "OK"
}
"""

    with patch("builtins.open", mock_open(read_data=status_json)):
        text = get_backup_history_text()

    assert "vps-backup-1.tar.gz" in text
    assert "vps-backup-2.tar.gz" in text
    assert "04.07.2026 06:00 MSK" in text
    assert "130 MB" in text
    assert "OK" in text


@patch("services.backup.subprocess.run")
def test_backup_history_filename_with_spaces(mock_run):
    mock_run.return_value.stdout = (
        "-rw-r--r-- 1 root root 120M Jul 3 10:00 vps-backup-before upgrade.tar.gz\\n"
    )

    with patch("builtins.open", side_effect=FileNotFoundError):
        text = get_backup_history_text()

    assert "vps-backup-before upgrade.tar.gz" in text
    assert "(120M)" in text


@patch("services.backup.subprocess.run")
def test_backup_history_status_unavailable(mock_run):
    mock_run.return_value.stdout = (
        "-rw-r--r-- 1 root root 120M Jul 1 10:00 vps-backup.tar.gz\n"
    )

    with patch("builtins.open", side_effect=Exception("boom")):
        text = get_backup_history_text()

    assert "Статус недоступен" in text


@patch("services.backup.subprocess.run")
def test_backup_history_ls_exception(mock_run):
    mock_run.side_effect = Exception("ls failed")

    text = get_backup_history_text()

    assert "Ошибка" in text
    assert "ls failed" in text


def test_format_msk_time_returns_original_value_on_invalid_input():
    from services.backup import format_msk_time

    assert format_msk_time("not-a-date") == "not-a-date"


@patch("services.backup.subprocess.run")
def test_get_backup_remote_size_gigabytes(mock_run):
    from services.backup import get_backup_remote_size

    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = '{"bytes": 2147483648, "count": 3}'

    assert get_backup_remote_size() == "2.00 GB (3 шт.)"


@patch("services.backup.subprocess.run")
def test_get_backup_remote_size_megabytes(mock_run):
    from services.backup import get_backup_remote_size

    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = '{"bytes": 5242880, "count": 4}'

    assert get_backup_remote_size() == "5.0 MB (4 шт.)"


@patch("services.backup.subprocess.run")
def test_get_backup_remote_size_kilobytes(mock_run):
    from services.backup import get_backup_remote_size

    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = '{"bytes": 3072, "count": 2}'

    assert get_backup_remote_size() == "3.0 KB (2 шт.)"


@patch("services.backup.subprocess.run")
def test_get_backup_remote_size_bytes(mock_run):
    from services.backup import get_backup_remote_size

    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = '{"bytes": 512, "count": 1}'

    assert get_backup_remote_size() == "512 B (1 шт.)"


@patch("services.backup.subprocess.run")
def test_get_backup_remote_size_returns_na_on_rclone_failure(mock_run):
    from services.backup import get_backup_remote_size

    mock_run.return_value.returncode = 1
    mock_run.return_value.stdout = ""

    assert get_backup_remote_size() == "N/A"


@patch("services.backup.subprocess.run")
def test_get_backup_remote_size_returns_na_on_invalid_json(mock_run):
    from services.backup import get_backup_remote_size

    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "{invalid json"

    assert get_backup_remote_size() == "N/A"


@patch("services.backup.subprocess.run")
def test_get_backup_remote_size_returns_na_on_rclone_exception(mock_run):
    from services.backup import get_backup_remote_size

    mock_run.side_effect = Exception("rclone failed")

    assert get_backup_remote_size() == "N/A"


def test_get_backup_remote_size_returns_na_when_remote_not_configured(monkeypatch):
    from services import backup

    monkeypatch.setattr(backup, "BACKUP_REMOTE", "")
    monkeypatch.setattr(backup, "BACKUP_ROOT_DIR", "/backups")

    assert backup.get_backup_remote_size() == "N/A"


@patch("services.backup.subprocess.run")
def test_backup_history_skips_irrelevant_ls_line(mock_run):
    mock_run.return_value.stdout = (
        "total 8\n"
        "-rw-r--r-- 1 root root 120M Jul 1 10:00 vps-backup-1.tar.gz\n"
    )

    with patch("builtins.open", side_effect=FileNotFoundError):
        text = get_backup_history_text()

    assert "vps-backup-1.tar.gz" in text


@patch("services.backup.subprocess.run")
def test_backup_history_skips_line_without_backup_separator(mock_run):
    mock_run.return_value.stdout = (
        "-rw-r--r-- 1 root root 120M Jul 1 10:00 something-vps-backup\n"
        "invalid vps-backup line\n"
    )

    with patch("builtins.open", side_effect=FileNotFoundError):
        text = get_backup_history_text()

    assert "История бэкапов" in text


@patch("services.backup.subprocess.run")
def test_backup_history_skips_short_ls_line(mock_run):
    mock_run.return_value.stdout = (
        "-rw-r--r-- root root vps-backup-broken.tar.gz\n"
        "-rw-r--r-- 1 root root 120M Jul 1 10:00 vps-backup-good.tar.gz\n"
    )

    with patch("builtins.open", side_effect=FileNotFoundError):
        text = get_backup_history_text()

    assert "vps-backup-good.tar.gz" in text
    assert "vps-backup-broken.tar.gz" not in text
