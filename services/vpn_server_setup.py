"""Создание серверных конфигураций VPN."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config.paths import AWG_CONF, XRAY_CONF
from services.awg.config_manager import get_awg_readiness
from services.xray.config_manager import (
    get_xray_readiness,
    load_xray_config,
    save_xray_config,
)


@dataclass(frozen=True)
class SetupResult:
    """Результат создания серверной конфигурации."""

    protocol: str
    created: bool
    message: str


XRAY_DEFAULT_PORT = 2096
XRAY_DEFAULT_SNI = "speed.cloudflare.com"
XRAY_DEFAULT_DEST = "speed.cloudflare.com:443"

AWG_DEFAULT_PORT = 58352
AWG_DEFAULT_ADDRESS = "10.66.66.1/24"


def _run_command(*args: str, timeout: int = 10, input_text: str | None = None) -> str:
    """Запускает системную команду и возвращает stdout."""
    result = subprocess.run(
        list(args),
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or "неизвестная ошибка"
        raise RuntimeError(f"{args[0]} {' '.join(args[1:])}: {error}")

    return result.stdout.strip()


def _run_xray(*args: str) -> str:
    """Запускает Xray CLI."""
    return _run_command("xray", *args)


def _generate_uuid() -> str:
    """Генерирует UUID средствами Xray."""
    value = _run_xray("uuid").strip()
    if not value:
        raise RuntimeError("Xray не вернул UUID")
    return value


def _generate_reality_private_key() -> str:
    """Генерирует Reality private key средствами Xray."""
    output = _run_xray("x25519")

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("PrivateKey:"):
            value = line.split(":", 1)[1].strip()
            if value:
                return value

    raise RuntimeError("Xray не вернул Reality private key")


def _generate_short_id() -> str:
    """Генерирует Reality shortId."""
    return os.urandom(8).hex()


def _build_xray_config(
    *,
    port: int = XRAY_DEFAULT_PORT,
    sni: str = XRAY_DEFAULT_SNI,
    dest: str = XRAY_DEFAULT_DEST,
) -> dict:
    """Создаёт минимальную рабочую конфигурацию VLESS Reality."""
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "listen": "0.0.0.0",
                "port": port,
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {
                            "id": _generate_uuid(),
                            "flow": "xtls-rprx-vision",
                            "email": "default",
                            "level": 0,
                        }
                    ],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "dest": dest,
                        "serverNames": [sni],
                        "privateKey": _generate_reality_private_key(),
                        "shortIds": [_generate_short_id()],
                    },
                },
            }
        ],
        "outbounds": [
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "block"},
        ],
    }


def _backup_path(path: Path) -> Path:
    """Создаёт backup существующего конфига."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{timestamp}")
    shutil.copy2(path, backup)
    return backup


def _save_awg_candidate(content: str) -> None:
    """Проверяет и атомарно сохраняет AWG candidate."""
    ready, problems = get_awg_readiness(content)
    if not ready:
        raise ValueError("AWG config не прошёл проверку: " + "; ".join(problems))

    from services.awg.config_manager import save_awg_config

    save_awg_config(content)


def _generate_awg_private_key() -> str:
    """Генерирует приватный ключ AmneziaWG."""
    value = _run_command("awg", "genkey").strip()
    if not value:
        raise RuntimeError("AWG не вернул private key")
    return value


def _build_awg_config(*, port: int = AWG_DEFAULT_PORT) -> str:
    """Создаёт минимальный серверный AWG-конфиг."""
    private_key = _generate_awg_private_key()

    return (
        "[Interface]\n"
        f"PrivateKey = {private_key}\n"
        f"Address = {AWG_DEFAULT_ADDRESS}\n"
        f"ListenPort = {port}\n"
        "Jc = 4\n"
        "Jmin = 40\n"
        "Jmax = 70\n"
        "S1 = 117\n"
        "S2 = 74\n"
        "S3 = 63\n"
        "S4 = 82\n"
        "H1 = 1\n"
        "H2 = 2\n"
        "H3 = 3\n"
        "H4 = 4\n"
    )


def setup_xray_server(
    *,
    port: int = XRAY_DEFAULT_PORT,
    sni: str = XRAY_DEFAULT_SNI,
    dest: str = XRAY_DEFAULT_DEST,
) -> SetupResult:
    """Создаёт Xray-конфиг только если текущий конфиг нерабочий."""
    try:
        if XRAY_CONF.exists():
            try:
                current = load_xray_config()
                ready, _ = get_xray_readiness(current)

                from services.xray.config_manager import validate_xray_config

                if ready and validate_xray_config(current):
                    return SetupResult(
                        "xray",
                        False,
                        f"Рабочий Xray config уже существует: {XRAY_CONF}",
                    )
            except Exception:
                pass

            backup = _backup_path(XRAY_CONF)
        else:
            backup = None

        config = _build_xray_config(port=port, sni=sni, dest=dest)
        save_xray_config(config)

        # Installer создаёт новый Xray config с 0644. Для нового файла
        # сохраняем ту же модель доступа, чтобы Xray мог читать config
        # независимо от пользователя systemd-службы. Для существующего
        # файла atomic_write() сохраняет его исходные owner/group/mode.
        if backup is None:
            XRAY_CONF.chmod(0o644)

        message = f"Xray config создан: {XRAY_CONF}"
        if backup:
            message += f"\nBackup старого конфига: {backup}"

        return SetupResult("xray", True, message)

    except Exception as exc:
        return SetupResult(
            "xray",
            False,
            f"Не удалось создать Xray config: {exc}",
        )


def setup_awg_server(
    *,
    port: int = AWG_DEFAULT_PORT,
) -> SetupResult:
    """Создаёт AWG-конфиг только если текущий конфиг нерабочий."""
    try:
        if AWG_CONF.exists():
            current = AWG_CONF.read_text(encoding="utf-8")
            ready, _ = get_awg_readiness(current)

            if ready:
                return SetupResult(
                    "awg",
                    False,
                    f"Рабочий AWG config уже существует: {AWG_CONF}",
                )

            backup = _backup_path(AWG_CONF)
        else:
            backup = None

        config = _build_awg_config(port=port)
        _save_awg_candidate(config)

        message = f"AWG config создан: {AWG_CONF}"
        if backup:
            message += f"\nBackup старого конфига: {backup}"

        return SetupResult("awg", True, message)

    except Exception as exc:
        return SetupResult(
            "awg",
            False,
            f"Не удалось создать AWG config: {exc}",
        )
