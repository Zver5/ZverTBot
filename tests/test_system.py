import json
from unittest.mock import Mock, patch

from services.system import (
    get_service_logs,
    run_disk_cleanup,
    run_speedtest_and_ip,
)


class FakeStat:
    def __init__(self, blocks, bavail, frsize):
        self.f_blocks = blocks
        self.f_bavail = bavail
        self.f_frsize = frsize


@patch("services.system.subprocess.run")
@patch("services.system.os.statvfs")
def test_disk_cleanup_success(mock_stat, mock_run):
    mock_stat.side_effect = [
        FakeStat(1000, 200, 1024),
        FakeStat(1000, 300, 1024),
    ]

    text = run_disk_cleanup()

    assert "Очистка завершена" in text
    assert "Освобождено" in text


@patch("services.system.subprocess.run")
@patch("services.system.os.statvfs")
def test_disk_cleanup_exception(mock_stat, mock_run):
    mock_stat.side_effect = Exception("disk error")

    text = run_disk_cleanup()

    assert "Ошибка" in text
    assert "disk error" in text


@patch("services.system.shutil.which")
@patch("services.system.subprocess.run")
def test_speedtest_success(mock_run, mock_which):
    mock_which.return_value = "/usr/local/bin/speedtest"
    # Мокаем JSON-ответ от Ookla speedtest
    ookla_json = {
        "ping": {"latency": 15.2},
        "download": {"bandwidth": 31263750},  # 250.11 Mbps в bytes/s
        "upload": {"bandwidth": 12568750},  # 100.55 Mbps в bytes/s
        "server": {
            "host": "speedtest.example.com",
            "location": "Moscow",
            "country": "Russia",
        },
    }

    mock_run.return_value = Mock(returncode=0, stdout=json.dumps(ookla_json), stderr="")

    text = run_speedtest_and_ip()

    assert "Speedtest Result" in text
    assert "15.2 ms" in text
    assert "250.11 Mbit/s" in text
    assert "100.55 Mbit/s" in text
    assert "speedtest.example.com" in text


@patch("services.system.shutil.which")
@patch("services.system.subprocess.run")
def test_speedtest_error(mock_run, mock_which):
    mock_which.return_value = "/usr/local/bin/speedtest"
    mock_run.return_value = Mock(returncode=1, stdout="", stderr="network error")

    text = run_speedtest_and_ip()

    assert "network error" in text


@patch("services.system.subprocess.run")
def test_speedtest_exception(mock_run):
    import subprocess

    mock_run.side_effect = subprocess.TimeoutExpired(cmd="speedtest", timeout=120)

    text = run_speedtest_and_ip()

    assert "Таймаут" in text


def test_logs_wrong_service():
    text = get_service_logs("unknown")

    assert "Доступно" in text


@patch("services.system.XRAY_ACCESS_LOG")
@patch("services.system.subprocess.run")
def test_logs_empty(mock_run, mock_log):
    mock_log.exists.return_value = False
    mock_run.return_value = Mock(stdout="")

    text = get_service_logs("xray")

    assert "пусты" in text


@patch("services.system.XRAY_ACCESS_LOG")
@patch("services.system.subprocess.run")
def test_logs_success(mock_run, mock_log):
    mock_log.exists.return_value = False
    mock_run.return_value = Mock(stdout="first line\nsecond line\n")

    text = get_service_logs("xray")

    assert "Логи: xray" in text
    assert "first line" in text
    assert "second line" in text


@patch("services.system.XRAY_ACCESS_LOG")
@patch("services.system.subprocess.run")
def test_logs_strip_ansi(mock_run, mock_log):
    mock_log.exists.return_value = False
    mock_run.return_value = Mock(stdout="\x1b[31mERROR\x1b[0m\n")

    text = get_service_logs("xray")

    assert "ERROR" in text
    assert "\x1b" not in text


@patch("services.system.XRAY_ACCESS_LOG")
@patch("services.system.subprocess.run")
def test_logs_exception(mock_run, mock_log):
    mock_log.exists.return_value = False
    mock_run.side_effect = Exception("boom")

    text = get_service_logs("xray")

    assert "Ошибка чтения" in text


@patch("services.system.shutil.which")
def test_speedtest_not_installed(mock_which):
    mock_which.return_value = None

    text = run_speedtest_and_ip()

    assert "speedtest не установлен" in text


@patch("services.system.shutil.which")
@patch("services.system.subprocess.run")
def test_speedtest_invalid_json(mock_run, mock_which):
    mock_which.return_value = "/usr/local/bin/speedtest"
    mock_run.return_value = Mock(
        returncode=0,
        stdout="{invalid json",
        stderr="",
    )

    text = run_speedtest_and_ip()

    assert "Ошибка парсинга JSON" in text


@patch("services.system.shutil.which")
def test_awg_not_installed(mock_which):
    mock_which.return_value = None

    text = get_service_logs("awg")

    assert "AmneziaWG не установлен" in text


@patch("services.system.shutil.which")
@patch("services.system.service_exists")
def test_awg_service_not_installed(mock_exists, mock_which):
    mock_which.return_value = "/usr/bin/awg"
    mock_exists.return_value = False

    text = get_service_logs("awg")

    assert "AmneziaWG не установлен" in text


@patch("services.system.shutil.which")
@patch("services.system.service_exists")
@patch("services.system.subprocess.run")
def test_awg_empty_output(mock_run, mock_exists, mock_which):
    mock_which.return_value = "/usr/bin/awg"
    mock_exists.return_value = True
    mock_run.return_value = Mock(stdout="")

    text = get_service_logs("awg")

    assert "AWG awg0 не отвечает" in text


@patch("services.system.shutil.which")
@patch("services.system.service_exists")
@patch("services.system.subprocess.run")
def test_awg_success_strips_ansi(mock_run, mock_exists, mock_which):
    mock_which.return_value = "/usr/bin/awg"
    mock_exists.return_value = True
    mock_run.return_value = Mock(stdout="\x1b[32minterface: awg0\x1b[0m\npeer: test")

    text = get_service_logs("awg")

    assert "AWG статус awg0" in text
    assert "interface: awg0" in text
    assert "peer: test" in text
    assert "\x1b" not in text


@patch("services.system.shutil.which")
@patch("services.system.service_exists")
@patch("services.system.subprocess.run")
def test_awg_exception(mock_run, mock_exists, mock_which):
    mock_which.return_value = "/usr/bin/awg"
    mock_exists.return_value = True
    mock_run.side_effect = Exception("awg failed")

    text = get_service_logs("awg")

    assert "Ошибка AWG" in text
    assert "awg failed" in text


@patch("services.system.XRAY_ACCESS_LOG")
@patch("services.system.subprocess.run")
def test_xray_uses_access_log_when_available(mock_run, mock_log):
    mock_log.exists.return_value = True
    mock_log.read_text.return_value = "line 1\nline 2\nline 3\n"

    text = get_service_logs("xray")

    assert "Логи: xray" in text
    assert "line 1" in text
    assert "line 3" in text
    mock_run.assert_not_called()


@patch("services.system.XRAY_ACCESS_LOG")
@patch("services.system.subprocess.run")
def test_xray_access_log_uses_last_30_lines(mock_run, mock_log):
    mock_log.exists.return_value = True
    mock_log.read_text.return_value = "\n".join(f"line {index}" for index in range(35))

    text = get_service_logs("xray")

    assert "line 0" not in text
    assert "line 4" not in text
    assert "line 5" in text
    assert "line 34" in text
    mock_run.assert_not_called()


@patch("services.system.subprocess.run")
def test_bot_logs_from_journal(mock_run):
    mock_run.return_value = Mock(stdout="bot started\nbot is running\n")

    text = get_service_logs("bot")

    assert "Логи: zvertbot" in text
    assert "bot started" in text
    assert "bot is running" in text


@patch("services.system.subprocess.run")
def test_bot_empty_logs(mock_run):
    mock_run.return_value = Mock(stdout="")

    text = get_service_logs("bot")

    assert "Логи zvertbot пусты" in text


@patch("services.system.shutil.which")
@patch("services.system.subprocess.run")
def test_speedtest_unexpected_exception(mock_run, mock_which):
    mock_which.return_value = "/usr/local/bin/speedtest"
    mock_run.side_effect = RuntimeError("unexpected speedtest error")

    text = run_speedtest_and_ip()

    assert "Ошибка: unexpected speedtest error" in text
