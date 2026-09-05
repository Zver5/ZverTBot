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


def service_is_active(service: str) -> bool:
    """
    Проверяет, находится ли systemd unit в состоянии active.
    """
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip() == "active"
    except Exception:
        return False


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

        status = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=5,
        )

        state = status.stdout.strip()

        if status.returncode != 0 or state != "active":
            raise RuntimeError(f"{service} не активен после рестарта (state={state})")

        logger.info("service.restart.completed | service=%s", service)

    except Exception as e:
        logger.error("service.restart.failed | service=%s | error=%s", service, e)
        raise
