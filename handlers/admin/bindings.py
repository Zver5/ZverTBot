"""
Обработчики привязок клиентов к Telegram.
"""

from telebot import types

from core.callback_response import CallbackResponse
from core.navigation import NAV_BACK_CALLBACK, navigation
from services.bindings import (
    add_client_binding,
    get_all_client_bindings,
    get_client_bindings,
    get_pending_bindings,
    remove_client_binding,
    remove_pending_binding,
)
from services.client_service import get_users_list
from ui.screens import BINDINGS_ACTIVE, BINDINGS_MENU, BINDINGS_PENDING
from utils.error_handler import handle_errors
from utils.helpers import (
    escape_md,
    normalize_client_list,
    safe_delete,
    safe_send_message,
)
from utils.logger import logger
from utils.notifications import log_action


def _get_all_users():
    """Возвращает уникальный отсортированный список клиентов VLESS и AWG."""
    users_vless = get_users_list("vless")
    users_awg = get_users_list("awg")
    return sorted(set(users_vless) | set(users_awg))


def _get_bound_users(bindings):
    """Возвращает множество всех уже привязанных клиентов."""
    bound_users = set()
    for clients in bindings.values():
        bound_users.update(normalize_client_list(clients))
    return bound_users


def _get_unbound_users(bindings):
    """Возвращает клиентов, которые ещё ни к одному чату не привязаны."""
    bound_users = _get_bound_users(bindings)
    return [user for user in _get_all_users() if user not in bound_users]


def _build_bind_keyboard(target_cid, users):
    """Создаёт клавиатуру с кнопками выбора клиента для привязки."""
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(
            f"👤 {user}",
            callback_data=f"do_bind_{target_cid}_{user}",
        )
        for user in users
    ]
    buttons.append(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        )
    )
    kb.add(*buttons)

    return kb


def _build_pending_bind_keyboard(target_cid, users):
    """Создаёт клавиатуру выбора клиента для заявки на привязку."""
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(
            f"👤 {user}",
            callback_data=f"do_bind_{target_cid}_{user}",
        )
        for user in users
    ]
    buttons.append(
        types.InlineKeyboardButton(
            "❌ Отмена",
            callback_data=NAV_BACK_CALLBACK,
        )
    )
    kb.add(*buttons)
    return kb


def _build_unbind_keyboard(p_cid, clients):
    """Создаёт клавиатуру выбора клиента для отвязки."""
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(
            f"✖️ {client}",
            callback_data=f"unbind_confirm_{p_cid}_{client}",
        )
        for client in clients
    ]
    buttons.append(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        )
    )
    kb.add(*buttons)
    return kb


def render_bindings_menu(bot, cid, message_id):
    """Отрисовать главное меню управления привязками."""
    bindings = get_all_client_bindings()
    active_count = sum(
        len(normalize_client_list(clients)) for clients in bindings.values()
    )
    pending_count = len(get_pending_bindings())

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(
            f"✅ Активные ({active_count})",
            callback_data="bindings_active",
        ),
        types.InlineKeyboardButton(
            f"⏳ Ожидающие ({pending_count})",
            callback_data="bindings_pending",
        ),
    )
    kb.add(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        )
    )

    try:
        bot.edit_message_text(
            "🔗 *УПРАВЛЕНИЕ ПРИВЯЗКАМИ*\nВыберите раздел:",
            cid,
            message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )
        return True
    except Exception as e:
        logger.exception("bindings.render.menu_failed | error=%s", e)
        return False


def render_bindings_active(bot, cid, message_id):
    """Отрисовать список активных привязок."""
    bindings = get_all_client_bindings()

    active_list = []
    for p_cid, clients in bindings.items():
        clients = normalize_client_list(clients)
        if clients:
            active_list.append((p_cid, clients))

    if not active_list:
        text = "👥 *АКТИВНЫЕ ПРИВЯЗКИ (0):*\n\nНет активных привязок."
        kb = types.InlineKeyboardMarkup()
    else:
        text = "👥 *АКТИВНЫЕ ПРИВЯЗКИ (" + str(len(active_list)) + "):*\n\n"
        kb = types.InlineKeyboardMarkup(row_width=2)

        for p_cid, clients in active_list:
            name_label = ", ".join(clients)
            kb.add(
                types.InlineKeyboardButton(
                    "👤 " + name_label,
                    callback_data="bind_existing_" + p_cid,
                ),
                types.InlineKeyboardButton(
                    "✖️ " + p_cid,
                    callback_data="unbind_select_" + p_cid,
                ),
            )

    kb.add(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        )
    )

    try:
        bot.edit_message_text(
            text,
            cid,
            message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )
        return True
    except Exception as e:
        logger.exception("bindings.render.active_failed | error=%s", e)
        return False


def render_bindings_pending(bot, cid, message_id):
    """Отрисовать список ожидающих заявок."""
    pending = get_pending_bindings()

    if not pending:
        text = "📋 *ОЖИДАЮЩИЕ ЗАЯВКИ:*\n\nЗаявок нет."
        kb = types.InlineKeyboardMarkup()
    else:
        text = "📋 *ОЖИДАЮЩИЕ ЗАЯВКИ:*\n"
        kb = types.InlineKeyboardMarkup(row_width=2)

        for p_cid, info in pending.items():
            bindings_check = get_all_client_bindings()
            current_list = normalize_client_list(bindings_check.get(p_cid, []))
            bound_info = (
                f" (🔗 {escape_md(', '.join(current_list))})" if current_list else ""
            )
            safe_time = escape_md(str(info["time"]))

            text += (
                f"👤 {escape_md(info['name'])} | 🆔 `{p_cid}`"
                f"{bound_info}\n🕒 {safe_time}\n"
            )

            button_name = info["name"]

            kb.add(
                types.InlineKeyboardButton(
                    f"✅ Привязать {button_name}",
                    callback_data=f"approve_bind_{p_cid}",
                ),
                types.InlineKeyboardButton(
                    f"❌ Отклонить {button_name}",
                    callback_data=f"reject_bind_{p_cid}",
                ),
            )

    kb.add(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        )
    )

    try:
        bot.edit_message_text(
            text,
            cid,
            message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )
        return True
    except Exception as e:
        logger.exception("bindings.render.pending_failed | error=%s", e)
        return False


@handle_errors("Ошибка в handle_bindings_part1_callback")
def handle_bindings_part1_callback(bot, cid, call, data):
    """Обрабатывает заявки на привязку: approve_bind_, do_bind_, reject_bind_"""
    if data.startswith("approve_bind_"):
        target_cid = data.split("_", 2)[2]
        pending = get_pending_bindings()
        if target_cid not in pending:
            return CallbackResponse("Заявка уже обработана или удалена.")

        bindings = get_all_client_bindings()
        unbound = _get_unbound_users(bindings)

        if not unbound:
            return CallbackResponse("Нет непривязанных клиентов!")

        kb = _build_pending_bind_keyboard(target_cid, unbound)

        user_info = escape_md(pending[target_cid]["name"])
        text = (
            f"📋 *Привязка клиента*\n"
            f"👤 Пользователь: {user_info}\n"
            f"🆔 Chat ID: `{target_cid}`\n\n"
            "Выберите клиента для привязки:"
        )
        bot.edit_message_text(
            text,
            cid,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )
        return CallbackResponse()

    if data.startswith("do_bind_"):
        parts = data.split("_", 3)
        target_cid = parts[2]
        username = parts[3]
        binding_result = add_client_binding(target_cid, username)

        if binding_result == "added":
            remove_pending_binding(target_cid)

        if binding_result == "duplicate":
            return CallbackResponse("Уже привязан!")

        if binding_result == "limit":
            return CallbackResponse("Лимит: 4 аккаунта на чат!")
        log_action("ПРИВЯЗКА", username, "SUCCESS", f"chat_id: {target_cid}")
        callback_response = CallbackResponse(f"✅ {username} добавлен!")

        safe_send_message(
            bot,
            target_cid,
            f"✅ Аккаунт `{escape_md(username)}` успешно привязан!",
            parse_mode="Markdown",
        )

        # Возврат в то же меню выбора клиента для привязки
        bindings = get_all_client_bindings()
        current_list = normalize_client_list(bindings.get(target_cid, []))

        unbound = _get_unbound_users(bindings)

        text = (
            "📋 *Добавить клиента*\n"
            f"🆔 Chat ID: `{target_cid}`\n"
            f"👥 Уже привязано: `{len(current_list)}/4`\n\n"
            "Выберите клиента для привязки:"
        )

        kb = _build_bind_keyboard(target_cid, unbound)

        bot.edit_message_text(
            text,
            cid,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )
        return callback_response

    if data.startswith("reject_bind_"):
        target_cid = data.split("_", 2)[2]
        pending = get_pending_bindings()
        if target_cid in pending:
            remove_pending_binding(target_cid)

            render_bindings_pending(
                bot,
                cid,
                call.message.message_id,
            )

            safe_send_message(
                bot,
                target_cid,
                "❌ Ваша заявка на привязку отклонена администратором.",
            )

            log_action("ОТКЛОНЕНИЕ ЗАЯВКИ", f"chat_id={target_cid}", "SUCCESS")
            return CallbackResponse("Заявка отклонена.")
        return CallbackResponse()
    return False


@handle_errors("Ошибка в handle_bindings_part2_callback")
def handle_bindings_part2_callback(bot, cid, call, data):
    """Обрабатывает меню привязок через единую систему навигации."""

    if data == "bindings_menu":
        navigation.go(cid, BINDINGS_MENU)
        navigation.render(BINDINGS_MENU, bot, cid, call.message.message_id)
        return CallbackResponse()

    if data == "bindings_pending":
        navigation.go(cid, BINDINGS_PENDING)
        navigation.render(BINDINGS_PENDING, bot, cid, call.message.message_id)
        return CallbackResponse()

    if data == "bindings_active":
        navigation.go(cid, BINDINGS_ACTIVE)
        navigation.render(BINDINGS_ACTIVE, bot, cid, call.message.message_id)
        return CallbackResponse()

    return False


@handle_errors("Ошибка в выборе клиента для существующей привязки")
def handle_bind_existing_callback(bot, cid, call, data):
    """Открывает выбор дополнительного клиента для существующей привязки."""
    if not data.startswith("bind_existing_"):
        return False

    target_cid = data.split("_", 2)[2]

    bindings = get_all_client_bindings()
    current_list = normalize_client_list(bindings.get(target_cid, []))

    if len(current_list) >= 4:
        return CallbackResponse("Лимит: 4 аккаунта на чат!")

    unbound = _get_unbound_users(bindings)

    if not unbound:
        return CallbackResponse("Нет непривязанных клиентов!")

    kb = _build_bind_keyboard(target_cid, unbound)

    text = (
        "📋 *Добавить клиента*\n"
        f"🆔 Chat ID: `{target_cid}`\n"
        f"👥 Уже привязано: `{len(current_list)}/4`\n\n"
        "Выберите клиента для привязки:"
    )

    bot.edit_message_text(
        text, cid, call.message.message_id, parse_mode="Markdown", reply_markup=kb
    )

    return CallbackResponse()


@handle_errors("Ошибка в handle_bindings_part3_callback")
def handle_bindings_part3_callback(bot, cid, call, data):
    """Обрабатывает отвязку: unbind_select_, unbind_confirm_"""
    if data.startswith("unbind_select_"):
        p_cid = data.split("_", 2)[2]
        clients = get_client_bindings(p_cid)
        if not clients:
            return CallbackResponse("Нет привязанных клиентов")

        text = f"⚠️ Выберите клиента для отвязки от 🆔 `{p_cid}`:"
        kb = _build_unbind_keyboard(p_cid, clients)

        safe_delete(bot, cid, call.message.message_id)
        bot.send_message(cid, text, parse_mode="Markdown", reply_markup=kb)
        return CallbackResponse()

    if data.startswith("unbind_confirm_"):
        parts = data.split("_", 3)
        p_cid = parts[2]
        username = parts[3]
        removal_result = remove_client_binding(p_cid, username)

        if removal_result:
            log_action("ОТВЯЗКА", username, "SUCCESS", f"chat_id: {p_cid}")
            callback_response = CallbackResponse(f"✅ {username} отвязан!")
            safe_send_message(
                bot,
                p_cid,
                f"❌ Ваш аккаунт `{escape_md(username)}` отвязан администратором.",
                parse_mode="Markdown",
            )
        else:
            callback_response = CallbackResponse("Клиент не найден в привязках")

        # Возврат в то же меню выбора клиента для отвязки
        clients = get_client_bindings(p_cid)
        text = f"⚠️ Выберите клиента для отвязки от 🆔 `{p_cid}`:"
        kb = _build_unbind_keyboard(p_cid, clients)
        bot.edit_message_text(
            text,
            cid,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )
        return callback_response
    return False
