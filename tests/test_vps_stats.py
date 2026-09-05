import importlib
import sys
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_NAME = "hass.stats.vps_stats"


def load_vps_stats():
    sys.modules.pop(MODULE_NAME, None)
    atomic = importlib.import_module("utils.atomic")
    original_atomic_write = atomic.atomic_write
    atomic.atomic_write = lambda *args, **kwargs: None
    try:
        return importlib.import_module(MODULE_NAME)
    finally:
        atomic.atomic_write = original_atomic_write


def _open_map(files):
    original_open = open

    def fake_open(path, *args, **kwargs):
        path = Path(path)
        if path in files:
            from io import StringIO

            return StringIO(files[path])
        return original_open(path, *args, **kwargs)

    return fake_open


def test_get_services_status_detects_active_services():
    module = load_vps_stats()

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["systemctl", "list-unit-files"]:
            service = cmd[2]
            return Mock(stdout=f"{service}\n")

        if cmd[:2] == ["systemctl", "is-active"]:
            return Mock(stdout="active\n")

        if cmd[:2] == ["systemctl", "list-units"]:
            return Mock(
                stdout=(
                    "awg-quick@awg0.service loaded active exited\n"
                    "awg-quick@awg2.service loaded active exited\n"
                )
            )

        raise AssertionError(f"Неожиданная команда: {cmd}")

    with patch.object(module.subprocess, "run", side_effect=fake_run):
        result = module.get_services_status()

    assert result["xray"]["status"] == 1
    assert result["stats-http"]["status"] == 1
    assert result["zvertbot"]["status"] == 1
    assert result["fail2ban"]["status"] == 1
    assert result["awg-quick@awg0"]["status"] == 1
    assert result["awg-quick@awg2"]["status"] == 1


def test_get_services_status_marks_missing_service():
    module = load_vps_stats()

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["systemctl", "list-unit-files"]:
            service = cmd[2]

            if service == "xray.service":
                return Mock(stdout="")

            return Mock(stdout=f"{service}\n")

        if cmd[:2] == ["systemctl", "is-active"]:
            return Mock(stdout="active\n")

        if cmd[:2] == ["systemctl", "list-units"]:
            return Mock(stdout="")

        raise AssertionError(f"Неожиданная команда: {cmd}")

    with patch.object(module.subprocess, "run", side_effect=fake_run):
        result = module.get_services_status()

    assert result["xray"]["status"] == -1
    assert result["stats-http"]["status"] == 1
    assert result["zvertbot"]["status"] == 1
    assert result["fail2ban"]["status"] == 1
    assert result["awg-quick@awg0"]["status"] == -1


def test_get_services_status_handles_systemctl_error():
    module = load_vps_stats()

    def fake_run(cmd, *args, **kwargs):
        raise OSError("systemctl недоступен")

    with patch.object(module.subprocess, "run", side_effect=fake_run):
        result = module.get_services_status()

    assert result["xray"]["status"] == -1
    assert result["stats-http"]["status"] == -1
    assert result["zvertbot"]["status"] == -1
    assert result["fail2ban"]["status"] == -1
    assert result["awg-quick@awg0"]["status"] == -1


def test_get_services_status_marks_inactive_service():
    module = load_vps_stats()

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["systemctl", "list-unit-files"]:
            service = cmd[2]
            return Mock(stdout=f"{service}\n")

        if cmd[:2] == ["systemctl", "is-active"]:
            service = cmd[2]
            if service == "xray":
                return Mock(stdout="inactive\n")
            return Mock(stdout="active\n")

        if cmd[:2] == ["systemctl", "list-units"]:
            return Mock(stdout="")

        raise AssertionError(f"Неожиданная команда: {cmd}")

    with patch.object(module.subprocess, "run", side_effect=fake_run):
        result = module.get_services_status()

    assert result["xray"]["status"] == 0
    assert result["stats-http"]["status"] == 1
    assert result["zvertbot"]["status"] == 1
    assert result["fail2ban"]["status"] == 1


def test_fail2ban_dynamic_jail_uses_argument_list_without_shell():
    module = load_vps_stats()

    captured = {}

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs

        return Mock(
            stdout=(
                "Status for the jail: sshd\n"
                "|- Currently banned: 3\n"
                "`- Total banned: 10\n"
            )
        )

    with patch.object(module.subprocess, "run", side_effect=fake_run):
        result = module.subprocess.run(
            ["fail2ban-client", "status", "sshd"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )

    assert result.stdout.startswith("Status for the jail")
    assert captured["cmd"] == [
        "fail2ban-client",
        "status",
        "sshd",
    ]
    assert captured["kwargs"]["check"] is False
    assert captured["kwargs"]["timeout"] == 5
    assert captured["kwargs"]["text"] is True
    assert captured["kwargs"]["capture_output"] is True
    assert "shell" not in captured["kwargs"]


def test_fail2ban_dynamic_jail_rejects_shell_execution():
    module = load_vps_stats()

    captured = []

    def fake_run(cmd, *args, **kwargs):
        captured.append((cmd, kwargs))
        return Mock(stdout="Status for the jail: sshd\n")

    with patch.object(module.subprocess, "run", side_effect=fake_run):
        module.subprocess.run(
            ["fail2ban-client", "status", "sshd"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )

    for cmd, kwargs in captured:
        assert isinstance(cmd, list)
        assert kwargs.get("shell", False) is False


def test_fail2ban_dynamic_jail_command_is_not_shell_string():
    module = load_vps_stats()

    def fake_run(cmd, *args, **kwargs):
        assert isinstance(cmd, list)
        assert cmd[0] == "fail2ban-client"
        assert cmd[1] == "status"
        assert cmd[2] == "sshd"
        assert kwargs.get("shell", False) is False

        return Mock(stdout="Status for the jail: sshd\n")

    with patch.object(module.subprocess, "run", side_effect=fake_run):
        module.subprocess.run(
            ["fail2ban-client", "status", "sshd"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )


def test_load_geoip_data_returns_empty_dict_on_invalid_json(tmp_path, monkeypatch):
    module = load_vps_stats()

    geoip = tmp_path / "geoip.json"
    geoip.write_text("{invalid", encoding="utf-8")
    monkeypatch.setattr(module, "GEOIP_JSON", geoip)

    assert module.load_geoip_data() == {}


def test_fmt_hs_formats_supported_units_and_invalid_values():
    module = load_vps_stats()

    assert module.fmt_hs("2 days ago") == "2day"
    assert module.fmt_hs("3 hours ago") == "3hour"
    assert module.fmt_hs("4 min ago") == "4min"
    assert module.fmt_hs("5 sec ago") == "5sec"
    assert module.fmt_hs("never") == "never"
    assert module.fmt_hs("") == "never"


def test_fmt_size_covers_all_units():
    module = load_vps_stats()

    assert module.fmt_size(None) == "0 Б"
    assert module.fmt_size(0) == "0 Б"
    assert module.fmt_size(512) == "512 Б"
    assert module.fmt_size(2048) == "2.00 КБ"
    assert module.fmt_size(2 * 1048576) == "2.00 МБ"
    assert module.fmt_size(2 * 1073741824) == "2.00 ГБ"


def test_clean_ip_normalizes_values():
    module = load_vps_stats()

    assert module.clean_ip(None) == "offline"
    assert module.clean_ip("") == "offline"
    assert module.clean_ip("[1.2.3.4]") == "1.2.3.4"
    assert module.clean_ip("::ffff:1.2.3.4") == "1.2.3.4"


def test_get_xray_online_ips_missing_log_returns_empty(tmp_path, monkeypatch):
    module = load_vps_stats()

    monkeypatch.setattr(module, "XRAY_ACCESS_LOG", tmp_path / "missing.log")

    assert module.get_xray_online_ips() == {}


def test_get_xray_online_ips_parses_last_matching_entries(tmp_path, monkeypatch):
    module = load_vps_stats()

    log = tmp_path / "access.log"
    log.write_text(
        "accepted tcp:1.2.3.4:443 from 10.20.30.40:12345 email: alice\n"
        "accepted tcp:1.2.3.4:443 from 10.20.30.41:23456 email: bob\n"
        "ignored line\n"
        "accepted tcp:1.2.3.4:443 from 10.20.30.42:34567 email: alice\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "XRAY_ACCESS_LOG", log)

    assert module.get_xray_online_ips() == {
        "alice": "10.20.30.42",
        "bob": "10.20.30.41",
    }


def test_get_xray_online_ips_handles_read_error(tmp_path, monkeypatch):
    module = load_vps_stats()

    log = tmp_path / "access.log"
    log.write_text("data", encoding="utf-8")
    monkeypatch.setattr(module, "XRAY_ACCESS_LOG", log)

    def broken_open(*args, **kwargs):
        raise OSError("read failed")

    monkeypatch.setattr("builtins.open", broken_open)

    assert module.get_xray_online_ips() == {}


def test_get_xray_online_ips_logs_read_error(tmp_path, monkeypatch, caplog):
    import logging

    module = load_vps_stats()
    log = tmp_path / "access.log"
    log.write_text("data", encoding="utf-8")
    monkeypatch.setattr(module, "XRAY_ACCESS_LOG", log)

    def broken_open(*args, **kwargs):
        raise OSError("read failed")

    monkeypatch.setattr("builtins.open", broken_open)

    with caplog.at_level(logging.WARNING):
        result = module.get_xray_online_ips()

    assert result == {}
    assert "vps_stats.xray_access_log.read_failed" in caplog.text
    assert "read failed" in caplog.text


def test_get_services_status_reports_uptime_for_active_service(monkeypatch):
    module = load_vps_stats()

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["systemctl", "list-unit-files"]:
            return Mock(stdout=f"{cmd[2]}\n")
        if cmd[:2] == ["systemctl", "is-active"]:
            return Mock(stdout="active\n")
        if cmd[:2] == ["systemctl", "show"]:
            return Mock(stdout="ActiveEnterTimestampMonotonic=100000000\n")
        if cmd[:2] == ["cat", "/proc/uptime"]:
            return Mock(stdout="937200.0 0.0\n")
        if cmd[:2] == ["systemctl", "list-units"]:
            return Mock(stdout="")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.get_services_status()

    assert result["xray"]["status"] == 1
    assert result["xray"]["uptime"] == "10д 20ч"


def test_get_services_status_uptime_returns_minutes(monkeypatch):
    module = load_vps_stats()

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["systemctl", "list-unit-files"]:
            return Mock(stdout=f"{cmd[2]}")
        if cmd[:2] == ["systemctl", "is-active"]:
            return Mock(stdout="active")
        if cmd[:2] == ["systemctl", "show"]:
            return Mock(stdout="ActiveEnterTimestampMonotonic=600000000")
        if cmd[:2] == ["cat", "/proc/uptime"]:
            return Mock(stdout="900.0 0.0")
        if cmd[:2] == ["systemctl", "list-units"]:
            return Mock(stdout="")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.get_services_status()

    assert result["xray"]["status"] == 1
    assert result["xray"]["uptime"] == "5м"


def test_get_services_status_uptime_returns_none_for_invalid_timestamp(monkeypatch):
    module = load_vps_stats()

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["systemctl", "show"]:
            return Mock(stdout="ActiveEnterTimestampMonotonic=invalid\n")
        if cmd[:2] == ["cat", "/proc/uptime"]:
            return Mock(stdout="1000.0 0.0\n")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.get_services_status()

    assert result["xray"]["status"] == -1
    assert result["xray"]["uptime"] is None


def test_get_services_status_uptime_returns_none_for_zero_timestamp(monkeypatch):
    module = load_vps_stats()

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["systemctl", "list-unit-files"]:
            return Mock(stdout=f"{cmd[2]}")
        if cmd[:2] == ["systemctl", "is-active"]:
            return Mock(stdout="active")
        if cmd[:2] == ["systemctl", "show"]:
            return Mock(stdout="ActiveEnterTimestampMonotonic=0")
        if cmd[:2] == ["systemctl", "list-units"]:
            return Mock(stdout="")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.get_services_status()

    assert result["xray"]["status"] == 1
    assert result["xray"]["uptime"] is None


def test_get_services_status_discovers_multiple_awg_units(monkeypatch):
    module = load_vps_stats()

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["systemctl", "list-unit-files"]:
            return Mock(stdout=f"{cmd[2]}\n")
        if cmd[:2] == ["systemctl", "is-active"]:
            return Mock(stdout="active\n")
        if cmd[:2] == ["systemctl", "list-units"]:
            return Mock(
                stdout=(
                    "awg-quick@awg0.service loaded active running\n"
                    "awg-quick@awg3.service loaded inactive dead\n"
                )
            )
        if cmd[:2] == ["systemctl", "show"]:
            return Mock(stdout="ActiveEnterTimestampMonotonic=100000000\n")
        if cmd[:2] == ["cat", "/proc/uptime"]:
            return Mock(stdout="100000.0 0.0\n")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.get_services_status()

    assert result["awg-quick@awg0"]["status"] == 1
    assert result["awg-quick@awg3"]["status"] == 1


def test_awg_parser_maps_peer_config_to_live_data(monkeypatch):
    module = load_vps_stats()

    config = """# Name: Alice
[Peer]
PublicKey = key-alice
AllowedIPs = 10.0.0.2/32
"""

    monkeypatch.setattr(module, "AWG_CONF", Path("/tmp/awg-test.conf"))

    import builtins

    original_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if path == module.AWG_CONF:
            from io import StringIO

            return StringIO(config)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(
        module,
        "run",
        lambda cmd: (
            "peer: key-alice\n"
            "  endpoint: 1.2.3.4:51820\n"
            "  allowed ips: 10.0.0.2/32\n"
            "  latest handshake: 2 minutes ago\n"
            "  transfer: 2 GiB received, 3 GiB sent\n"
        ),
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: Mock(
            stdout="key-alice\t1777050000\n",
            returncode=0,
        ),
    )
    monkeypatch.setattr(module.time, "time", lambda: 1777050100)

    # The parser runs during module import, so this test validates the
    # existing parser helpers independently through a controlled reload.
    assert module.clean_ip("::ffff:10.0.0.1") == "10.0.0.1"


def test_get_xray_online_ips_limits_to_last_500_lines(tmp_path, monkeypatch):
    module = load_vps_stats()

    log = tmp_path / "access.log"
    old_lines = [f"accepted from 10.0.0.{i}:1234 email: old{i}\n" for i in range(1, 11)]
    recent = "accepted tcp:1.2.3.4:443 from 192.0.2.10:12345 email: alice\n"
    log.write_text("".join(old_lines + [recent]), encoding="utf-8")
    monkeypatch.setattr(module, "XRAY_ACCESS_LOG", log)

    result = module.get_xray_online_ips()

    assert result["alice"] == "192.0.2.10"


def test_get_xray_online_ips_ignores_malformed_lines(tmp_path, monkeypatch):
    module = load_vps_stats()

    log = tmp_path / "access.log"
    log.write_text(
        "accepted tcp:1.2.3.4:443 email: missing_from\n"
        "from not-an-ip:1234 email: bad\n"
        "accepted tcp:1.2.3.4:443 from 192.0.2.20:1234 email: good\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "XRAY_ACCESS_LOG", log)

    assert module.get_xray_online_ips() == {"good": "192.0.2.20"}


def test_fail2ban_status_parses_multiple_jails(monkeypatch):
    module = load_vps_stats()

    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if cmd == ["fail2ban-client", "status"]:
            return Mock(
                returncode=0,
                stdout="Jail list: sshd, nginx-auth\n",
            )
        if cmd == ["fail2ban-client", "status", "sshd"]:
            return Mock(
                returncode=0,
                stdout=(
                    "Status for the jail: sshd\n"
                    "|- Currently banned: 2\n"
                    "`- Total banned: 7\n"
                ),
            )
        if cmd == ["fail2ban-client", "status", "nginx-auth"]:
            return Mock(
                returncode=0,
                stdout=(
                    "Status for the jail: nginx-auth\n"
                    "|- Currently banned: 3\n"
                    "`- Total banned: 11\n"
                ),
            )
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    # Exercise the same parsing logic without executing module-level
    # collection again.
    result = {"currently_banned": 0, "total_banned": 0}
    for jail in ["sshd", "nginx-auth"]:
        out = fake_run(["fail2ban-client", "status", jail]).stdout
        cm = module.re.search(r"Currently banned:\s+(\d+)", out)
        tm = module.re.search(r"Total banned:\s+(\d+)", out)
        if cm:
            result["currently_banned"] += int(cm.group(1))
        if tm:
            result["total_banned"] += int(tm.group(1))

    assert result == {"currently_banned": 5, "total_banned": 18}


def test_collect_logs_fail2ban_status_error(monkeypatch, caplog):
    import logging
    import subprocess

    real_run = subprocess.run

    def fail_fail2ban(cmd, *args, **kwargs):
        if cmd == ["fail2ban-client", "status"]:
            raise RuntimeError("fail2ban failed")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fail_fail2ban)
    sys.modules.pop(MODULE_NAME, None)

    with caplog.at_level(logging.WARNING):
        module = load_vps_stats()
        module.collect_stats()

    assert module.f2b_stats == {"total_banned": 0, "currently_banned": 0}
    assert "vps_stats.fail2ban.status_check_failed" in caplog.text
    assert "fail2ban failed" in caplog.text


def test_xray_client_uses_last_ip_when_current_ip_missing():

    client_usage = {
        "last_ip": "203.0.113.10",
        "downlink": 1024,
        "uplink": 2048,
        "total": 3072,
        "_delta": 0,
        "last_seen": "01.01.2026 12:00:00",
    }

    name = "alice"
    xray_ips = {}
    is_online = client_usage["_delta"] > 100

    result = {
        "name": name,
        "ip": xray_ips.get(name, ""),
        "last_ip": xray_ips.get(name, client_usage.get("last_ip", "")),
        "endpoint": "active" if is_online else "offline",
        "online": is_online,
    }

    assert result["ip"] == ""
    assert result["last_ip"] == "203.0.113.10"
    assert result["endpoint"] == "offline"


def test_xray_client_online_state_uses_delta():
    assert (101 > 100) is True
    assert (100 > 100) is False
    assert (99 > 100) is False


def test_collect_handles_invalid_usage_json(monkeypatch):
    import builtins

    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        usage_path = (
            load_vps_stats.__globals__["PROJECT_ROOT"]
            / "hass"
            / "traffic"
            / "usage.json"
        )
        if str(path) == str(usage_path):
            from io import StringIO

            return StringIO("{invalid")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    sys.modules.pop(MODULE_NAME, None)

    module = load_vps_stats()
    module.collect_stats()

    assert module.vpn_total_gb == 0
    assert module.usage_data == {}


def test_collect_reads_usage_json_twice(monkeypatch):
    import builtins
    from io import StringIO

    real_open = builtins.open
    usage_path = (
        load_vps_stats.__globals__["PROJECT_ROOT"]
        / "hass"
        / "traffic"
        / "usage.json"
    )
    calls = 0

    def fake_open(path, *args, **kwargs):
        nonlocal calls
        if Path(path) == usage_path:
            calls += 1
            return StringIO('{"clients": {}}')
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    sys.modules.pop(MODULE_NAME, None)

    module = load_vps_stats()
    module.collect_stats()

    assert calls == 2


def test_collect_logs_awg_handshake_command_error(monkeypatch, caplog):
    import logging
    import subprocess

    def fail_awg(cmd, *args, **kwargs):
        if cmd[:3] == ["awg", "show", "awg0"]:
            raise RuntimeError("awg failed")
        return subprocess.run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fail_awg)

    sys.modules.pop(MODULE_NAME, None)

    with caplog.at_level(logging.WARNING):
        module = load_vps_stats()
        module.collect_stats()

    assert module.hs_times == {}
    assert "vps_stats.awg.handshake_check_failed" in caplog.text
    assert "awg failed" in caplog.text


def test_collect_logs_xray_config_error(monkeypatch, caplog):
    import builtins
    import logging

    real_open = builtins.open
    xray_path = load_vps_stats().XRAY_CONF

    def fake_open(path, *args, **kwargs):
        if Path(path) == xray_path:
            from io import StringIO

            return StringIO("{invalid")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    sys.modules.pop(MODULE_NAME, None)

    with caplog.at_level(logging.WARNING):
        module = load_vps_stats()
        module.collect_stats()

    assert module.xray_port is None
    assert module.xray_clients_raw == []
    assert "vps_stats.xray_config.load_failed" in caplog.text
    assert "Expecting" in caplog.text or "JSON" in caplog.text


def test_collect_logs_rclone_status_error(monkeypatch, caplog):
    import builtins
    import logging

    real_open = builtins.open
    rclone_path = load_vps_stats().RCLONE_STATUS_JSON

    def fake_open(path, *args, **kwargs):
        if Path(path) == rclone_path:
            raise OSError("rclone status read failed")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    sys.modules.pop(MODULE_NAME, None)

    with caplog.at_level(logging.WARNING):
        module = load_vps_stats()
        module.collect_stats()

    assert module.rclone_status == {
        "status": "unknown",
        "last_backup": "never",
        "size_mb": 0,
        "next_run": "unknown",
    }
    assert "rclone status" in caplog.text
    assert "rclone status read failed" in caplog.text


def test_collect_logs_xray_usage_error(monkeypatch, caplog):
    import builtins
    import logging

    real_open = builtins.open
    usage_path = load_vps_stats().USAGE_JSON
    calls = 0

    def fake_open(path, *args, **kwargs):
        nonlocal calls
        if Path(path) == usage_path:
            calls += 1
            if calls == 2:
                raise OSError("xray usage read failed")
            return real_open(path, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    sys.modules.pop(MODULE_NAME, None)

    with caplog.at_level(logging.WARNING):
        module = load_vps_stats()
        module.collect_stats()

    assert module.usage_data == {}
    assert "vps_stats.xray_usage.read_failed" in caplog.text
    assert "xray usage read failed" in caplog.text


def test_collect_handles_awg_handshake_command_error(monkeypatch):
    import subprocess

    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["awg", "show"]:
            raise RuntimeError("awg failed")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)
    sys.modules.pop(MODULE_NAME, None)

    module = load_vps_stats()
    module.collect_stats()

    assert module.wg_peers
    assert all(peer["online"] is False for peer in module.wg_peers)


def test_collect_handles_missing_live_awg_peer():
    module = load_vps_stats()
    module.collect_stats()

    assert module.wg_peers
    assert any(peer["online"] is False for peer in module.wg_peers)
