"""Модуль форматирования текста для Telegram-бота ZverTBot."""

import json
from pathlib import Path

from config import (
    BOT_NAME,
    BOT_VERSION,
    HA_TUNNEL_IP,
    HASS_FLAG,
    SERVER_FLAG,
    SERVER_IP,
)
from services.awg.network import get_default_route_interface

CHEBURCHECK_STATE_FILE = Path("data/cheburcheck_state.json")


def _get_cheburcheck_status():
    """Показывает предупреждение при проблемах с API или блокировке IP."""
    try:
        state = json.loads(CHEBURCHECK_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ""

    if not isinstance(state, dict) or state.get("target") != SERVER_IP:
        return ""

    if state.get("api_status") != "unavailable" and state.get("blocked") is not True:
        return ""

    return (
        "⚠️ Возможно, IP заблокирован\n🔎 [ТСПУ: Проверить IP](https://cheburcheck.ru/)"
    )


def get_help_text():
    """Возвращает текст главного меню бота."""
    try:
        interface = get_default_route_interface()
    except Exception:
        interface = "не определён"

    lines = [
        "📖 *Управление сервером VPS*",
        f"🐺 {BOT_NAME}: v{BOT_VERSION}",
        "",
        f"🌐 VPS: `{SERVER_IP}` {SERVER_FLAG}",
        f"🏠 HASS: `{HA_TUNNEL_IP}` {HASS_FLAG}",
        f"🔗 WAN-интерфейс: `{interface}`",
    ]

    cheburcheck_status = _get_cheburcheck_status()
    if cheburcheck_status:
        lines.extend(["", cheburcheck_status])

    lines.extend(["", "Выберите действие👇"])
    return "\n".join(lines)
