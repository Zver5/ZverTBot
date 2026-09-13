import subprocess

from services.awg.runtime import (
    AwgPeerRuntime,
    _parse_show_output,
    extract_endpoint_ip,
    get_latest_handshakes,
    get_runtime_peers,
)


def test_extract_endpoint_ip():
    assert extract_endpoint_ip("192.0.2.10:51820") == "192.0.2.10"
    assert extract_endpoint_ip("[2001:db8::10]:51820") == "2001:db8::10"
    assert extract_endpoint_ip("192.0.2.10") == "192.0.2.10"
    assert extract_endpoint_ip("(none)") is None
    assert extract_endpoint_ip("") is None


def test_parse_show_output():
    output = """
interface: awg0
peer: KEY1
  endpoint: 192.0.2.10:51820
  allowed ips: 10.66.66.20/32
  latest handshake: 1 minute, 2 seconds ago
  transfer: 1.5 MiB received, 2 KiB sent
peer: KEY2
  endpoint: (none)
  allowed ips: 10.66.66.30/32
  latest handshake: never
  transfer: 500 B received, 3 GiB sent
"""

    result = _parse_show_output(output)

    assert result == {
        "KEY1": AwgPeerRuntime(
            public_key="KEY1",
            endpoint="192.0.2.10:51820",
            allowed_ip="10.66.66.20",
            rx_bytes=1572864,
            tx_bytes=2048,
            latest_handshake="1 minute, 2 seconds ago",
        ),
        "KEY2": AwgPeerRuntime(
            public_key="KEY2",
            endpoint="",
            allowed_ip="10.66.66.30",
            rx_bytes=500,
            tx_bytes=3221225472,
            latest_handshake="never",
        ),
    }


def test_parse_show_output_ignores_invalid_peer_data():
    output = """
peer:
  endpoint: 192.0.2.10:51820
peer: KEY1
  allowed ips: 10.66.66.20/32
  transfer: invalid
"""

    result = _parse_show_output(output)

    assert result["KEY1"].allowed_ip == "10.66.66.20"
    assert result["KEY1"].rx_bytes == 0
    assert result["KEY1"].tx_bytes == 0


def test_get_runtime_peers(monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["awg", "show", "awg0"],
        returncode=0,
        stdout="peer: KEY1\n  allowed ips: 10.66.66.20/32\n",
        stderr="",
    )

    monkeypatch.setattr(
        "services.awg.runtime.subprocess.run",
        lambda *args, **kwargs: completed,
    )

    result = get_runtime_peers()

    assert result["KEY1"].allowed_ip == "10.66.66.20"


def test_get_runtime_peers_returns_empty_on_command_failure(monkeypatch):
    def raise_error(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(
        "services.awg.runtime.subprocess.run",
        raise_error,
    )

    assert get_runtime_peers() == {}


def test_get_runtime_peers_returns_empty_on_timeout(monkeypatch):
    def raise_error(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 5)

    monkeypatch.setattr(
        "services.awg.runtime.subprocess.run",
        raise_error,
    )

    assert get_runtime_peers() == {}


def test_get_latest_handshakes(monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["awg", "show", "awg0", "latest-handshakes"],
        returncode=0,
        stdout="KEY1\t1757800000\nKEY2\t1757800010\n",
        stderr="",
    )

    monkeypatch.setattr(
        "services.awg.runtime.subprocess.run",
        lambda *args, **kwargs: completed,
    )

    assert get_latest_handshakes() == {
        "KEY1": 1757800000,
        "KEY2": 1757800010,
    }


def test_get_latest_handshakes_ignores_invalid_lines(monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["awg", "show", "awg0", "latest-handshakes"],
        returncode=0,
        stdout="KEY1\t123\ninvalid\nKEY2\tnot-a-number\n",
        stderr="",
    )

    monkeypatch.setattr(
        "services.awg.runtime.subprocess.run",
        lambda *args, **kwargs: completed,
    )

    assert get_latest_handshakes() == {"KEY1": 123}


def test_get_latest_handshakes_returns_empty_on_failure(monkeypatch):
    monkeypatch.setattr(
        "services.awg.runtime.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, args[0])
        ),
    )

    assert get_latest_handshakes() == {}
