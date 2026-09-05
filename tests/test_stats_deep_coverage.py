"""
Глубокое покрытие services/stats.py
"""

import io
import json
from unittest.mock import Mock, patch

import services.stats as st

# ---------------------------------------------------------
# _build_status_text
# ---------------------------------------------------------


def test_build_status_services_missing(monkeypatch, tmp_path):
    stats = tmp_path / "stats.json"

    stats.write_text(
        json.dumps(
            {
                "cpu": 1,
                "mem": 2,
                "disk": {},
            }
        )
    )

    monkeypatch.setattr(st, "STATS_JSON", str(stats))

    _real_open = open

    def fake_open(path, *args, **kwargs):
        if path == "/proc/uptime":
            return io.StringIO("1000 0\n")
        if path == "/proc/meminfo":
            return io.StringIO("SwapTotal:       1024 kB\nSwapFree:         512 kB\n")
        return _real_open(path, *args, **kwargs)

    with patch("builtins.open", side_effect=fake_open):
        result = st._build_status_text()

    assert "VPS ОТЧЕТ" in result


def test_build_status_unknown_service_state(monkeypatch, tmp_path):

    stats = tmp_path / "stats.json"

    stats.write_text(json.dumps({"services": {"test": 99}}))

    monkeypatch.setattr(st, "STATS_JSON", str(stats))

    result = st._build_status_text()

    assert "не установлен" in result


def test_build_status_meminfo_error(monkeypatch, tmp_path):

    stats = tmp_path / "stats.json"

    stats.write_text(json.dumps({}))

    monkeypatch.setattr(st, "STATS_JSON", str(stats))

    original_open = open

    def fake_open(path, *args, **kwargs):
        if path == "/proc/meminfo":
            raise Exception("mem fail")
        return original_open(path, *args, **kwargs)

    with patch("builtins.open", side_effect=fake_open):
        result = st._build_status_text()

    assert "Swap" in result


def test_build_status_proc_error(monkeypatch, tmp_path):

    stats = tmp_path / "stats.json"

    stats.write_text(json.dumps({}))

    monkeypatch.setattr(st, "STATS_JSON", str(stats))

    with patch("os.listdir", side_effect=Exception("proc fail")):
        result = st._build_status_text()

    assert "Процессы" in result


def test_status_text_calls_builder_each_time(monkeypatch):

    fake = Mock(return_value="OK")

    monkeypatch.setattr(st, "_build_status_text", fake)

    first = st.get_status_text()
    second = st.get_status_text()

    assert first == "OK"
    assert second == "OK"

    assert fake.call_count == 2


# ---------------------------------------------------------
# AWG edge
# ---------------------------------------------------------


def test_awg_registry_without_ip(monkeypatch):

    monkeypatch.setattr(st, "load_awg_registry", lambda: {"user": {}})

    result = st.get_client_stats_text("user", "awg")

    assert "Нет IP" in result


def test_awg_handshake_empty(monkeypatch):

    monkeypatch.setattr(st, "load_awg_registry", lambda: {"user": {"ip": "10.0.0.2"}})

    monkeypatch.setattr(
        st, "get_client_traffic", lambda x: {"uplink": 0, "downlink": 0, "total": 0}
    )

    with patch("subprocess.run", return_value=Mock(stdout="")):
        result = st.get_client_stats_text("user", "awg")

    assert "Оффлайн" in result


def test_awg_command_exception(monkeypatch):

    monkeypatch.setattr(st, "load_awg_registry", lambda: {"user": {"ip": "10.0.0.3"}})

    monkeypatch.setattr(
        st, "get_client_traffic", lambda x: {"uplink": 1, "downlink": 2, "total": 3}
    )

    with patch("subprocess.run", side_effect=Exception("awg fail")):
        result = st.get_client_stats_text("user", "awg")

    assert "Оффлайн" in result


# ---------------------------------------------------------
# VLESS
# ---------------------------------------------------------


def test_vless_client_missing_fields(monkeypatch):

    monkeypatch.setattr(st, "load_usage", lambda: {"clients": {"test": {}}})

    result = st.get_client_stats_text("test", "vless")

    assert "Итого" in result


def test_vless_bad_usage(monkeypatch):

    monkeypatch.setattr(st, "load_usage", lambda: None)

    result = st.get_client_stats_text("test", "vless")

    assert "Ожидание" in result


def test_build_status_process_count_error_logs_standardized_event(
    monkeypatch,
    tmp_path,
):
    stats = tmp_path / "stats.json"
    stats.write_text("{}")
    monkeypatch.setattr(st, "STATS_JSON", str(stats))

    monkeypatch.setattr(
        st.os,
        "listdir",
        Mock(side_effect=OSError("proc list failed")),
    )

    with patch("services.stats.logger.exception") as mock_exception:
        st.get_status_text()

    calls = [
        call for call in mock_exception.call_args_list
        if call.args
        and call.args[0] == "stats.status.process_count_failed | error=%s"
    ]
    assert len(calls) == 1
    assert isinstance(calls[0].args[1], OSError)


def test_get_bot_stats_text_logs_standardized_error(monkeypatch):
    error = RuntimeError("stats generation failed")
    monkeypatch.setattr(st, "load_stats", Mock(side_effect=error))

    with patch("services.stats.logger.error") as mock_error:
        result = st.get_bot_stats_text()

    assert "Ошибка чтения статистики" in result
    mock_error.assert_called_once_with(
        "stats.bot.generate_failed | error=%s",
        error,
    )


def test_get_client_stats_text_logs_standardized_awg_error(monkeypatch):
    error = RuntimeError("awg status failed")

    monkeypatch.setattr(
        st,
        "load_awg_registry",
        lambda: {"user": {"ip": "10.0.0.2"}},
    )
    monkeypatch.setattr(
        st,
        "get_client_traffic",
        lambda username: {
            "uplink": 0,
            "downlink": 0,
            "total": 0,
        },
    )
    monkeypatch.setattr(
        st.subprocess,
        "run",
        Mock(side_effect=error),
    )

    with patch("services.stats.logger.exception") as mock_exception:
        result = st.get_client_stats_text("user", "awg")

    assert "Оффлайн" in result
    mock_exception.assert_called_once_with(
        "stats.client.awg_status_failed | username=%s | error=%s",
        "user",
        error,
    )

def test_build_status_swap_error_logs_standardized_event(
    monkeypatch,
    tmp_path,
):
    import builtins

    stats = tmp_path / "stats.json"
    stats.write_text("{}")
    monkeypatch.setattr(st, "STATS_JSON", str(stats))

    original_open = builtins.open

    def broken_open(path, *args, **kwargs):
        if path == "/proc/meminfo":
            raise OSError("meminfo read failed")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", broken_open)

    with patch("services.stats.logger.exception") as mock_exception:
        st.get_status_text()

    mock_exception.assert_called_once()
    args = mock_exception.call_args.args
    assert args[0] == "stats.status.swap_read_failed | error=%s"
    assert isinstance(args[1], OSError)
    assert str(args[1]) == "meminfo read failed"
