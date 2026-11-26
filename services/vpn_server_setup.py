"""Создание серверных конфигураций VPN."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config.paths import AWG_CONF, XRAY_ACCESS_LOG, XRAY_CONF
from services.awg.config_manager import (
    get_awg_readiness,
    parse_awg_interface,
    save_awg_config,
)
from services.awg.network import (
    build_awg_input_firewall_hooks,
    build_awg_network_hooks,
)
from services.xray import firewall as xray_firewall
from services.xray.config_manager import (
    get_xray_readiness,
    load_xray_config,
    save_xray_config,
    validate_xray_config,
)
from utils.atomic import atomic_write
from utils.client_operation_lock import client_operation_lock
from utils.service_control import (
    get_service_state,
    restart_service,
    run_systemctl,
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
AWG_DEFAULT_PARAMS = {
    "jc": 4,
    "jmin": 40,
    "jmax": 70,
    "s1": 117,
    "s2": 74,
    "s3": 63,
    "s4": 82,
    "h1": 1,
    "h2": 2,
    "h3": 3,
    "h4": 4,
}


def _validate_port(port: int, protocol: str) -> None:
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError(f"Некорректный порт {protocol}: {port!r}")


def _validate_awg_parameters(port: int, **params: int) -> None:
    _validate_port(port, "AWG")
    for name, value in params.items():
        if type(value) is not int or value < 0:
            raise ValueError(f"Некорректный параметр AWG {name}: {value!r}")
    if params["jmin"] > params["jmax"]:
        raise ValueError("AWG Jmin не может быть больше Jmax")


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


def _is_tcp_port_listening(port: int) -> bool:
    """Проверяет, что TCP-порт слушает основной процесс службы Xray."""
    main_pid = _run_command(
        "systemctl", "show", "xray", "--property=MainPID", "--value"
    )
    if not main_pid.isdigit() or int(main_pid) <= 0:
        return False

    output = _run_command("ss", "-lntpH")
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 6 or fields[0] != "LISTEN":
            continue
        if fields[3].rsplit(":", 1)[-1] != str(port):
            continue
        match = re.search(r'users:\(\("xray",pid=(\d+),', line)
        if match and match.group(1) == main_pid:
            return True
    return False


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
    flow: str = "xtls-rprx-vision",
) -> dict:
    """Создаёт минимальную рабочую конфигурацию VLESS Reality."""
    _validate_port(port, "Xray")
    if not isinstance(sni, str) or not sni or any(ch.isspace() for ch in sni):
        raise ValueError("Некорректный SNI")
    if (
        not isinstance(dest, str)
        or not dest
        or any(ch.isspace() for ch in dest)
        or ":" not in dest
    ):
        raise ValueError("Некорректный Reality dest (ожидается host:port)")
    if flow not in ("", "xtls-rprx-vision"):
        raise ValueError("Поддерживается flow=xtls-rprx-vision или flow=none")
    return {
        "api": {
            "tag": "api",
            "services": ["HandlerService", "LoggerService", "StatsService"],
        },
        "log": {
            "access": str(XRAY_ACCESS_LOG),
            "loglevel": "warning",
        },
        "stats": {},
        "policy": {
            "levels": {
                "0": {
                    "statsUserUplink": True,
                    "statsUserDownlink": True,
                }
            }
        },
        "inbounds": [
            {
                "listen": "0.0.0.0",
                "port": port,
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {
                            "id": _generate_uuid(),
                            "flow": flow,
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
            },
            {
                "listen": "127.0.0.1",
                "port": 10085,
                "protocol": "dokodemo-door",
                "settings": {"address": "127.0.0.1"},
                "tag": "api",
            },
        ],
        "outbounds": [
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "block"},
        ],
        "routing": {
            "rules": [
                {
                    "type": "field",
                    "inboundTag": ["api"],
                    "outboundTag": "api",
                }
            ]
        },
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


def _extract_awg_peer_blocks(content: str) -> list[str]:
    """Сохраняет реальные [Peer]-блоки без placeholder-пиров."""
    lines = content.splitlines(keepends=True)
    blocks: list[str] = []
    start: int | None = None

    for index, line in enumerate(lines):
        if line.strip().lower() != "[peer]":
            continue

        block_start = index

        # Сохраняем только комментарий непосредственно перед этим [Peer].
        if index > 0 and lines[index - 1].strip().startswith("#"):
            block_start = index - 1

        if start is not None:
            block = "".join(lines[start:block_start]).strip()
            if block and "REPLACE_WITH_CLIENT_PUBLIC_KEY" not in block:
                blocks.append(block + "\n")

        start = block_start

    if start is not None:
        block = "".join(lines[start:]).strip()
        if block and "REPLACE_WITH_CLIENT_PUBLIC_KEY" not in block:
            blocks.append(block + "\n")

    return blocks


def _build_awg_config(
    *,
    port: int = AWG_DEFAULT_PORT,
    jc: int = 4,
    jmin: int = 40,
    jmax: int = 70,
    s1: int = 117,
    s2: int = 74,
    s3: int = 63,
    s4: int = 82,
    h1: int = 1,
    h2: int = 2,
    h3: int = 3,
    h4: int = 4,
    peer_blocks: list[str] | tuple[str, ...] = (),
    network_hooks=None,
) -> str:
    """Создаёт серверный AWG-конфиг, сохраняя переданные peers."""
    params = {
        "jc": jc,
        "jmin": jmin,
        "jmax": jmax,
        "s1": s1,
        "s2": s2,
        "s3": s3,
        "s4": s4,
        "h1": h1,
        "h2": h2,
        "h3": h3,
        "h4": h4,
    }
    _validate_awg_parameters(port, **params)
    private_key = _generate_awg_private_key()

    lines = [
        "[Interface]",
        f"PrivateKey = {private_key}",
        f"Address = {AWG_DEFAULT_ADDRESS}",
        f"ListenPort = {port}",
        f"Jc = {jc}",
        f"Jmin = {jmin}",
        f"Jmax = {jmax}",
        f"S1 = {s1}",
        f"S2 = {s2}",
        f"S3 = {s3}",
        f"S4 = {s4}",
        f"H1 = {h1}",
        f"H2 = {h2}",
        f"H3 = {h3}",
        f"H4 = {h4}",
    ]

    if network_hooks is not None:
        lines.extend(f"PostUp = {command}" for command in network_hooks.post_up)
        lines.extend(f"PostDown = {command}" for command in network_hooks.post_down)

    input_up, input_down = build_awg_input_firewall_hooks(port)
    lines.extend(f"PostUp = {command}" for command in input_up)
    lines.extend(f"PostDown = {command}" for command in input_down)

    if peer_blocks:
        lines.append("")
        lines.extend(block.rstrip("\n") for block in peer_blocks)

    return "\n".join(lines) + "\n"


def _validate_xray_parameters(port: int, sni: str, dest: str, flow: str) -> None:
    _validate_port(port, "Xray")
    if not isinstance(sni, str) or not sni or any(ch.isspace() for ch in sni):
        raise ValueError("Некорректный SNI")
    if (
        not isinstance(dest, str)
        or not dest
        or any(ch.isspace() for ch in dest)
        or ":" not in dest
    ):
        raise ValueError("Некорректный Reality dest (ожидается host:port)")
    host, raw_port = dest.rsplit(":", 1)
    if not host or not raw_port.isdigit() or not 1 <= int(raw_port) <= 65535:
        raise ValueError("Некорректный порт Reality dest")
    if flow not in ("", "xtls-rprx-vision"):
        raise ValueError("Поддерживается flow=xtls-rprx-vision или flow=none")


def _modify_xray_config(
    current: dict,
    *,
    port: int,
    sni: str,
    dest: str,
    flow: str,
) -> dict:
    """Меняет параметры одного VLESS Reality inbound без смены ключей."""
    import copy

    candidate = copy.deepcopy(current)
    inbounds = candidate.get("inbounds")
    if not isinstance(inbounds, list):
        raise ValueError("Xray config: inbounds должен быть списком")

    vless = [
        item
        for item in inbounds
        if isinstance(item, dict) and item.get("protocol") == "vless"
    ]
    if len(vless) != 1:
        raise ValueError(
            "Безопасная перенастройка поддерживает ровно один VLESS inbound"
        )

    inbound = vless[0]
    stream = inbound.get("streamSettings")
    if not isinstance(stream, dict):
        raise ValueError("У VLESS inbound отсутствует streamSettings")
    if stream.get("network", "tcp") != "tcp" or stream.get("security") != "reality":
        raise ValueError("Поддерживается только VLESS TCP Reality")

    reality = stream.get("realitySettings")
    if not isinstance(reality, dict):
        raise ValueError("Reality settings отсутствуют")

    settings = inbound.get("settings")
    clients = settings.get("clients") if isinstance(settings, dict) else None
    if not isinstance(clients, list):
        raise ValueError("Список VLESS-клиентов повреждён")

    inbound["port"] = port
    reality["dest"] = dest
    reality["serverNames"] = [sni]

    for client in clients:
        if not isinstance(client, dict):
            raise ValueError("Некорректная запись VLESS-клиента")
        if flow:
            client["flow"] = flow
        else:
            client.pop("flow", None)

    return candidate


def _strict_awg_interface_fields(content: str) -> dict[str, str]:
    """Разбирает единственную [Interface], запрещая повторяющиеся ключи."""
    sections = [
        line.strip().lower()
        for line in content.splitlines()
        if line.strip().startswith("[")
    ]
    if sections.count("[interface]") != 1:
        raise ValueError("AWG config должен содержать ровно одну секцию [Interface]")

    fields: dict[str, str] = {}
    in_interface = False

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("["):
            in_interface = line.lower() == "[interface]"
            continue
        if not in_interface or not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip().lower()
        if not key:
            raise ValueError("В AWG [Interface] найден пустой ключ")
        if key in fields and key not in {"postup", "postdown"}:
            raise ValueError(f"Дублирующийся параметр AWG: {key}")
        fields[key] = value.strip()

    return fields


def _modify_awg_config(
    current: str,
    *,
    port: int,
    params: dict,
) -> str:
    """Обновляет только поддерживаемые параметры [Interface]."""
    fields = _strict_awg_interface_fields(current)
    try:
        previous_port = int(fields["listenport"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("В существующем AWG config некорректный ListenPort") from exc

    if not fields.get("privatekey"):
        raise ValueError("В существующем AWG config отсутствует PrivateKey")
    if not fields.get("address"):
        raise ValueError("В существующем AWG config отсутствует Address")
    original_address = fields["address"]

    awg_names = {
        "jc": "Jc",
        "jmin": "Jmin",
        "jmax": "Jmax",
        "s1": "S1",
        "s2": "S2",
        "s3": "S3",
        "s4": "S4",
        "h1": "H1",
        "h2": "H2",
        "h3": "H3",
        "h4": "H4",
    }
    values = {"ListenPort": port}
    values.update({awg_names[key.lower()]: value for key, value in params.items()})

    lines = current.splitlines()
    in_interface = False
    seen = set()
    output = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            if in_interface:
                missing = [
                    f"{key} = {value}"
                    for key, value in values.items()
                    if key.lower() not in seen
                ]
                output.extend(missing)
            in_interface = stripped.lower() == "[interface]"
            output.append(line)
            continue

        if in_interface and "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip().lower()
            matching = next(
                (name for name in values if name.lower() == key),
                None,
            )
            if matching:
                if key in seen:
                    raise ValueError(f"Дублирующийся параметр AWG: {matching}")
                seen.add(key)
                indent = line[: len(line) - len(line.lstrip())]
                output.append(f"{indent}{matching} = {values[matching]}")
                continue

        output.append(line)

    if in_interface:
        output.extend(
            f"{key} = {value}"
            for key, value in values.items()
            if key.lower() not in seen
        )

    candidate = "\n".join(output).rstrip() + "\n"

    # Адрес и подсеть существующего сервера должны остаться прежними.
    new_fields = parse_awg_interface(candidate)
    if new_fields.get("address") != original_address:
        raise ValueError("Перенастройка не должна менять Address AWG")

    input_up, input_down = build_awg_input_firewall_hooks(
        listen_port=port,
        previous_listen_port=previous_port,
    )
    lines = [
        line for line in candidate.splitlines() if "ZverTBot-AWG-INPUT" not in line
    ]

    peer_index = next(
        (index for index, line in enumerate(lines) if line.strip().lower() == "[peer]"),
        len(lines),
    )
    hooks = [f"PostUp = {command}" for command in input_up] + [
        f"PostDown = {command}" for command in input_down
    ]
    if peer_index and lines[peer_index - 1].strip():
        hooks.insert(0, "")
    lines[peer_index:peer_index] = hooks
    candidate = "\n".join(lines).rstrip() + "\n"

    return candidate


def _validate_awg_candidate(content: str) -> None:
    ready, problems = get_awg_readiness(content)
    if not ready:
        raise ValueError("AWG config не прошёл проверку: " + "; ".join(problems))

    AWG_CONF.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="awg0.validate.",
        dir=str(AWG_CONF.parent),
    ) as temp_dir:
        temp_path = Path(temp_dir) / "awg0.conf"
        temp_path.write_text(content, encoding="utf-8")
        _run_command("awg-quick", "strip", str(temp_path), timeout=10)


def _backup_path(path: Path) -> Path:
    """Создаёт backup с уникальным именем."""
    import uuid
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{timestamp}-{uuid.uuid4().hex[:6]}")
    shutil.copy2(path, backup)
    return backup


def _apply_xray_transaction(
    candidate: dict,
    *,
    existed: bool,
    old_port: int | None = None,
) -> str | None:
    """Атомарно применяет Xray config и соответствующие правила firewall."""
    if not validate_xray_config(candidate):
        raise ValueError("Candidate Xray не прошёл xray run -test")

    inbounds = candidate.get("inbounds")
    vless = [
        item
        for item in inbounds or []
        if isinstance(item, dict) and item.get("protocol") == "vless"
    ]
    if len(vless) != 1:
        raise ValueError("Для firewall требуется ровно один VLESS inbound")

    new_port = vless[0].get("port")
    _validate_port(new_port, "VLESS")

    backup = _backup_path(XRAY_CONF) if existed else None
    old_state = get_service_state("xray")

    firewall_transaction = xray_firewall.prepare_xray_port_change(old_port, new_port)

    try:
        save_xray_config(candidate)
        verify_listener = False
        if old_state == "active":
            restart_service("xray")
            verify_listener = True
        elif not existed:
            run_systemctl("start", "xray", timeout=15, check=True)
            if get_service_state("xray") != "active":
                raise RuntimeError("Xray не перешёл в active после запуска")
            verify_listener = True

        if verify_listener and not _is_tcp_port_listening(new_port):
            raise RuntimeError(
                f"Xray не открыл TCP/{new_port} после применения конфигурации"
            )

        firewall_transaction.commit()

    except Exception as original_error:
        rollback_errors = []

        try:
            if backup:
                original_content = backup.read_text(encoding="utf-8")
                atomic_write(XRAY_CONF, original_content)
                if old_state == "active":
                    restart_service("xray")
            else:
                XRAY_CONF.unlink(missing_ok=True)
                run_systemctl("stop", "xray", timeout=15)
        except Exception as exc:
            rollback_errors.append(f"откат Xray: {exc}")

        try:
            firewall_transaction.rollback()
        except Exception as exc:
            rollback_errors.append(f"откат firewall: {exc}")

        if rollback_errors:
            raise RuntimeError(
                f"{original_error}; " + "; ".join(rollback_errors)
            ) from original_error
        raise

    return str(backup) if backup else None


def _apply_awg_transaction(candidate: str, *, existed: bool) -> str | None:
    """Проверяет, сохраняет, перезапускает AWG и откатывает при ошибке."""
    _validate_awg_candidate(candidate)

    backup = _backup_path(AWG_CONF) if existed else None
    old_state = get_service_state("awg-quick@awg0")

    try:
        save_awg_config(candidate)
        if old_state == "active":
            restart_service("awg-quick@awg0")
        elif not existed:
            run_systemctl("start", "awg-quick@awg0", timeout=15, check=True)
            if get_service_state("awg-quick@awg0") != "active":
                raise RuntimeError("AWG не перешёл в active после запуска")
    except Exception as original_error:
        try:
            if backup:
                save_awg_config(backup.read_text(encoding="utf-8"))
                if old_state == "active":
                    restart_service("awg-quick@awg0")
            else:
                AWG_CONF.unlink(missing_ok=True)
                run_systemctl("stop", "awg-quick@awg0", timeout=15)
        except Exception as rollback_error:
            raise RuntimeError(
                f"{original_error}; откат AWG также завершился ошибкой: "
                f"{rollback_error}"
            ) from rollback_error
        raise

    return str(backup) if backup else None


@client_operation_lock
def setup_xray_server(
    *,
    port: int = XRAY_DEFAULT_PORT,
    sni: str = XRAY_DEFAULT_SNI,
    dest: str = XRAY_DEFAULT_DEST,
    flow: str = "xtls-rprx-vision",
    initial_setup_only: bool = False,
) -> SetupResult:
    """Создаёт или перенастраивает Xray с сохранением идентификаторов."""
    try:
        _validate_xray_parameters(port, sni, dest, flow)
        existed = XRAY_CONF.exists() or XRAY_CONF.is_symlink()

        if initial_setup_only and existed:
            return SetupResult(
                "xray",
                False,
                "Первичная настройка отменена: конфигурация уже существует",
            )
        if XRAY_CONF.is_symlink():
            raise ValueError("Перенастройка символьной ссылки запрещена")

        old_port = None
        if existed:
            current = load_xray_config()
            ready, problems = get_xray_readiness(current)
            if not ready:
                raise ValueError(
                    "Существующий Xray config не готов: " + "; ".join(problems)
                )

            current_inbounds = current.get("inbounds")
            current_vless = [
                item
                for item in current_inbounds or []
                if isinstance(item, dict) and item.get("protocol") == "vless"
            ]
            if len(current_vless) != 1:
                raise ValueError(
                    "Безопасная перенастройка поддерживает ровно один VLESS inbound"
                )

            old_port = current_vless[0].get("port")
            _validate_port(old_port, "VLESS")
            candidate = _modify_xray_config(
                current, port=port, sni=sni, dest=dest, flow=flow
            )
        else:
            candidate = _build_xray_config(port=port, sni=sni, dest=dest, flow=flow)

        backup = _apply_xray_transaction(candidate, existed=existed, old_port=old_port)
        action = "перенастроен" if existed else "создан"
        message = f"Xray config {action}: {XRAY_CONF}"
        if backup:
            message += f"\nBackup: {backup}"
        return SetupResult("xray", True, message)

    except Exception as exc:
        return SetupResult("xray", False, f"Не удалось применить Xray config: {exc}")


@client_operation_lock
def setup_awg_server(
    *,
    port: int = AWG_DEFAULT_PORT,
    jc: int = 4,
    jmin: int = 40,
    jmax: int = 70,
    s1: int = 117,
    s2: int = 74,
    s3: int = 63,
    s4: int = 82,
    h1: int = 1,
    h2: int = 2,
    h3: int = 3,
    h4: int = 4,
    initial_setup_only: bool = False,
) -> SetupResult:
    """Создаёт или перенастраивает AWG без смены ключей и peers."""
    try:
        params = {
            "jc": jc,
            "jmin": jmin,
            "jmax": jmax,
            "s1": s1,
            "s2": s2,
            "s3": s3,
            "s4": s4,
            "h1": h1,
            "h2": h2,
            "h3": h3,
            "h4": h4,
        }
        _validate_awg_parameters(port, **params)

        existed = AWG_CONF.exists() or AWG_CONF.is_symlink()
        if initial_setup_only and existed:
            return SetupResult(
                "awg",
                False,
                "Первичная настройка отменена: конфигурация уже существует",
            )
        if AWG_CONF.is_symlink():
            raise ValueError("Перенастройка символьной ссылки запрещена")

        if existed:
            current = AWG_CONF.read_text(encoding="utf-8")
            ready, problems = get_awg_readiness(current)
            if not ready:
                raise ValueError(
                    "Существующий AWG config не готов: " + "; ".join(problems)
                )
            candidate = _modify_awg_config(current, port=port, params=params)
        else:
            network_hooks = build_awg_network_hooks(
                address=AWG_DEFAULT_ADDRESS,
            )
            candidate = _build_awg_config(
                port=port,
                **params,
                network_hooks=network_hooks,
            )

        backup = _apply_awg_transaction(candidate, existed=existed)
        action = "перенастроен" if existed else "создан"
        message = f"AWG config {action}: {AWG_CONF}"
        if backup:
            message += f"\nBackup: {backup}"
        return SetupResult("awg", True, message)

    except Exception as exc:
        return SetupResult("awg", False, f"Не удалось применить AWG config: {exc}")
