from unittest.mock import Mock, patch

from services.processes import (
    format_processes_text,
    get_top_processes,
    kill_process_by_pid,
    search_process_by_name,
)


@patch("services.processes.subprocess.run")
def test_get_top_processes_success(mock_run):
    mock_run.return_value = Mock(
        returncode=0,
        stdout=(
            "USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND\n"
            "root 1234 10.5 5.0 100000 50000 ? S 10:00 00:01 python bot.py\n"
        ),
    )

    result = get_top_processes()

    assert len(result) == 1
    assert result[0]["pid"] == "1234"
    assert result[0]["cpu"] == 10.5
    assert result[0]["mem"] == 5.0
    assert result[0]["command"] == "python bot.py"


@patch("services.processes.subprocess.run")
def test_get_top_processes_ps_error(mock_run):
    mock_run.return_value = Mock(returncode=1, stdout="", stderr="ps error")
    assert get_top_processes() == []


@patch("services.processes.subprocess.run")
def test_get_top_processes_bad_line(mock_run):
    mock_run.return_value = Mock(
        returncode=0,
        stdout=(
            "USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND\n"
            "this is invalid line\n"
        ),
    )
    assert get_top_processes() == []


@patch("services.processes.get_top_processes")
def test_format_processes_text_empty(mock_get):
    mock_get.return_value = []
    assert "Не удалось получить список процессов" in format_processes_text()


@patch("services.processes.get_top_processes")
def test_format_processes_text_success(mock_get):
    mock_get.return_value = [
        {
            "user": "root",
            "pid": "123",
            "cpu": 12.5,
            "mem": 3.2,
            "rss": 150,
            "command": "python bot.py",
        }
    ]

    text = format_processes_text()

    assert "123" in text
    assert "python bot.py" in text
    assert "Итого" in text


def test_kill_process_invalid_pid():
    ok, msg = kill_process_by_pid("abc")
    assert ok is False
    assert "PID" in msg


@patch("services.processes.subprocess.run")
def test_kill_process_not_found(mock_run):
    mock_run.return_value = Mock(returncode=1)

    ok, msg = kill_process_by_pid("123")

    assert ok is False
    assert "не найден" in msg


@patch("services.processes.time.sleep")
@patch("services.processes.subprocess.run")
def test_kill_process_sigterm_success(mock_run, mock_sleep):
    mock_run.side_effect = [
        Mock(returncode=0),
        Mock(returncode=0, stdout="USER COMMAND\nroot python"),
        Mock(returncode=0),
        Mock(returncode=1),
    ]

    ok, msg = kill_process_by_pid("123")

    assert ok is True
    assert "SIGTERM" in msg


@patch("services.processes.time.sleep")
@patch("services.processes.subprocess.run")
def test_kill_process_sigkill(mock_run, mock_sleep):
    mock_run.side_effect = [
        Mock(returncode=0),
        Mock(returncode=0, stdout="USER COMMAND\nroot python"),
        Mock(returncode=0),
        Mock(returncode=0),
        Mock(returncode=0),
    ]

    ok, msg = kill_process_by_pid("123")

    assert ok is True
    assert "SIGKILL" in msg


def test_search_process_short_name():
    text = search_process_by_name("a")

    assert "минимум 2 символа" in text


@patch("services.processes.subprocess.run")
def test_search_process_not_found(mock_run):
    mock_run.return_value = Mock(returncode=1, stdout="")

    text = search_process_by_name("python")

    assert "не найдены" in text


@patch("services.processes.subprocess.run")
def test_search_process_found(mock_run):
    mock_run.return_value = Mock(
        returncode=0, stdout="1234 python bot.py\n5678 python worker.py\n"
    )

    text = search_process_by_name("python")

    assert "1234" in text
    assert "5678" in text
    assert "Найдено: 2" in text


@patch("services.processes.subprocess.run")
def test_search_process_escapes_markdown_once(mock_run):
    mock_run.return_value = Mock(
        returncode=0, stdout="1234 worker*prod `test`\n"
    )

    text = search_process_by_name("worker")

    assert "`1234` worker\\*prod \\`test\\`" in text
    assert "worker\\\\*prod" not in text


@patch("services.processes.subprocess.run")
def test_get_top_processes_grep_filtered(mock_run):
    mock_run.return_value = Mock(
        returncode=0,
        stdout=(
            "USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND\n"
            "grep python\n"
            "root 5678 20.0 10.0 200000 100000 ? S 10:00 00:02 python bot.py\n"
        ),
    )
    result = get_top_processes()
    assert len(result) == 1
    assert result[0]["pid"] == "5678"


@patch("services.processes.subprocess.run")
def test_get_top_processes_parse_error(mock_run):
    mock_run.return_value = Mock(
        returncode=0,
        stdout=(
            "USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND\n"
            "root 1234 invalid_cpu 5.0 100000 50000 ? S 10:00 00:01 python\n"
        ),
    )
    result = get_top_processes()
    assert result == []


@patch("services.processes.subprocess.run")
def test_get_top_processes_exception(mock_run):
    mock_run.side_effect = Exception("ps failed")
    result = get_top_processes()
    assert result == []


@patch("services.processes.get_top_processes")
def test_format_processes_text_exception(mock_get):
    mock_get.side_effect = Exception("format failed")
    text = format_processes_text()
    assert "Ошибка" in text


@patch("services.processes.get_top_processes")
def test_format_processes_text_long_command(mock_get):
    long_cmd = "a" * 60
    mock_get.return_value = [
        {
            "user": "root",
            "pid": "123",
            "cpu": 1.0,
            "mem": 1.0,
            "rss": 10,
            "command": long_cmd,
        }
    ]
    text = format_processes_text()
    assert "..." in text


@patch("services.processes.time.sleep")
@patch("services.processes.subprocess.run")
def test_kill_process_kill_15_error(mock_run, mock_sleep):
    mock_run.side_effect = [
        Mock(returncode=0),
        Mock(returncode=0, stdout="USER COMMAND\nroot python"),
        Mock(returncode=1, stderr="kill failed"),
    ]
    ok, msg = kill_process_by_pid("123")
    assert ok is False
    assert "Ошибка завершения" in msg


@patch("services.processes.time.sleep")
@patch("services.processes.subprocess.run")
def test_kill_process_exception(mock_run, mock_sleep):
    mock_run.side_effect = Exception("kill failed")
    ok, msg = kill_process_by_pid("123")
    assert ok is False
    assert "Ошибка" in msg


@patch("services.processes.subprocess.run")
def test_search_process_by_name_exception(mock_run):
    mock_run.side_effect = Exception("pgrep failed")
    text = search_process_by_name("python")
    assert "Ошибка" in text


@patch("services.processes.subprocess.run")
def test_get_top_processes_limit_break(mock_run):
    lines = ["USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND"]
    for i in range(15):
        lines.append(f"root {1000 + i} 1.0 1.0 1000 500 ? S 10:00 00:01 cmd{i}")
    mock_run.return_value = Mock(returncode=0, stdout="\n".join(lines))
    result = get_top_processes(limit=5)
    assert len(result) == 5


@patch("services.processes.subprocess.run")
def test_get_top_processes_ps_aux_filtered(mock_run):
    mock_run.return_value = Mock(
        returncode=0,
        stdout=(
            "USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND\n"
            "root 1111 1.0 1.0 1000 500 ? S 10:00 00:01 ps aux --sort=-%cpu\n"
            "root 5678 20.0 10.0 200000 100000 ? S 10:00 00:02 python bot.py\n"
        ),
    )
    result = get_top_processes()
    assert len(result) == 1
    assert result[0]["pid"] == "5678"
