"""
Сбор фактов о состоянии сервера для AI-анализа.
"""

import shutil
import subprocess

from services.vps_monitor import _discover_awg_units, check_all
from utils.service_control import get_service_state


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


def collect_monitoring_facts() -> str:
    """Возвращает компактные результаты всех проверок VPS-мониторинга."""
    try:
        results = check_all()
    except Exception:
        return "MONITORING FACT | checks unavailable"

    if not results:
        return "MONITORING FACT | no checks returned"

    facts = []

    for result in results:
        status = "OK" if result.healthy else "FAIL"
        failure = (
            f" | failure={result.failure.value}"
            if result.failure is not None
            else ""
        )
        details = result.details or "no details"
        facts.append(
            "MONITORING FACT | "
            f"{result.name} | category={result.category.value} | "
            f"status={status} | {details}{failure}"
        )

    return "\n".join(facts)


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
    ]:
        status = get_service_state(service)
        parts.append(f"{service}: {status or 'unknown'}")

    awg_units = _discover_awg_units()
    if awg_units:
        for service in awg_units:
            status = get_service_state(service)
            parts.append(f"{service}: {status or 'unknown'}")
    else:
        parts.append("awg: no units detected")

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


def collect_server_health_for_ai() -> str:
    """Добавляет к отчёту сервера подтверждённые результаты мониторинга."""
    return "\n".join(
        [
            collect_server_health(),
            "\n=== MONITORING FACTS ===",
            collect_monitoring_facts(),
        ]
    )
