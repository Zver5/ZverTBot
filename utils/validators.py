"""
Модуль валидации данных для ZverTBot.
Содержит функции проверки имён клиентов, IP-адресов, PID, chat_id
и проверки уникальности имён (case-insensitive).
"""

import ipaddress
import json
import os
import re

from config.paths import AWG_USERS_JSON, XRAY_CONF


def validate_username(username: str) -> bool:
    """Проверяет валидность имени клиента VPN."""
    if not username:
        return False
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", username))


def validate_ip(ip: str) -> bool:
    """Проверяет валидность IPv4-адреса (строгая проверка 0-255)."""
    if not ip:
        return False
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def validate_pid(pid) -> bool:
    """Проверяет валидность PID процесса."""
    return str(pid).isdigit()


def validate_chat_id(chat_id) -> bool:
    """Проверяет валидность Telegram chat_id."""
    return str(chat_id).isdigit()


def is_username_unique_vless(username: str, config_path: str = XRAY_CONF) -> bool:
    """Проверяет уникальность имени клиента VLESS (case-insensitive)."""
    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        for inbound in config.get("inbounds", []):
            if (
                inbound.get("protocol") == "vless"
                and "clients" in inbound.get("settings", {})
                and any(
                    c["email"].lower() == username.lower()
                    for c in inbound["settings"]["clients"]
                )
            ):
                return False
        return True
    except Exception:
        return False


def is_username_unique_awg(username: str, registry_path: str = AWG_USERS_JSON) -> bool:
    """Проверяет уникальность имени клиента AWG (case-insensitive)."""
    try:
        if not os.path.exists(registry_path):
            return True
        with open(registry_path, encoding="utf-8") as f:
            registry = json.load(f)
        return not any(k.lower() == username.lower() for k in registry)
    except Exception:
        return False
