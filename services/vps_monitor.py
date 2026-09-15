"""VPS monitoring checks.

Monitoring classification:
CRITICAL: zvertbot, stats-http
OPTIONAL: backup, xray, awg, ssh, fail2ban
DATA COLLECTORS: xray-traffic-collect, geoip-collect
"""

import json
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from urllib.error import URLError
from urllib.request import urlopen

from config.paths import RCLONE_STATUS_JSON
from services.xray.config_manager import load_xray_config


class MonitorCategory(StrEnum):
    CRITICAL = "critical"
    OPTIONAL = "optional"
    DATA_COLLECTOR = "data_collector"


class MonitorState(StrEnum):
    UP = "up"
    DOWN = "down"


class MonitorFailure(StrEnum):
    SYSTEMD_INACTIVE = "systemd_inactive"
    SYSTEMD_FAILED = "systemd_failed"
    NOT_INSTALLED = "not_installed"
    HTTP_FAILED = "http_failed"
    TCP_FAILED = "tcp_failed"
    UDP_FAILED = "udp_failed"
    CLIENT_FAILED = "client_failed"
    BACKUP_FAILED = "backup_failed"
    BACKUP_STALE = "backup_stale"
    BACKUP_TIMESTAMP = "backup_timestamp"
    CONFIG_FAILED = "config_failed"


@dataclass(frozen=True)
class MonitorResult:
    name: str
    category: MonitorCategory
    healthy: bool
    details: str = ""
    failure: MonitorFailure | None = None


@dataclass(frozen=True)
class StateTransition:
    previous: MonitorState
    current: MonitorState
    notify: bool


CRITICAL_COMPONENTS = frozenset({"zvertbot", "stats-http"})

OPTIONAL_COMPONENTS = frozenset({"backup", "xray", "awg", "ssh", "fail2ban"})

DATA_COLLECTORS = frozenset({"xray-traffic-collect", "geoip-collect"})


def transition_state(
    previous: MonitorState,
    healthy: bool,
) -> StateTransition:
    current = MonitorState.UP if healthy else MonitorState.DOWN
    return StateTransition(
        previous=previous,
        current=current,
        notify=current != previous,
    )


def component_category(name: str) -> MonitorCategory:
    if name in CRITICAL_COMPONENTS:
        return MonitorCategory.CRITICAL
    if name in OPTIONAL_COMPONENTS:
        return MonitorCategory.OPTIONAL
    if name in DATA_COLLECTORS:
        return MonitorCategory.DATA_COLLECTOR
    raise ValueError(f"Unknown monitoring component: {name}")


def _systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", *args],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )


def _tcp_check(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_check(
    url: str,
    timeout: float = 3.0,
) -> tuple[bool, str]:
    try:
        with urlopen(url, timeout=timeout) as response:
            status = response.status
            if 200 <= status < 400:
                return True, f"HTTP {status}"
            return False, f"HTTP {status}"
    except (OSError, URLError) as exc:
        return False, str(exc)


def check_long_running_service(
    name: str,
    category: MonitorCategory,
) -> MonitorResult:
    """Check a normal long-running systemd service."""
    unit = f"{name}.service"

    exists = _systemctl("list-unit-files", unit)
    if unit not in exists.stdout:
        return MonitorResult(
            name=name,
            category=category,
            healthy=category == MonitorCategory.OPTIONAL,
            details="service not installed",
            failure=(
                None
                if category == MonitorCategory.OPTIONAL
                else MonitorFailure.NOT_INSTALLED
            ),
        )

    active = _systemctl("is-active", name)
    state = active.stdout.strip()

    if state == "active":
        return MonitorResult(
            name=name,
            category=category,
            healthy=True,
            details="active",
        )

    failure = (
        MonitorFailure.SYSTEMD_FAILED
        if state == "failed"
        else MonitorFailure.SYSTEMD_INACTIVE
    )

    return MonitorResult(
        name=name,
        category=category,
        healthy=False,
        details=f"systemd state: {state or 'unknown'}",
        failure=failure,
    )


def check_stats_http() -> MonitorResult:
    """Check stats-http service and its local HTTP endpoint."""
    service = check_long_running_service(
        "stats-http",
        MonitorCategory.CRITICAL,
    )

    if not service.healthy:
        return service

    healthy, details = _http_check("http://127.0.0.1:8080/vps-status.json")

    return MonitorResult(
        name="stats-http",
        category=MonitorCategory.CRITICAL,
        healthy=healthy,
        details=details,
        failure=None if healthy else MonitorFailure.HTTP_FAILED,
    )


def _xray_listen_port() -> int | None:
    """Return the first VLESS inbound port configured for Xray."""
    try:
        config = load_xray_config()
    except Exception:
        return None

    for inbound in config.get("inbounds", []):
        if not isinstance(inbound, dict) or inbound.get("protocol") != "vless":
            continue
        try:
            return int(inbound["port"])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def check_xray() -> MonitorResult:
    """Check Xray service and its configured VLESS TCP endpoint."""
    service = check_long_running_service(
        "xray",
        MonitorCategory.OPTIONAL,
    )

    if not service.healthy:
        return service

    port = _xray_listen_port()
    if port is None:
        return MonitorResult(
            name="xray",
            category=MonitorCategory.OPTIONAL,
            healthy=False,
            details="active; VLESS listen port unavailable",
            failure=MonitorFailure.CONFIG_FAILED,
        )

    if _tcp_check("127.0.0.1", port):
        return MonitorResult(
            name="xray",
            category=MonitorCategory.OPTIONAL,
            healthy=True,
            details=f"active; TCP {port} reachable",
        )

    return MonitorResult(
        name="xray",
        category=MonitorCategory.OPTIONAL,
        healthy=False,
        details=f"active; TCP {port} unreachable",
        failure=MonitorFailure.TCP_FAILED,
    )


def _discover_awg_units() -> list[str]:
    """Find all installed awg-quick instances without assuming awg0."""
    result = _systemctl("list-units", "--all", "awg-quick@*.service")
    units = []

    for line in result.stdout.splitlines():
        unit = line.split()[0] if line.split() else ""
        if (
            unit.startswith("awg-quick@")
            and unit != "awg-quick@.service"
            and unit.endswith(".service")
        ):
            units.append(unit.removesuffix(".service"))

    return units


def check_awg_service(
    unit_name: str | None = None,
) -> MonitorResult:
    """Check all AWG systemd units, interfaces and listening ports."""
    units = [unit_name] if unit_name else _discover_awg_units()

    if not units:
        return MonitorResult(
            name="awg",
            category=MonitorCategory.OPTIONAL,
            healthy=True,
            details="AWG service not installed",
        )

    results = []

    for unit in units:
        active = _systemctl("is-active", unit)
        state = active.stdout.strip() or "unknown"

        if state != "active":
            failure = (
                MonitorFailure.SYSTEMD_FAILED
                if state == "failed"
                else MonitorFailure.SYSTEMD_INACTIVE
            )
            results.append(
                MonitorResult(
                    name="awg",
                    category=MonitorCategory.OPTIONAL,
                    healthy=False,
                    details=f"{unit}: {state}",
                    failure=failure,
                )
            )
            continue

        show = subprocess.run(
            ["awg", "show", unit.split("@", 1)[1]],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        if show.returncode != 0:
            results.append(
                MonitorResult(
                    name="awg",
                    category=MonitorCategory.OPTIONAL,
                    healthy=False,
                    details=f"{unit} interface unavailable",
                    failure=MonitorFailure.UDP_FAILED,
                )
            )
            continue

        port = None
        for line in show.stdout.splitlines():
            if line.strip().startswith("listening port:"):
                port = line.split(":", 1)[1].strip()
                break

        if not port:
            results.append(
                MonitorResult(
                    name="awg",
                    category=MonitorCategory.OPTIONAL,
                    healthy=False,
                    details=f"{unit} listening port unavailable",
                    failure=MonitorFailure.UDP_FAILED,
                )
            )
            continue

        results.append(
            MonitorResult(
                name="awg",
                category=MonitorCategory.OPTIONAL,
                healthy=True,
                details=f"{unit} active; UDP {port}",
            )
        )

    failures = [result for result in results if not result.healthy]
    if failures:
        return MonitorResult(
            name="awg",
            category=MonitorCategory.OPTIONAL,
            healthy=False,
            details="; ".join(result.details for result in results),
            failure=failures[0].failure,
        )

    return MonitorResult(
        name="awg",
        category=MonitorCategory.OPTIONAL,
        healthy=True,
        details="; ".join(result.details for result in results),
    )


def _parse_timestamp(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def check_backup(
    max_age_seconds: int = 9 * 60 * 60,
) -> MonitorResult:
    """Check the persisted result and freshness of the last backup."""
    try:
        with open(RCLONE_STATUS_JSON, encoding="utf-8") as file:
            status = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        return MonitorResult(
            name="backup",
            category=MonitorCategory.OPTIONAL,
            healthy=False,
            details=f"backup status unavailable: {exc}",
            failure=MonitorFailure.BACKUP_FAILED,
        )

    if status.get("status") != "success":
        return MonitorResult(
            name="backup",
            category=MonitorCategory.OPTIONAL,
            healthy=False,
            details=f"last backup status: {status.get('status', 'unknown')}",
            failure=MonitorFailure.BACKUP_FAILED,
        )

    completed_at = _parse_timestamp(str(status.get("last_backup", "")))
    if completed_at is None:
        return MonitorResult(
            name="backup",
            category=MonitorCategory.OPTIONAL,
            healthy=False,
            details="last backup timestamp unavailable",
            failure=MonitorFailure.BACKUP_TIMESTAMP,
        )

    age = (
        datetime.now(timezone.utc) - completed_at.astimezone(timezone.utc)
    ).total_seconds()

    if age < 0:
        return MonitorResult(
            name="backup",
            category=MonitorCategory.OPTIONAL,
            healthy=False,
            details="last backup timestamp is in the future",
            failure=MonitorFailure.BACKUP_TIMESTAMP,
        )

    if age > max_age_seconds:
        return MonitorResult(
            name="backup",
            category=MonitorCategory.OPTIONAL,
            healthy=False,
            details=f"last backup is {int(age)} seconds old",
            failure=MonitorFailure.BACKUP_STALE,
        )

    return MonitorResult(
        name="backup",
        category=MonitorCategory.OPTIONAL,
        healthy=True,
        details=f"last backup {int(age)} seconds ago",
    )


def check_ssh() -> MonitorResult:
    """Check SSH service and local TCP port 22."""
    service = check_long_running_service(
        "ssh",
        MonitorCategory.OPTIONAL,
    )

    if not service.healthy:
        return service

    if _tcp_check("127.0.0.1", 22):
        return MonitorResult(
            name="ssh",
            category=MonitorCategory.OPTIONAL,
            healthy=True,
            details="active; TCP 22 reachable",
        )

    return MonitorResult(
        name="ssh",
        category=MonitorCategory.OPTIONAL,
        healthy=False,
        details="active; TCP 22 unreachable",
        failure=MonitorFailure.TCP_FAILED,
    )


def check_fail2ban() -> MonitorResult:
    """Check fail2ban service and fail2ban-client availability."""
    service = check_long_running_service(
        "fail2ban",
        MonitorCategory.OPTIONAL,
    )

    if not service.healthy:
        return service

    result = subprocess.run(
        ["fail2ban-client", "status"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    if result.returncode == 0:
        return MonitorResult(
            name="fail2ban",
            category=MonitorCategory.OPTIONAL,
            healthy=True,
            details="active; fail2ban-client OK",
        )

    return MonitorResult(
        name="fail2ban",
        category=MonitorCategory.OPTIONAL,
        healthy=False,
        details="active; fail2ban-client failed",
        failure=MonitorFailure.CLIENT_FAILED,
    )


def check_all() -> list[MonitorResult]:
    """Run all currently defined VPS monitoring checks."""
    return [
        check_long_running_service(
            "zvertbot",
            MonitorCategory.CRITICAL,
        ),
        check_stats_http(),
        check_backup(),
        check_xray(),
        check_awg_service(),
        check_ssh(),
        check_fail2ban(),
    ]
