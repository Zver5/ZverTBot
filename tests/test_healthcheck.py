import json
import subprocess
from pathlib import Path

from hass.health import healthcheck


def test_cmd_handles_timeout(monkeypatch):
    errors = []

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=5,
        )

    monkeypatch.setattr(healthcheck.subprocess, "run", fake_run)
    monkeypatch.setattr(
        healthcheck.logger,
        "error",
        lambda message, *args: errors.append((message, args)),
    )

    result = healthcheck.cmd(["systemctl", "is-active", "xray.service"])

    assert result is None
    assert errors == [
        (
            "healthcheck.command.timeout | args=%s",
            (["systemctl", "is-active", "xray.service"],),
        )
    ]


def test_cmd_handles_unexpected_exception(monkeypatch):
    exceptions = []

    def fake_run(*args, **kwargs):
        raise RuntimeError("test error")

    monkeypatch.setattr(healthcheck.subprocess, "run", fake_run)
    monkeypatch.setattr(
        healthcheck.logger,
        "exception",
        lambda message, *args: exceptions.append((message, args)),
    )

    result = healthcheck.cmd(["systemctl", "is-active", "xray.service"])

    assert result is None
    assert len(exceptions) == 1
    assert exceptions[0][0] == "healthcheck.command.failed | error=%s"
    assert len(exceptions[0][1]) == 1
    assert isinstance(exceptions[0][1][0], RuntimeError)
    assert str(exceptions[0][1][0]) == "test error"


def test_cmd_returns_completed_process(monkeypatch):
    expected = subprocess.CompletedProcess(
        ["echo", "ok"],
        0,
        stdout="ok\n",
        stderr="",
    )

    monkeypatch.setattr(
        healthcheck.subprocess,
        "run",
        lambda *args, **kwargs: expected,
    )

    result = healthcheck.cmd(["echo", "ok"])

    assert result is expected


def test_check_systemd_active(monkeypatch):
    result = subprocess.CompletedProcess(
        ["systemctl"],
        0,
        stdout="active\n",
        stderr="",
    )

    monkeypatch.setattr(healthcheck, "cmd", lambda args: result)

    assert healthcheck.check_systemd("xray.service") is True


def test_check_systemd_inactive(monkeypatch):
    result = subprocess.CompletedProcess(
        ["systemctl"],
        3,
        stdout="inactive\n",
        stderr="",
    )

    monkeypatch.setattr(healthcheck, "cmd", lambda args: result)

    assert healthcheck.check_systemd("xray.service") is False


def test_check_systemd_handles_no_result(monkeypatch):
    monkeypatch.setattr(healthcheck, "cmd", lambda args: None)

    assert healthcheck.check_systemd("xray.service") is False


def test_check_port_tcp_open(monkeypatch):
    result = subprocess.CompletedProcess(
        ["ss"],
        0,
        stdout="LISTEN 0 128 0.0.0.0:443 0.0.0.0:*\n",
        stderr="",
    )

    calls = []
    monkeypatch.setattr(
        healthcheck,
        "cmd",
        lambda args: calls.append(args) or result,
    )

    assert healthcheck.check_port("tcp", 443) is True
    assert calls == [["ss", "-tlnp"]]


def test_check_port_udp_open(monkeypatch):
    result = subprocess.CompletedProcess(
        ["ss"],
        0,
        stdout="UNCONN 0 0 0.0.0.0:58352 0.0.0.0:*\n",
        stderr="",
    )

    calls = []
    monkeypatch.setattr(
        healthcheck,
        "cmd",
        lambda args: calls.append(args) or result,
    )

    assert healthcheck.check_port("udp", 58352) is True
    assert calls == [["ss", "-ulnp"]]


def test_check_port_closed(monkeypatch):
    result = subprocess.CompletedProcess(
        ["ss"],
        0,
        stdout="LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\n",
        stderr="",
    )

    monkeypatch.setattr(healthcheck, "cmd", lambda args: result)

    assert healthcheck.check_port("tcp", 443) is False


def test_check_port_handles_no_result(monkeypatch):
    monkeypatch.setattr(healthcheck, "cmd", lambda args: None)

    assert healthcheck.check_port("tcp", 443) is False


def test_check_http_success(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        healthcheck.urllib.request,
        "urlopen",
        lambda url, timeout: Response(),
    )

    assert healthcheck.check_http("http://127.0.0.1/status") is True


def test_check_http_non_200(monkeypatch):
    class Response:
        status = 503

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        healthcheck.urllib.request,
        "urlopen",
        lambda url, timeout: Response(),
    )

    assert healthcheck.check_http("http://127.0.0.1/status") is False


def test_check_http_handles_exception(monkeypatch):
    exceptions = []

    def fake_urlopen(url, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(
        healthcheck.urllib.request,
        "urlopen",
        fake_urlopen,
    )
    monkeypatch.setattr(
        healthcheck.logger,
        "exception",
        lambda message, *args: exceptions.append((message, args)),
    )

    assert healthcheck.check_http("http://127.0.0.1/status") is False
    assert len(exceptions) == 1
    assert exceptions[0][0] == "healthcheck.http.failed | error=%s"
    assert len(exceptions[0][1]) == 1
    assert isinstance(exceptions[0][1][0], OSError)
    assert str(exceptions[0][1][0]) == "connection refused"


def test_check_tunnel_connected(monkeypatch):
    result = subprocess.CompletedProcess(
        ["ss"],
        0,
        stdout=f"ESTAB 0 0 10.0.0.1:22 {healthcheck.HA_TUNNEL_IP}:22\n",
        stderr="",
    )

    monkeypatch.setattr(healthcheck, "cmd", lambda args: result)

    assert healthcheck.check_tunnel() is True


def test_check_tunnel_disconnected(monkeypatch):
    result = subprocess.CompletedProcess(
        ["ss"],
        0,
        stdout="ESTAB 0 0 10.0.0.1:22 192.0.2.1:12345\n",
        stderr="",
    )

    monkeypatch.setattr(healthcheck, "cmd", lambda args: result)

    assert healthcheck.check_tunnel() is False


def test_check_tunnel_handles_no_result(monkeypatch):
    monkeypatch.setattr(healthcheck, "cmd", lambda args: None)

    assert healthcheck.check_tunnel() is False


def test_system_info(monkeypatch):
    class Disk:
        used = 75
        total = 100

    monkeypatch.setattr(
        healthcheck.shutil,
        "disk_usage",
        lambda path: Disk(),
    )
    monkeypatch.setattr(
        healthcheck.os,
        "getloadavg",
        lambda: (1.25, 0.5, 0.25),
    )

    values = {
        "SC_AVPHYS_PAGES": 25,
        "SC_PHYS_PAGES": 100,
    }
    monkeypatch.setattr(
        healthcheck.os,
        "sysconf",
        lambda name: values[name],
    )

    assert healthcheck.system_info() == {
        "load": 1.25,
        "ram": 75,
        "disk": 75,
    }


def test_run_checks_healthy(monkeypatch):
    monkeypatch.setattr(
        healthcheck,
        "check_systemd",
        lambda service: True,
    )
    monkeypatch.setattr(
        healthcheck,
        "check_port",
        lambda proto, port: True,
    )
    monkeypatch.setattr(
        healthcheck,
        "check_http",
        lambda url: True,
    )
    monkeypatch.setattr(
        healthcheck,
        "check_tunnel",
        lambda: True,
    )
    monkeypatch.setattr(
        healthcheck,
        "system_info",
        lambda: {"load": 1, "ram": 20, "disk": 30},
    )

    data, ok = healthcheck.run_checks()

    assert ok is True
    assert data["status"] == "healthy"
    assert data["failed"] == []
    assert data["checks"]["xray"]["systemd"] == "active"
    assert data["checks"]["xray"]["port"] == "open"
    assert data["checks"]["stats_http"]["http"] == "OK"
    assert data["checks"]["ha_tunnel"]["status"] == "ok"
    assert data["system"] == {"load": 1, "ram": 20, "disk": 30}
    assert "time" in data


def test_run_checks_required_failures_and_optional_failures(monkeypatch):
    def fake_systemd(service):
        return service not in {
            "stats-http.service",
            "ssh.service",
            "fail2ban.service",
        }

    def fake_port(proto, port):
        return port != 8080

    monkeypatch.setattr(healthcheck, "check_systemd", fake_systemd)
    monkeypatch.setattr(healthcheck, "check_port", fake_port)
    monkeypatch.setattr(healthcheck, "check_http", lambda url: False)
    monkeypatch.setattr(healthcheck, "check_tunnel", lambda: False)
    monkeypatch.setattr(
        healthcheck,
        "system_info",
        lambda: {"load": 2, "ram": 50, "disk": 80},
    )

    data, ok = healthcheck.run_checks()

    assert ok is False
    assert data["status"] == "degraded"

    assert data["checks"]["xray"]["status"] == "ok"
    assert data["checks"]["amnezia_wg"]["status"] == "ok"

    assert data["checks"]["stats_http"]["status"] == "fail"
    assert data["checks"]["stats_http"]["systemd"] == "failed"
    assert data["checks"]["stats_http"]["port"] == "closed"
    assert data["checks"]["stats_http"]["http"] == "FAILED"

    assert data["checks"]["ssh"]["status"] == "fail"
    assert data["checks"]["fail2ban"]["status"] == "fail"

    assert data["checks"]["ha_tunnel"] == {
        "status": "fail",
        "reason": "SSH tunnel disconnected",
    }

    failed_services = {item["service"] for item in data["failed"]}

    assert failed_services == {
        "stats_http",
        "ssh",
        "fail2ban",
        "ha_tunnel",
    }


def test_handler_returns_404_for_unknown_path(monkeypatch):
    handler = object.__new__(healthcheck.Handler)
    handler.path = "/unknown"
    handler.send_response = lambda status: setattr(
        handler,
        "_response_status",
        status,
    )
    handler.end_headers = lambda: None

    handler.do_GET()

    assert handler._response_status == 404


def test_handler_returns_200_for_healthy_status(monkeypatch):
    handler = object.__new__(healthcheck.Handler)
    handler.path = "/status"

    body = []

    handler.send_response = lambda status: setattr(
        handler,
        "_response_status",
        status,
    )
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None

    class Writer:
        def write(self, data):
            body.append(data)

    handler.wfile = Writer()

    monkeypatch.setattr(
        healthcheck,
        "run_checks",
        lambda: (
            {
                "status": "healthy",
                "failed": [],
                "checks": {},
                "system": {},
                "time": "now",
            },
            True,
        ),
    )

    handler.do_GET()

    assert handler._response_status == 200
    assert json.loads(body[0])["status"] == "healthy"


def test_handler_returns_503_for_degraded_status(monkeypatch):
    handler = object.__new__(healthcheck.Handler)
    handler.path = "/status"

    body = []

    handler.send_response = lambda status: setattr(
        handler,
        "_response_status",
        status,
    )
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None

    class Writer:
        def write(self, data):
            body.append(data)

    handler.wfile = Writer()

    monkeypatch.setattr(
        healthcheck,
        "run_checks",
        lambda: (
            {
                "status": "degraded",
                "failed": [{"service": "ssh"}],
                "checks": {},
                "system": {},
                "time": "now",
            },
            False,
        ),
    )

    handler.do_GET()

    assert handler._response_status == 503
    assert json.loads(body[0])["status"] == "degraded"


def test_handler_log_message_is_silent():
    handler = object.__new__(healthcheck.Handler)

    assert handler.log_message("ignored", "value") is None


def test_main_starts_healthcheck_server(monkeypatch):
    calls = []

    class FakeHTTPServer:
        def __init__(self, address, handler):
            calls.append(("init", address, handler))

        def serve_forever(self):
            calls.append(("serve_forever",))

    source = Path("hass/health/healthcheck.py").read_text(
        encoding="utf-8",
    )

    namespace = {
        "__name__": "__main__",
        "__file__": str(Path("hass/health/healthcheck.py").resolve()),
    }

    real_http_server = healthcheck.http.server.HTTPServer
    monkeypatch.setattr(
        healthcheck.http.server,
        "HTTPServer",
        FakeHTTPServer,
    )

    exec(
        compile(source, "hass/health/healthcheck.py", "exec"),
        namespace,
    )

    assert calls[0][0] == "init"
    assert calls[0][1] == ("0.0.0.0", 8081)
    assert calls[0][2] is namespace["Handler"]
    assert calls[1] == ("serve_forever",)

    monkeypatch.setattr(
        healthcheck.http.server,
        "HTTPServer",
        real_http_server,
    )


def test_check_tunnel_disabled_without_ha_ip(monkeypatch):
    monkeypatch.setattr(healthcheck, "HA_TUNNEL_IP", "")

    assert healthcheck.check_tunnel() is True


def test_check_tunnel_detects_established_ssh_tunnel(monkeypatch):
    monkeypatch.setattr(healthcheck, "HA_TUNNEL_IP", "10.20.30.40")

    class Result:
        stdout = (
            "State Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
            "ESTAB 0 0 192.168.1.10:22 10.20.30.40:22\n"
        )

    monkeypatch.setattr(
        healthcheck,
        "cmd",
        lambda args: Result(),
    )

    assert healthcheck.check_tunnel() is True


def test_check_tunnel_accepts_any_remote_port(monkeypatch):
    monkeypatch.setattr(healthcheck, "HA_TUNNEL_IP", "10.20.30.40")

    class Result:
        stdout = "ESTAB 0 0 192.168.1.10:22 10.20.30.40:4168\\n"

    monkeypatch.setattr(
        healthcheck,
        "cmd",
        lambda args: Result(),
    )

    assert healthcheck.check_tunnel() is True


def test_check_tunnel_ignores_other_ssh_connections(monkeypatch):
    monkeypatch.setattr(healthcheck, "HA_TUNNEL_IP", "10.20.30.40")

    class Result:
        stdout = (
            "ESTAB 0 0 192.168.1.10:22 10.20.30.50:22\n"
            "ESTAB 0 0 192.168.1.10:443 10.20.30.40:443\n"
        )

    monkeypatch.setattr(
        healthcheck,
        "cmd",
        lambda args: Result(),
    )

    assert healthcheck.check_tunnel() is False


def test_check_tunnel_handles_command_failure(monkeypatch):
    monkeypatch.setattr(healthcheck, "HA_TUNNEL_IP", "10.20.30.40")
    monkeypatch.setattr(healthcheck, "cmd", lambda args: None)

    assert healthcheck.check_tunnel() is False


def test_run_checks_marks_tunnel_failure(monkeypatch):
    monkeypatch.setattr(healthcheck, "HA_TUNNEL_IP", "10.20.30.40")
    monkeypatch.setattr(healthcheck, "check_tunnel", lambda: False)

    data, ok = healthcheck.run_checks()

    assert ok is False
    assert data["status"] == "degraded"
    assert data["checks"]["ha_tunnel"]["status"] == "fail"
    assert data["checks"]["ha_tunnel"]["reason"] == "SSH tunnel disconnected"
    assert {
        "service": "ha_tunnel",
        "reason": "SSH tunnel disconnected",
    } in data["failed"]
