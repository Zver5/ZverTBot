"""Модуль управления IP-адресами AmneziaWG.
Проверяет занятые IP из двух источников: реестр + running config.
Диапазон: 10.66.66.8-99 (92 адреса).
"""

import subprocess

from data.storage import load_awg_registry
from utils.logger import logger


def get_used_awg_ips() -> set:
    """
    Возвращает множество занятых IP-адресов AWG.

    Проверяет ДВА источника:
    1. Реестр awg_users.json (постоянные назначения)
    2. Текущие подключения через 'awg show awg0' (активные сессии)

    Returns:
        set: Множество занятых IP (например: {'10.66.66.8', '10.66.66.9'})
    """
    # Источник 1: Реестр клиентов
    reg_ips = {v["ip"] for v in load_awg_registry().values() if "ip" in v}

    # Источник 2: Активные подключения
    live_ips = set()
    try:
        out = subprocess.run(
            ["awg", "show", "awg0"], capture_output=True, text=True
        ).stdout
        for line in out.splitlines():
            if "allowed ips:" in line:
                ip = line.split(":")[1].strip().split("/")[0]
                if ip.startswith("10.66.66."):
                    live_ips.add(ip)
    except Exception as e:
        logger.warning(
            "awg.runtime.list_peers_failed | error=%s",
            e,
        )

    # Объединяем оба источника
    return reg_ips | live_ips


def find_free_awg_ip() -> str | None:
    """
    Находит первый свободный IP в диапазоне 10.66.66.8-99.

    Returns:
        str | None: Свободный IP или None если все заняты
    """
    used = get_used_awg_ips()

    # Диапазон 8-99 (92 возможных адреса)
    for i in range(8, 100):
        ip = f"10.66.66.{i}"
        if ip not in used:
            return ip

    return None
