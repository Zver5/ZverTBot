"""Определение состояния серверных VPN-конфигураций."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from config.paths import AWG_CONF, XRAY_CONF
from services.awg.config_manager import get_awg_readiness
from services.xray.config_manager import get_xray_readiness, load_xray_config


@dataclass(frozen=True)
class VpnConfigStatus:
    """Состояние одного VPN-протокола."""

    protocol: str
    installed: bool
    working: bool
    problems: tuple[str, ...] = ()


def _xray_installed() -> bool:
    return shutil.which("xray") is not None


def _xray_test() -> tuple[bool, str | None]:
    try:
        result = subprocess.run(
            ["xray", "run", "-test", "-config", str(XRAY_CONF)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)

    if result.returncode == 0:
        return True, None

    return False, result.stderr.strip() or result.stdout.strip() or "Xray test failed"


def get_xray_status() -> VpnConfigStatus:
    if not _xray_installed():
        return VpnConfigStatus("xray", False, False, ("Xray не установлен",))

    if not XRAY_CONF.is_file():
        return VpnConfigStatus("xray", True, False, ("Конфиг Xray не найден",))

    try:
        config = load_xray_config()
        ready, problems = get_xray_readiness(config)
        if not ready:
            return VpnConfigStatus("xray", True, False, tuple(problems))

        tested, error = _xray_test()
        if not tested:
            return VpnConfigStatus(
                "xray",
                True,
                False,
                (error or "Xray не прошёл проверку",),
            )

        return VpnConfigStatus("xray", True, True)
    except Exception as exc:
        return VpnConfigStatus("xray", True, False, (str(exc),))


def _awg_installed() -> bool:
    """Проверяет установку AmneziaWG без требования запущенного интерфейса."""
    if shutil.which("awg") is None:
        return False

    try:
        result = subprocess.run(
            [
                "systemctl",
                "list-unit-files",
                "awg-quick@.service",
                "--no-legend",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

    return "awg-quick@.service" in result.stdout


def get_awg_status() -> VpnConfigStatus:
    if not _awg_installed():
        return VpnConfigStatus(
            "awg",
            False,
            False,
            ("AmneziaWG не установлен",),
        )

    if not AWG_CONF.is_file():
        return VpnConfigStatus(
            "awg",
            True,
            False,
            ("Конфиг AWG не найден",),
        )

    try:
        content = AWG_CONF.read_text(encoding="utf-8")
        ready, problems = get_awg_readiness(content)

        return VpnConfigStatus(
            "awg",
            True,
            ready,
            tuple(problems),
        )
    except Exception as exc:
        return VpnConfigStatus("awg", True, False, (str(exc),))


def get_vpn_config_status() -> dict[str, VpnConfigStatus]:
    """Возвращает состояние Xray и AWG."""
    return {
        "xray": get_xray_status(),
        "awg": get_awg_status(),
    }


def get_missing_config_protocols() -> list[str]:
    """Возвращает установленные протоколы без рабочего конфига."""
    return [
        protocol
        for protocol, status in get_vpn_config_status().items()
        if status.installed and not status.working
    ]


def has_missing_vpn_config() -> bool:
    """Нужно ли показывать кнопку создания конфига."""
    return bool(get_missing_config_protocols())
