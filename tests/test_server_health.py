"""
Тесты services.server_health.
"""

from services import server_health


def test_collect_server_health_contains_sections(monkeypatch):
    monkeypatch.setattr(
        server_health,
        "_run",
        lambda cmd, timeout=5: "test-data",
    )

    result = server_health.collect_server_health()

    assert "=== SYSTEM ===" in result
    assert "=== SERVICES ===" in result
    assert "=== SECURITY EVENTS ===" in result
    assert "=== SYSTEM ERRORS ===" in result
    assert "=== FIREWALL ===" in result


def test_collect_server_health_handles_empty_commands(monkeypatch):
    monkeypatch.setattr(
        server_health,
        "_run",
        lambda cmd, timeout=5: "",
    )

    result = server_health.collect_server_health()

    assert "=== SYSTEM ===" in result
    assert "=== SERVICES ===" in result
    assert "No SSH events" in result
    assert "No system errors" in result or "iptables not installed" in result


def test_run_returns_stripped_stdout(monkeypatch):
    class Result:
        stdout = "  test output  \n"

    def fake_run(cmd, capture_output, text, timeout):
        assert cmd == ["echo", "test"]
        assert capture_output is True
        assert text is True
        assert timeout == 7
        return Result()

    monkeypatch.setattr(server_health.subprocess, "run", fake_run)

    assert server_health._run(["echo", "test"], timeout=7) == "test output"


def test_run_returns_empty_string_on_exception(monkeypatch):
    def fake_run(*args, **kwargs):
        raise RuntimeError("command failed")

    monkeypatch.setattr(server_health.subprocess, "run", fake_run)

    assert server_health._run(["false"]) == ""


def test_collect_server_health_includes_command_results(monkeypatch):
    values = {
        ("uptime", "-p"): "up 3 days",
        ("cat", "/proc/loadavg"): "0.12 0.34 0.56 1/100 12345",
        ("free", "-h"): "Mem: 4Gi 2Gi 2Gi",
        ("df", "-h", "/"): "/dev/vda1 20G 10G 10G 50% /",
        (
            "journalctl",
            "-u",
            "ssh",
            "-n",
            "30",
            "--no-pager",
        ): "Aug 27 ssh event",
        (
            "journalctl",
            "-p",
            "err",
            "-n",
            "30",
            "--no-pager",
        ): "Aug 27 system error",
        (
            "iptables",
            "-L",
            "-n",
            "--line-numbers",
        ): "line1\nline2\nline3",
    }

    def fake_run(cmd, timeout=5):
        return values.get(tuple(cmd), "")

    monkeypatch.setattr(server_health, "_run", fake_run)
    monkeypatch.setattr(
        server_health,
        "get_service_state",
        lambda service: {
            "xray": "active",
            "zvertbot": "active",
            "fail2ban": "active",
            "stats-http": "active",
            "awg-quick@awg0": "inactive",
        }[service],
    )
    monkeypatch.setattr(
        server_health.shutil,
        "which",
        lambda name: "/usr/sbin/iptables",
    )

    result = server_health.collect_server_health()

    assert "Uptime: up 3 days" in result
    assert "Load: 0.12 0.34 0.56" in result
    assert "RAM:\nMem: 4Gi 2Gi 2Gi" in result
    assert "Disk:\n/dev/vda1 20G 10G 10G 50% /" in result

    assert "xray: active" in result
    assert "zvertbot: active" in result
    assert "fail2ban: active" in result
    assert "stats-http: active" in result
    assert "awg-quick@awg0: inactive" in result

    assert "Aug 27 ssh event" in result
    assert "Aug 27 system error" in result
    assert "Rules lines: 3" in result


def test_collect_server_health_handles_iptables_without_data(monkeypatch):
    monkeypatch.setattr(
        server_health,
        "_run",
        lambda cmd, timeout=5: "",
    )
    monkeypatch.setattr(
        server_health.shutil,
        "which",
        lambda name: "/usr/sbin/iptables",
    )

    result = server_health.collect_server_health()

    assert "No data" in result
    assert "iptables not installed" not in result


def test_collect_server_health_handles_missing_iptables(monkeypatch):
    monkeypatch.setattr(
        server_health,
        "_run",
        lambda cmd, timeout=5: "",
    )
    monkeypatch.setattr(
        server_health.shutil,
        "which",
        lambda name: None,
    )

    result = server_health.collect_server_health()

    assert "iptables not installed" in result


def test_collect_monitoring_facts_formats_check_results(monkeypatch):
    from services.vps_monitor import MonitorCategory, MonitorFailure, MonitorResult

    monkeypatch.setattr(
        server_health,
        "check_all",
        lambda: [
            MonitorResult(
                name="xray",
                category=MonitorCategory.OPTIONAL,
                healthy=False,
                details="active; TCP 443 unreachable",
                failure=MonitorFailure.TCP_FAILED,
            ),
            MonitorResult(
                name="stats-http",
                category=MonitorCategory.CRITICAL,
                healthy=True,
                details="HTTP 200",
            ),
        ],
    )

    result = server_health.collect_monitoring_facts()

    assert "MONITORING FACT | xray | category=optional | status=FAIL" in result
    assert "failure=tcp_failed" in result
    assert "MONITORING FACT | stats-http | category=critical | status=OK" in result


def test_collect_server_health_for_ai_appends_monitoring(monkeypatch):
    monkeypatch.setattr(server_health, "collect_server_health", lambda: "HEALTH")
    monkeypatch.setattr(
        server_health,
        "collect_monitoring_facts",
        lambda: "MONITORING FACT | xray | status=OK",
    )

    result = server_health.collect_server_health_for_ai()

    assert result == (
        "HEALTH\n\n=== MONITORING FACTS ===\n"
        "MONITORING FACT | xray | status=OK"
    )


def test_collect_monitoring_facts_hides_check_exception_details(monkeypatch):
    def fail():
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(server_health, "check_all", fail)

    assert server_health.collect_monitoring_facts() == (
        "MONITORING FACT | checks unavailable"
    )
