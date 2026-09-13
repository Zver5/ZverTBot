"""Helpers for reading client connection data from the Xray access log."""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path

_CLIENT_LOG_PATTERN = re.compile(
    r"from\s+(\[[0-9a-fA-F:]+\]|[0-9.]+):\d+.*?email:\s+(\S+)"
)


def get_last_client_ips(log_path: str | Path, max_lines: int) -> dict[str, str]:
    """Return the last known client IP for each Xray email."""
    path = Path(log_path)

    if not path.exists():
        return {}

    with open(path, errors="ignore") as file:
        lines = file.readlines()[-max_lines:]

    clients: dict[str, str] = {}

    for line in lines:
        match = _CLIENT_LOG_PATTERN.search(line)
        if not match:
            continue

        raw_ip, email = match.groups()
        ip = raw_ip.strip("[]")

        try:
            normalized_ip = str(ipaddress.ip_address(ip))
        except ValueError:
            continue

        clients[email] = normalized_ip

    return clients
