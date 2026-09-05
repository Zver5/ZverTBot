"""
Обработчики мониторинга процессов.
"""

from functools import partial

from telebot import types

from core.access import is_admin
from core.callback_response import CallbackResponse
from core.navigation import (
    NAV_BACK_CALLBACK,
    PROCESS_KILL_CALLBACK,
    PROCESS_MENU_CALLBACK,
    PROCESS_SEARCH_CALLBACK,
    PROCESS_TOP_CALLBACK,
    PROCESS_TOP_CPU_CALLBACK,
    PROCESS_TOP_RAM_CALLBACK,
    navigation,
)
from services.processes import (
    format_processes_text,
    kill_process_by_pid,
    search_process_by_name,
)
from ui.keyboards import processes_menu_kb
from ui.screens import (
    PROCESS_KILL_INPUT,
    PROCESS_MENU,
    PROCESS_SEARCH_INPUT,
    PROCESS_TOP,
    PROCESS_TOP_CPU,
    PROCESS_TOP_RAM,
)
from utils.error_handler import handle_errors
from utils.logger import logger
from utils.notifications import log_action
from utils.validators import validate_pid

# Telegram callbacks.


@handle_errors("Ошибка в handle_processes_callback")
def render_processes_menu(bot, cid, message_id):
    """Отрисовать главное меню процессов."""
    return bot.edit_message_text(
        "📊 *Мониторинг процессов*\nВыберите действие:",
        cid,
        message_id,
        parse_mode="Markdown",
        reply_markup=processes_menu_kb(),
    )


def _render_processes_top(bot, cid, message_id, sort_by):
    """Отрисовать топ процессов с выбранной сортировкой."""
    text = format_processes_text(sort_by=sort_by)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(
            "🔥 CPU",
            callback_data=PROCESS_TOP_CPU_CALLBACK,
        ),
        types.InlineKeyboardButton(
            "💾 RAM",
            callback_data=PROCESS_TOP_RAM_CALLBACK,
        ),
    )
    kb.add(
        types.InlineKeyboardButton(
            "🔄 Обновить",
            callback_data=PROCESS_TOP_CALLBACK,
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
        if "message is not modified" in str(e):
            return True
        raise


@handle_errors("Ошибка в handle_processes_callback")
def render_processes_top(bot, cid, message_id):
    """Отрисовать топ процессов."""
    return _render_processes_top(
        bot,
        cid,
        message_id,
        "cpu",
    )


@handle_errors("Ошибка в handle_processes_callback")
def render_processes_top_cpu(bot, cid, message_id):
    """Отрисовать топ процессов по CPU."""
    return _render_processes_top(
        bot,
        cid,
        message_id,
        "cpu",
    )


@handle_errors("Ошибка в handle_processes_callback")
def render_processes_top_ram(bot, cid, message_id):
    """Отрисовать топ процессов по RAM."""
    return _render_processes_top(
        bot,
        cid,
        message_id,
        "mem",
    )


def render_processes_search_input(bot, cid, message_id):
    """Отрисовать экран ввода имени процесса для поиска."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        )
    )
    return bot.edit_message_text(
        "🔍 *Введите имя процесса для поиска:*\nПример: `xray`, `python`, `nginx`",
        cid,
        message_id,
        parse_mode="Markdown",
        reply_markup=kb,
    )


def render_processes_kill_input(bot, cid, message_id):
    """Отрисовать экран ввода PID для завершения процесса."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        )
    )
    return bot.edit_message_text(
        "🛑 *Введите PID процесса для завершения:*\n"
        "💡 PID можно найти в Топ CPU/RAM\n"
        "Пример: `1234`",
        cid,
        message_id,
        parse_mode="Markdown",
        reply_markup=kb,
    )


def handle_processes_callback(bot, cid, call, data):
    """Обрабатывает подменю мониторинга процессов"""
    try:
        if data == PROCESS_MENU_CALLBACK:
            if navigation.current(cid) == PROCESS_MENU:
                return CallbackResponse()

            navigation.go(cid, PROCESS_MENU)
            navigation.render(
                PROCESS_MENU,
                bot,
                cid,
                call.message.message_id,
            )
            return CallbackResponse()
        if data in {
            PROCESS_TOP_CALLBACK,
            PROCESS_TOP_CPU_CALLBACK,
            PROCESS_TOP_RAM_CALLBACK,
        }:
            top_options = {
                PROCESS_TOP_CALLBACK: (
                    "cpu",
                    PROCESS_TOP,
                    "Загружаю топ процессов...",
                ),
                PROCESS_TOP_CPU_CALLBACK: (
                    "cpu",
                    PROCESS_TOP_CPU,
                    "Сортировка по CPU...",
                ),
                PROCESS_TOP_RAM_CALLBACK: (
                    "mem",
                    PROCESS_TOP_RAM,
                    "Сортировка по RAM...",
                ),
            }

            _, navigation_state, answer_text = top_options[data]

            if navigation.current(cid) != navigation_state:
                if data == PROCESS_TOP_CALLBACK:
                    navigation.go(cid, navigation_state)
                else:
                    # Intentional: replace the current process screen so intermediate
                    # process views do not accumulate in NavigationStack history.
                    navigation.replace(cid, navigation_state)

            navigation.render(
                navigation_state,
                bot,
                cid,
                call.message.message_id,
            )

            return CallbackResponse(answer_text)

        if data == PROCESS_SEARCH_CALLBACK:
            navigation.go(cid, PROCESS_SEARCH_INPUT)
            navigation.render(
                PROCESS_SEARCH_INPUT,
                bot,
                cid,
                call.message.message_id,
            )
            bot.register_next_step_handler(
                call.message,
                partial(
                    process_search_handler,
                    bot,
                    call.message.message_id,
                ),
            )
            return CallbackResponse("Введите имя процесса...")

        if data == PROCESS_KILL_CALLBACK:
            navigation.go(cid, PROCESS_KILL_INPUT)
            navigation.render(
                PROCESS_KILL_INPUT,
                bot,
                cid,
                call.message.message_id,
            )
            bot.register_next_step_handler(
                call.message,
                partial(
                    process_kill_handler,
                    bot,
                    call.message.message_id,
                ),
            )
            return CallbackResponse("Введите PID процесса...")

    except Exception as e:
        err_text = str(e)
        if "message is not modified" in err_text or (
            "400" in err_text and "message" in err_text.lower()
        ):
            pass
        else:
            logger.error(
                "processes.handler.callback_failed | error=%s",
                e,
            )
    return False


def process_search_handler(bot, prompt_message_id, message):
    """Обрабатывает ввод имени процесса для поиска."""
    cid = message.chat.id
    if not is_admin(cid):
        return

    bot.clear_step_handler_by_chat_id(cid)
    navigation.back(cid)

    try:
        bot.delete_message(cid, prompt_message_id)
    except Exception as e:
        logger.debug(
            "processes.search.input_cleanup_failed | error=%s",
            e,
        )

    try:
        bot.delete_message(cid, message.message_id)
    except Exception as e:
        logger.debug(
            "processes.search.message_cleanup_failed | error=%s",
            e,
        )

    name = message.text.strip()
    text = search_process_by_name(name)
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        )
    )
    bot.send_message(cid, text, parse_mode="Markdown", reply_markup=kb)


def process_kill_handler(bot, prompt_message_id, message):
    """Обрабатывает ввод PID для завершения процесса."""
    cid = message.chat.id
    if not is_admin(cid):
        return

    bot.clear_step_handler_by_chat_id(cid)
    navigation.back(cid)

    try:
        bot.delete_message(cid, prompt_message_id)
    except Exception as e:
        logger.debug(
            "processes.kill.input_cleanup_failed | error=%s",
            e,
        )

    try:
        bot.delete_message(cid, message.message_id)
    except Exception as e:
        logger.debug(
            "processes.kill.message_cleanup_failed | error=%s",
            e,
        )

    pid = message.text.strip()
    if not validate_pid(pid):
        bot.send_message(cid, "❌ Неверный формат PID")
        return

    # Получаем имя процесса ДО убийства
    proc_name = "unknown"
    try:
        with open(f"/proc/{pid}/comm") as f:
            proc_name = f.read().strip()
    except Exception as e:
        logger.debug(
            "processes.kill.process_lookup_failed | pid=%s | error=%s",
            pid,
            e,
        )
        proc_name = f"PID={pid}"

    ok, result = kill_process_by_pid(pid)
    # Логирование действия
    if ok:
        log_action("ЗАВЕРШЕНИЕ ПРОЦЕССА", proc_name, "SUCCESS")
    else:
        log_action("ЗАВЕРШЕНИЕ ПРОЦЕССА", proc_name, "ERROR", result[:100])
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("↩️ Назад", callback_data=NAV_BACK_CALLBACK))
    bot.send_message(cid, result, parse_mode="Markdown", reply_markup=kb)
