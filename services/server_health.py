"""
Сбор фактов о состоянии сервера для AI-анализа.
"""

import shutil
import subprocess


def _run(cmd: list[str], timeout: int = 5) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def collect_server_health() -> str:
    parts = []

    parts.append("=== SYSTEM ===")

    uptime = _run(["uptime", "-p"])
    if uptime:
        parts.append(f"Uptime: {uptime}")

    load = _run(["cat", "/proc/loadavg"])
    if load:
        parts.append(f"Load: {' '.join(load.split()[:3])}")

    memory = _run(["free", "-h"])
    if memory:
        parts.append(f"RAM:\n{memory}")

    disk = _run(["df", "-h", "/"])
    if disk:
        parts.append(f"Disk:\n{disk}")

    parts.append("\n=== SERVICES ===")

    for service in [
        "xray",
        "zvertbot",
        "fail2ban",
        "stats-http",
        "awg-quick@awg0",
    ]:
        status = _run(["systemctl", "is-active", service])

        parts.append(f"{service}: {status or 'unknown'}")

    parts.append("\n=== SECURITY EVENTS ===")

    security = _run(
        [
            "journalctl",
            "-u",
            "ssh",
            "-n",
            "30",
            "--no-pager",
        ]
    )

    parts.append(security if security else "No SSH events")

    parts.append("\n=== SYSTEM ERRORS ===")

    errors = _run(
        [
            "journalctl",
            "-p",
            "err",
            "-n",
            "30",
            "--no-pager",
        ]
    )

    parts.append(errors if errors else "No system errors")

    parts.append("\n=== FIREWALL ===")

    if shutil.which("iptables"):
        firewall = _run(
            [
                "iptables",
                "-L",
                "-n",
                "--line-numbers",
            ]
        )

        parts.append(
            f"Rules lines: {len(firewall.splitlines())}" if firewall else "No data"
        )
    else:
        parts.append("iptables not installed")

    return "\n".join(parts)
