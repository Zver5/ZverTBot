"""
Управление systemd сервисами.
"""

import subprocess
import time

from utils.logger import logger


def service_exists(service: str) -> bool:
    """
    Проверяет наличие systemd unit.
    """
    try:
        result = subprocess.run(
            ["systemctl", "cat", service],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_service_state(service: str) -> str:
    """Возвращает текущее состояние systemd unit."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def service_is_active(service: str) -> bool:
    """
    Проверяет, находится ли systemd unit в состоянии active.
    """
    return get_service_state(service) == "active"


def list_service_units() -> list[str]:
    """Возвращает имена всех systemd service units."""
    try:
        result = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all", "--no-legend"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return []

    units = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if fields:
            units.append(fields[0].removesuffix(".service"))
    return units


def get_service_uptime_seconds(service: str) -> int | None:
    """Возвращает время работы active systemd unit в секундах."""
    try:
        result = subprocess.run(
            ["systemctl", "show", service, "-p", "ActiveEnterTimestampMonotonic"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        value = result.stdout.strip().partition("=")[2]
        if not value.isdigit() or int(value) <= 0:
            return None

        uptime = subprocess.run(
            ["cat", "/proc/uptime"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.split()[0]

        now = int(float(uptime))
        return max(0, now - int(value) // 1_000_000)
    except Exception:
        return None


def restart_service_detached(service: str) -> None:
    """
    Запускает рестарт systemd-сервиса без ожидания его завершения.
    Используется для рестарта текущего сервиса/процесса.
    """
    try:
        subprocess.Popen(
            ["systemctl", "restart", service],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info("service.restart.scheduled | service=%s", service)
    except Exception as e:
        logger.error(
            "service.restart.schedule_failed | service=%s | error=%s",
            service,
            e,
        )
        raise


def restart_service(service: str, wait: int = 2) -> None:
    """
    Перезапускает systemd сервис и проверяет состояние.
    """

    try:
        subprocess.run(["systemctl", "restart", service], check=True, timeout=15)

        time.sleep(wait)

        state = get_service_state(service)

        if state != "active":
            raise RuntimeError(f"{service} не активен после рестарта (state={state})")

        logger.info("service.restart.completed | service=%s", service)

    except Exception as e:
        logger.error("service.restart.failed | service=%s | error=%s", service, e)
        raise
