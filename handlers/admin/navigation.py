"""
Обработчики навигации и подменю.
Оптимизированная версия без лишних delete/send.
"""

from core.navigation import (
    NAV_AI_LOGS_CALLBACK,
    NAV_ANALYTICS_CALLBACK,
    NAV_BACK_CALLBACK,
    NAV_BACKUP_HISTORY_CALLBACK,
    NAV_BACKUPS_CALLBACK,
    NAV_CLIENTS_AWG_CALLBACK,
    NAV_CLIENTS_CALLBACK,
    NAV_CLIENTS_MANAGE_CALLBACK,
    NAV_CLIENTS_RENAME_CALLBACK,
    NAV_CLIENTS_VLESS_CALLBACK,
    NAV_CREATE_CALLBACK,
    NAV_HOME_CALLBACK,
    NAV_MANAGE_CALLBACK,
    NAV_NETWORK_CALLBACK,
    NAV_SYSTEM_CALLBACK,
    navigation,
)
from core.state import LAST_MAIN_MENU_MSGS
from ui.keyboards import (
    ai_diagnosis_menu_kb,
    analytics_menu_kb,
    backups_menu_kb,
    clients_manage_menu_kb,
    clients_menu_kb,
    create_menu_kb,
    main_menu_kb,
    manage_menu_kb,
    network_menu_kb,
    system_menu_kb,
)
from ui.screens import (
    ADMIN_AI_LOGS,
    ADMIN_ANALYTICS,
    ADMIN_BACKUPS,
    ADMIN_CLIENTS,
    ADMIN_CLIENTS_AWG,
    ADMIN_CLIENTS_MANAGE,
    ADMIN_CLIENTS_RENAME,
    ADMIN_CLIENTS_VLESS,
    ADMIN_CREATE,
    ADMIN_HOME,
    ADMIN_MANAGE,
    ADMIN_NETWORK,
    ADMIN_SYSTEM,
    BACKUP_HISTORY,
)
from utils.error_handler import handle_errors
from utils.formatters import get_help_text
from utils.helpers import safe_delete
from utils.logger import logger

# ============================================================
# Регистрация экранов навигационного адаптера.
#
# Каждый экран имеет единый контракт: ScreenRegistry хранит его
# renderer. NavigationManager отвечает за историю и отрисовку.
# Feature-модули регистрируют собственные экраны самостоятельно.
# ============================================================


def _render_static_screen(text_factory, keyboard_factory):
    """Создать renderer статического навигационного экрана."""

    def renderer(bot, cid, message_id):
        return _safe_edit(
            bot,
            cid,
            message_id,
            text_factory(),
            keyboard_factory(),
        )

    return renderer


_STATIC_SCREENS = {
    ADMIN_HOME: _render_static_screen(get_help_text, main_menu_kb),
    ADMIN_CREATE: _render_static_screen(
        lambda: "👤 *Создание клиента*",
        create_menu_kb,
    ),
    ADMIN_CLIENTS: _render_static_screen(
        lambda: "👥 *Клиенты*",
        clients_menu_kb,
    ),
    ADMIN_CLIENTS_MANAGE: _render_static_screen(
        lambda: "👥 *Управление клиентами*",
        clients_manage_menu_kb,
    ),
    ADMIN_MANAGE: _render_static_screen(
        lambda: "🌐 *Сеть и безопасность*",
        manage_menu_kb,
    ),
    ADMIN_SYSTEM: _render_static_screen(
        lambda: "🔧 *Система*",
        system_menu_kb,
    ),
    ADMIN_NETWORK: _render_static_screen(
        lambda: "🌐 *Сетевые инструменты*",
        network_menu_kb,
    ),
    ADMIN_ANALYTICS: _render_static_screen(
        lambda: "📊 *Аналитика*",
        analytics_menu_kb,
    ),
    ADMIN_BACKUPS: _render_static_screen(
        lambda: "💾 *Резервные копии*",
        backups_menu_kb,
    ),
    ADMIN_AI_LOGS: _render_static_screen(
        lambda: "🤖 *AI-диагностика логов*",
        ai_diagnosis_menu_kb,
    ),
}


def _safe_edit(bot, cid, mid, text, kb):
    """Отрисовать экран в существующем сообщении или создать новое."""
    try:
        bot.edit_message_text(
            text=text,
            chat_id=cid,
            message_id=mid,
            parse_mode="Markdown",
            reply_markup=kb,
        )
        return True

    except Exception as e:
        err = str(e)

        if "message is not modified" in err:
            return True

        if "message to edit not found" in err:
            try:
                bot.send_message(
                    chat_id=cid,
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=kb,
                )
                logger.debug(
                    "navigation.edit.fallback | chat_id=%s | message_id=%s",
                    cid,
                    mid,
                )
                return True
            except Exception:
                logger.exception(
                    "navigation.edit.fallback_failed | chat_id=%s | message_id=%s",
                    cid,
                    mid,
                )
                return False

        logger.exception(
            "navigation.edit.failed | chat_id=%s | message_id=%s | text=%r",
            cid,
            mid,
            text,
        )
        return False


def render_navigation_screen(bot, cid, message_id, screen_id):
    """Отрисовать экран исключительно через зарегистрированный renderer."""
    try:
        navigation.render(screen_id, bot, cid, message_id)
        return True
    except Exception:
        logger.exception(
            "navigation.render.failed | screen_id=%s",
            screen_id,
        )
        return False


@handle_errors("Ошибка handle_navigation_callback")
def handle_navigation_callback(bot, cid, call, data):
    """Единый Telegram-адаптер навигации."""

    def clear_input_context(delete_message=True):
        bot.clear_step_handler_by_chat_id(cid)

        from core.state import INPUT_REQUEST_MSGS

        message_id = INPUT_REQUEST_MSGS.pop(cid, None)

        # При возврате назад текущее сообщение нужно сохранить:
        # renderer должен отредактировать его и показать предыдущий экран.
        if delete_message and message_id is not None:
            safe_delete(bot, cid, message_id)

    if data == NAV_BACK_CALLBACK:
        logger.debug(
            "navigation.back.started | chat_id=%s | current=%s | "
            "history=%s | callback_message_id=%s",
            cid,
            navigation.current(cid),
            navigation.history(cid),
            call.message.message_id,
        )

        screen_id = navigation.back(cid)

        logger.debug(
            "navigation.back.completed | screen_id=%s | current=%s | history=%s",
            screen_id,
            navigation.current(cid),
            navigation.history(cid),
        )

        if screen_id is None:
            screen_id = ADMIN_HOME
            navigation.start(cid, screen_id)

        clear_input_context(delete_message=True)

        ok = render_navigation_screen(
            bot,
            cid,
            call.message.message_id,
            screen_id,
        )

        if ok and screen_id == ADMIN_HOME:
            LAST_MAIN_MENU_MSGS[cid] = call.message.message_id

        return ok

    if data == NAV_HOME_CALLBACK:
        screen_id = navigation.home(cid)

        if screen_id is None:
            screen_id = ADMIN_HOME
            navigation.start(cid, screen_id)

        clear_input_context()

        ok = render_navigation_screen(
            bot,
            cid,
            call.message.message_id,
            screen_id,
        )

        if ok and screen_id == ADMIN_HOME:
            LAST_MAIN_MENU_MSGS[cid] = call.message.message_id

        return ok

    screen_id = {
        NAV_CREATE_CALLBACK: ADMIN_CREATE,
        NAV_CLIENTS_CALLBACK: ADMIN_CLIENTS,
        NAV_CLIENTS_MANAGE_CALLBACK: ADMIN_CLIENTS_MANAGE,
        NAV_CLIENTS_VLESS_CALLBACK: ADMIN_CLIENTS_VLESS,
        NAV_CLIENTS_AWG_CALLBACK: ADMIN_CLIENTS_AWG,
        NAV_CLIENTS_RENAME_CALLBACK: ADMIN_CLIENTS_RENAME,
        NAV_MANAGE_CALLBACK: ADMIN_MANAGE,
        NAV_SYSTEM_CALLBACK: ADMIN_SYSTEM,
        NAV_NETWORK_CALLBACK: ADMIN_NETWORK,
        NAV_ANALYTICS_CALLBACK: ADMIN_ANALYTICS,
        NAV_BACKUPS_CALLBACK: ADMIN_BACKUPS,
        NAV_BACKUP_HISTORY_CALLBACK: BACKUP_HISTORY,
        NAV_AI_LOGS_CALLBACK: ADMIN_AI_LOGS,
    }.get(data)

    if screen_id is None:
        return False

    if navigation.current(cid) != screen_id:
        navigation.go(cid, screen_id)

    return render_navigation_screen(
        bot,
        cid,
        call.message.message_id,
        screen_id,
    )
