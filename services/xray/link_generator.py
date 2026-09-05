"""Модуль генерации VLESS ссылок для клиентов Xray.

Формирует ссылки для всех inbound'ов, где клиент реально присутствует.
Параметры Reality берутся непосредственно из текущего Xray-конфига.
"""

import re
import subprocess
from urllib.parse import quote

from config import SERVER_IP
from services.xray.config_manager import get_vless_inbounds, load_xray_config
from utils.logger import logger


def _get_reality_public_key(private_key: str) -> str:
    """Получает PublicKey Reality из privateKey через Xray."""
    result = subprocess.run(
        ["xray", "x25519", "-i", private_key],
        capture_output=True,
        text=True,
        check=True,
    )

    match = re.search(
        r"Password \(PublicKey\):\s*(\S+)",
        result.stdout,
    )
    if not match:
        raise RuntimeError("Xray не вернул PublicKey для Reality")

    return match.group(1)


def _get_reality_settings(inbound: dict) -> tuple[str, str, str]:
    """Возвращает SNI, public key и short ID из inbound."""
    reality = inbound.get("streamSettings", {}).get("realitySettings", {})

    server_names = reality.get("serverNames") or []
    sni = server_names[0] if server_names else ""

    private_key = reality.get("privateKey", "")
    if not private_key:
        raise RuntimeError("В Reality inbound отсутствует privateKey")

    short_ids = reality.get("shortIds") or []
    short_id = short_ids[0] if short_ids else ""

    if not short_id:
        raise RuntimeError("В Reality inbound отсутствует shortIds")

    public_key = _get_reality_public_key(private_key)

    return sni, public_key, short_id


def _build_vless_link(
    uuid: str,
    port: int,
    sni: str,
    public_key: str,
    short_id: str,
    username: str,
) -> str:
    """Строит VLESS Reality ссылку."""

    params = (
        "encryption=none"
        "&security=reality"
        "&type=tcp"
        "&flow=xtls-rprx-vision"
        f"&sni={quote(sni)}"
        "&fp=chrome"
        f"&pbk={quote(public_key)}"
        f"&sid={quote(short_id)}"
    )

    return f"vless://{uuid}@{SERVER_IP}:{port}?{params}#{quote(username)}"


def xray_get_sni_by_port() -> dict[int, str]:
    """Возвращает SNI Reality для каждого VLESS inbound-порта."""
    try:
        config = load_xray_config()
        sni_by_port = {}

        for inbound in get_vless_inbounds(config):
            port = inbound.get("port")
            reality = inbound.get("streamSettings", {}).get("realitySettings", {})
            server_names = reality.get("serverNames") or []

            if port and server_names:
                sni_by_port[port] = server_names[0]

        return sni_by_port

    except Exception as e:
        logger.error(
            "xray.link.sni_failed | error=%s",
            e,
        )
        return {}


def xray_get_link(username: str) -> str:
    """Возвращает VLESS ссылки для клиента."""

    try:
        config = load_xray_config()
        links = []

        for inbound in get_vless_inbounds(config):
            port = inbound.get("port")

            clients = inbound.get("settings", {}).get("clients")
            if not clients:
                continue

            client = next(
                (c for c in clients if c.get("email") == username),
                None,
            )
            if not client:
                continue

            sni, public_key, short_id = _get_reality_settings(inbound)

            if port and sni:
                links.append(
                    _build_vless_link(
                        client["id"],
                        port,
                        sni,
                        public_key,
                        short_id,
                        username,
                    )
                )

        if not links:
            return ""

        return "\n".join(links)

    except Exception as e:
        logger.error(
            "xray.link.generate_failed | username=%s | error=%s",
            username,
            e,
        )
        return ""


def xray_get_ports(username: str) -> list[int]:
    """Возвращает порты VLESS inbound, где присутствует клиент."""

    try:
        config = load_xray_config()
        ports = []

        for inbound in get_vless_inbounds(config):
            port = inbound.get("port")
            if not port:
                continue

            clients = inbound.get("settings", {}).get("clients")
            if not clients:
                continue

            if any(client.get("email") == username for client in clients):
                ports.append(port)

        return ports

    except Exception as e:
        logger.error(
            "xray.link.ports_failed | username=%s | error=%s",
            username,
            e,
        )
        return []


def xray_get_link_for_port(username: str, port: int) -> str:
    """Возвращает VLESS ссылку для клиента на конкретном порту."""

    try:
        config = load_xray_config()

        for inbound in get_vless_inbounds(config):
            if inbound.get("port") != port:
                continue

            clients = inbound.get("settings", {}).get("clients")
            if not clients:
                continue

            client = next(
                (c for c in clients if c.get("email") == username),
                None,
            )
            if not client:
                continue

            sni, public_key, short_id = _get_reality_settings(inbound)

            if not sni:
                continue

            return _build_vless_link(
                client["id"],
                port,
                sni,
                public_key,
                short_id,
                username,
            )

        return ""

    except Exception as e:
        logger.error(
            "xray.link.port_generate_failed | username=%s | port=%s | error=%s",
            username,
            port,
            e,
        )
        return ""
