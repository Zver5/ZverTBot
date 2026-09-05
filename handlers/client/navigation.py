"""
Навигация клиентского меню.

Клиентская навигация использует общий core.navigation,
но имеет собственные screen ID и Telegram callbacks.
"""

from core.callback_response import CallbackResponse
from core.navigation import (
    CLIENT_CONF_CALLBACK_PREFIX,
    CLIENT_CONF_RU_CALLBACK_PREFIX,
    NAV_CLIENT_BACK_CALLBACK,
    NAV_CLIENT_HELP_CALLBACK,
    NAV_CLIENT_HOME_CALLBACK,
    navigation,
)
from core.state import LAST_CLIENT_MENU_MSGS
from handlers.client.menu import (
    handle_client_conf,
    handle_client_conf_ru,
    handle_client_stats,
    render_client_account,
)
from ui.client_menu import (
    CLIENT_ACCOUNT_PREFIX,
    CLIENT_STATS_PREFIX,
)
from ui.screens import CLIENT_ACCOUNT, CLIENT_HELP, CLIENT_HOME
from utils.error_handler import handle_errors
from utils.helpers import safe_send_message
from utils.logger import logger

# Runtime-данные текущего account screen. Это НЕ navigation history и НЕ screen ID.
_CLIENT_ACCOUNT_USERS = {}


def _render_client_account(bot, cid, message_id):
    """Отрисовать текущий аккаунт из runtime-данных chat."""
    username = _CLIENT_ACCOUNT_USERS.get(cid)

    if not username:
        safe_send_message(
            bot,
            cid,
            "❌ Клиент не найден.",
        )
        return False

    return render_client_account(
        bot,
        cid,
        message_id,
        username,
    )


def render_client_navigation_screen(bot, cid, message_id, screen_id):
    """Отрисовать зарегистрированный клиентский экран."""
    try:
        return bool(
            navigation.render(
                screen_id,
                bot,
                cid,
                message_id,
            )
        )
    except Exception:
        logger.exception(
            "client_navigation.render.failed | screen_id=%s",
            screen_id,
        )
        return False


def _get_account_username(data):
    """Извлечь username из callback аккаунта."""
    return data.removeprefix(CLIENT_ACCOUNT_PREFIX)


def _is_client_account_owned(cid, username):
    """Проверить, принадлежит ли аккаунт указанному клиенту."""
    from ui.client_menu import get_client_list

    return username in get_client_list(cid)


def _open_account(bot, cid, message_id, username):
    """Открыть принадлежащий клиенту аккаунт."""
    if not username or not _is_client_account_owned(cid, username):
        safe_send_message(
            bot,
            cid,
            "❌ Клиент не найден.",
        )
        return False

    _CLIENT_ACCOUNT_USERS[cid] = username
    navigation.go(cid, CLIENT_ACCOUNT)

    return render_client_navigation_screen(
        bot,
        cid,
        message_id,
        CLIENT_ACCOUNT,
    )


@handle_errors("Ошибка handle_client_navigation_callback")
def handle_client_navigation_callback(bot, cid, call, data):
    """Единый Telegram-adapter клиентской навигации."""

    message_id = call.message.message_id

    if data == NAV_CLIENT_BACK_CALLBACK:
        screen_id = navigation.back(cid)

        if screen_id is None:
            screen_id = CLIENT_HOME
            navigation.start(cid, screen_id)

        ok = render_client_navigation_screen(
            bot,
            cid,
            message_id,
            screen_id,
        )

        if ok and screen_id == CLIENT_HOME:
            LAST_CLIENT_MENU_MSGS[cid] = message_id

        return CallbackResponse() if ok else False

    if data == NAV_CLIENT_HOME_CALLBACK:
        screen_id = navigation.home(cid)

        if screen_id is None:
            screen_id = CLIENT_HOME
            navigation.start(cid, screen_id)

        ok = render_client_navigation_screen(
            bot,
            cid,
            message_id,
            screen_id,
        )

        if ok and screen_id == CLIENT_HOME:
            LAST_CLIENT_MENU_MSGS[cid] = message_id

        return CallbackResponse() if ok else False

    if data == NAV_CLIENT_HELP_CALLBACK:
        screen_id = CLIENT_HELP
        navigation.go(cid, screen_id)

        return render_client_navigation_screen(
            bot,
            cid,
            message_id,
            screen_id,
        )

    if data.startswith(CLIENT_ACCOUNT_PREFIX):
        username = _get_account_username(data)
        return _open_account(
            bot,
            cid,
            message_id,
            username,
        )

    if data.startswith(CLIENT_STATS_PREFIX):
        return handle_client_stats(bot, cid, call, data)

    if data.startswith(CLIENT_CONF_RU_CALLBACK_PREFIX):
        return handle_client_conf_ru(bot, cid, call, data)

    if data.startswith(CLIENT_CONF_CALLBACK_PREFIX):
        return handle_client_conf(bot, cid, call, data)

    return False
