"""
Обработчики подменю Fail2ban.
"""

from functools import partial

from telebot import types

from core.access import is_admin
from core.callback_response import CallbackResponse
from core.navigation import (
    FAIL2BAN_LOGS_CALLBACK,
    FAIL2BAN_MENU_CALLBACK,
    FAIL2BAN_UNBAN_CALLBACK,
    NAV_BACK_CALLBACK,
    navigation,
)
from services.fail2ban import get_fail2ban_logs, get_fail2ban_status, unban_ip
from ui.keyboards import fail2ban_menu_kb
from ui.screens import FAIL2BAN_LOGS, FAIL2BAN_MENU, FAIL2BAN_UNBAN_INPUT
from utils.error_handler import handle_errors
from utils.logger import logger
from utils.notifications import log_action
from utils.validators import validate_ip

# Canonical screen IDs.
# Telegram callbacks.


@handle_errors("Ошибка в handle_fail2ban_callback")
def render_fail2ban_menu(bot, cid, message_id):
    """Отрисовать главное меню Fail2ban."""
    text = get_fail2ban_status()
    return bot.edit_message_text(
        text,
        cid,
        message_id,
        parse_mode="Markdown",
        reply_markup=fail2ban_menu_kb(),
    )


# Экраны Fail2Ban принадлежат этому feature-модулю.


@handle_errors("Ошибка в render_fail2ban_unban_input")
def render_fail2ban_unban_input(bot, cid, message_id):
    """Отрисовать экран ввода IP для разбана."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        )
    )
    return bot.edit_message_text(
        "🔓 *Введите IP для разбана:*\nПример: `192.168.1.100`",
        cid,
        message_id,
        parse_mode="Markdown",
        reply_markup=kb,
    )


@handle_errors("Ошибка в handle_fail2ban_callback")
def render_fail2ban_logs(bot, cid, message_id):
    """Отрисовать экран логов Fail2ban."""
    text = get_fail2ban_logs(limit=10)
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        )
    )
    return bot.edit_message_text(
        text,
        cid,
        message_id,
        parse_mode="Markdown",
        reply_markup=kb,
    )


def handle_fail2ban_callback(bot, cid, call, data):
    """Обрабатывает подменю Fail2ban: status, logs, unban"""
    try:
        screen_callbacks = {
            FAIL2BAN_MENU_CALLBACK: (
                FAIL2BAN_MENU,
                None,
            ),
            FAIL2BAN_LOGS_CALLBACK: (
                FAIL2BAN_LOGS,
                "Загружаю логи...",
            ),
        }

        if data in screen_callbacks:
            screen_id, notice = screen_callbacks[data]
            navigation.go(cid, screen_id)
            navigation.render(
                screen_id,
                bot,
                cid,
                call.message.message_id,
            )
            return CallbackResponse(notice)
        if data == FAIL2BAN_UNBAN_CALLBACK:
            navigation.go(cid, FAIL2BAN_UNBAN_INPUT)
            navigation.render(
                FAIL2BAN_UNBAN_INPUT,
                bot,
                cid,
                call.message.message_id,
            )
            bot.register_next_step_handler(
                call.message,
                partial(
                    process_fail2ban_unban,
                    bot,
                    call.message.message_id,
                ),
            )
            return CallbackResponse()

    except Exception as e:
        err_text = str(e)
        if "message is not modified" in err_text or (
            "400" in err_text and "message" in err_text.lower()
        ):
            pass
        else:
            logger.error("fail2ban.handler.callback_failed | error=%s", e)
    return False


def process_fail2ban_unban(bot, prompt_message_id, message):
    """Обрабатывает ввод IP для разбана"""
    cid = message.chat.id
    if not is_admin(cid):
        return

    bot.clear_step_handler_by_chat_id(cid)
    navigation.back(cid)

    try:
        bot.delete_message(cid, prompt_message_id)
    except Exception as e:
        logger.debug("fail2ban.handler.input_cleanup_failed | error=%s", e)

    try:
        bot.delete_message(cid, message.message_id)
    except Exception as e:
        logger.debug("fail2ban.handler.ip_message_cleanup_failed | error=%s", e)

    ip = message.text.strip()

    if not validate_ip(ip):
        bot.send_message(cid, "❌ Неверный IPv4-адрес")
        return

    ok, result = unban_ip(ip)
    # Логирование действия
    if ok:
        log_action("РАЗБАН IP", ip, "SUCCESS")
    else:
        log_action("РАЗБАН IP", ip, "ERROR", result[:100])
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        )
    )
    bot.send_message(cid, result, parse_mode="Markdown", reply_markup=kb)
