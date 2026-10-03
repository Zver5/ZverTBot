"""Runtime state reader for AmneziaWG."""

from __future__ import annotations

import ipaddress
import re
import subprocess
from dataclasses import dataclass

from utils.service_control import list_service_units


@dataclass(frozen=True)
class AwgPeerRuntime:
    """Raw runtime state reported by awg."""

    public_key: str
    endpoint: str
    allowed_ip: str
    rx_bytes: int
    tx_bytes: int
    latest_handshake: str


def extract_endpoint_ip(endpoint: str) -> str | None:
    """Extract a normalized IP address from an AWG endpoint."""
    value = endpoint.strip()

    if not value:
        return None

    if value.startswith("["):
        end = value.find("]")
        if end == -1:
            return None
        value = value[1:end]
    else:
        host, separator, port = value.rpartition(":")
        if separator and port.isdigit():
            value = host

    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _parse_transfer(value: str) -> int:
    match = re.search(
        r"([0-9]+(?:\.[0-9]+)?)\s*(B|KiB|MiB|GiB)",
        value,
        re.IGNORECASE,
    )
    if not match:
        return 0

    amount = float(match.group(1))
    unit = match.group(2).lower()
    return int(
        amount
        * {
            "b": 1,
            "kib": 1024,
            "mib": 1024**2,
            "gib": 1024**3,
        }[unit]
    )


def _normalize_endpoint(value: str) -> str:
    value = value.strip()
    if value.lower() in {"(none)", "(no endpoint)", "-"}:
        return ""
    return value


def _parse_show_output(output: str) -> dict[str, AwgPeerRuntime]:
    peers: dict[str, AwgPeerRuntime] = {}
    current: dict[str, object] | None = None

    def flush() -> None:
        nonlocal current
        if not current:
            return

        public_key = str(current.get("public_key", ""))
        if public_key:
            peers[public_key] = AwgPeerRuntime(
                public_key=public_key,
                endpoint=str(current.get("endpoint", "")),
                allowed_ip=str(current.get("allowed_ip", "")),
                rx_bytes=int(current.get("rx_bytes", 0)),
                tx_bytes=int(current.get("tx_bytes", 0)),
                latest_handshake=str(
                    current.get("latest_handshake", "never")
                ),
            )
        current = None

    for raw_line in output.splitlines():
        line = raw_line.strip()
        lower = line.lower()

        if lower.startswith("peer:"):
            flush()
            current = {
                "public_key": re.sub(r"\s+", "", line.split(":", 1)[1]),
                "endpoint": "",
                "allowed_ip": "",
                "rx_bytes": 0,
                "tx_bytes": 0,
                "latest_handshake": "never",
            }
            continue

        if current is None:
            continue

        if lower.startswith("endpoint:"):
            current["endpoint"] = _normalize_endpoint(
                line.split(":", 1)[1]
            )
        elif lower.startswith("allowed ips:"):
            current["allowed_ip"] = (
                line.split(":", 1)[1].strip().split("/", 1)[0]
            )
        elif lower.startswith("latest handshake:"):
            current["latest_handshake"] = line.split(":", 1)[1].strip()
        elif lower.startswith("transfer:"):
            transfer = line.split(":", 1)[1]

            received = re.search(
                r"([0-9]+(?:\.[0-9]+)?)\s*(B|KiB|MiB|GiB)\s*received",
                transfer,
                re.IGNORECASE,
            )
            sent = re.search(
                r"([0-9]+(?:\.[0-9]+)?)\s*(B|KiB|MiB|GiB)\s*sent",
                transfer,
                re.IGNORECASE,
            )

            if received:
                current["rx_bytes"] = _parse_transfer(received.group(0))
            if sent:
                current["tx_bytes"] = _parse_transfer(sent.group(0))

    flush()
    return peers


def discover_awg_units() -> list[str]:
    """Return installed AWG systemd units."""
    return [
        unit
        for unit in list_service_units("awg-quick@*.service")
        if unit.startswith("awg-quick@")
    ]


def get_interface_output(interface: str) -> str | None:
    """Return `awg show <interface>` output."""
    try:
        result = subprocess.run(
            ["awg", "show", interface],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return None

    if result.returncode != 0:
        return None

    return result.stdout


def get_listening_port(interface: str) -> int | None:
    """Return AWG listening UDP port for an interface."""
    output = get_interface_output(interface)

    if output is None:
        return None

    for line in output.splitlines():
        if not line.strip().startswith("listening port:"):
            continue

        value = line.split(":", 1)[1].strip()

        try:
            return int(value)
        except ValueError:
            return None

    return None


def get_runtime_peers() -> dict[str, AwgPeerRuntime]:
    """Return normalized runtime state for all AWG peers."""
    try:
        result = subprocess.run(
            ["awg", "show", "awg0"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        return {}

    return _parse_show_output(result.stdout)


def get_latest_handshakes() -> dict[str, int]:
    """Return latest handshake timestamps keyed by peer public key."""
    try:
        result = subprocess.run(
            ["awg", "show", "awg0", "latest-handshakes"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        return {}

    handshakes: dict[str, int] = {}

    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue

        public_key, timestamp = line.split("\t", 1)

        try:
            handshakes[public_key.strip()] = int(timestamp.strip())
        except ValueError:
            continue

    return handshakes
