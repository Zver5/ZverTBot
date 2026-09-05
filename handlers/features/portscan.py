"""
Обработчик сканирования портов.
"""

from telebot import types

from core.callback_response import CallbackResponse
from core.navigation import NAV_BACK_CALLBACK, navigation
from services.port_scanner import scan_open_ports
from ui.screens import PORT_SCAN
from utils.error_handler import handle_errors
from utils.logger import logger


def render_port_scan(bot, cid, message_id):
    """Отрисовать результат сканирования портов."""
    text = scan_open_ports()
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            "🔄 Сканировать снова",
            callback_data="port_scan",
        ),
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        ),
    )
    try:
        return bot.edit_message_text(
            text,
            cid,
            message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            logger.error("portscan.handler.message_update_failed | error=%s", e)
        return True


@handle_errors("Ошибка в handle_portscan_callback")
def handle_portscan_callback(bot, cid, call, data):
    """Обрабатывает навигацию сканирования портов."""
    if data != "port_scan":
        return False

    screen_id = PORT_SCAN
    if navigation.current(cid) != screen_id:
        navigation.go(cid, screen_id)

    navigation.render(screen_id, bot, cid, call.message.message_id)
    return CallbackResponse("Сканирую порты...")
