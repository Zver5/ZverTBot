"""
Модуль форматирования текста для Telegram-бота ZverTBot.
Содержит чистые функции генерации текста.
"""


from config import (
    BOT_NAME,
    BOT_VERSION,
    HA_TUNNEL_IP,
    HASS_FLAG,
    SERVER_FLAG,
    SERVER_IP,
)
from services.awg.network import get_default_route_interface


def get_help_text():
    """Возвращает текст главного меню бота."""
    try:
        interface = get_default_route_interface()
    except Exception:
        interface = "не определён"

    return f"""📖 *Управление сервером VPS*

🐺 {BOT_NAME}: v{BOT_VERSION}

🌐 VPS: `{SERVER_IP}` {SERVER_FLAG}
🏠 HASS: `{HA_TUNNEL_IP}` {HASS_FLAG}
🔗 WAN-интерфейс: `{interface}`

Выберите действие👇"""
