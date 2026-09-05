"""
Админская часть системы тикетов поддержки.
"""

from telebot import types

from core.access import is_admin
from core.bot import bot
from core.callback_response import CallbackResponse
from core.navigation import (
    NAV_ADMIN_TICKETS_CALLBACK,
    NAV_ADMIN_TICKETS_CLOSED_CALLBACK,
    NAV_ADMIN_TICKETS_NEW_CALLBACK,
    NAV_ADMIN_TICKETS_WORKING_CALLBACK,
    NAV_CLIENTS_CALLBACK,
)
from services import ticket_service
from utils.helpers import escape_md
from utils.logger import logger
from utils.ttl_dict import TTLDict

# Черновики ответов админа. TTL: 30 минут.
_admin_reply_drafts = TTLDict(ttl=1800)


@bot.message_handler(commands=["tickets"])
def cmd_admin_tickets(message):
    cid = message.chat.id

    if not is_admin(cid):
        bot.send_message(cid, "⛔ Доступ запрещён.")
        return

    bot.send_message(cid, "🎫 Загрузка тикетов...")

    tickets = ticket_service.get_all_tickets()
    open_tickets = {
        tid: t for tid, t in tickets.items() if t.get("status") in ["open", "answered"]
    }

    if not open_tickets:
        bot.send_message(cid, "✅ Открытых тикетов нет.")
        return

    for tid, ticket in open_tickets.items():
        username = escape_md(str(ticket.get("username", "Unknown")))
        topic = escape_md(str(ticket.get("topic", "Без темы")))
        status = (
            "🟢 Открыт"
            if ticket.get("status") == "open"
            else "🟡 Ожидает ответа клиента"
        )
        created = escape_md(str(ticket.get("created_at", "Unknown")))

        text = (
            f"🎫 *Тикет #{tid}*\n"
            f"👤 Клиент: @{username}\n"
            f"📝 Тема: {topic}\n"
            f"📅 Создан: {created}\n"
            f"📌 Статус: {status}\n"
        )

        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(
                "✏️ Ответить",
                callback_data=f"admin_reply_ticket:{tid}",
            )
        )
        kb.add(
            types.InlineKeyboardButton(
                "✅ Закрыть",
                callback_data=f"admin_close_ticket:{tid}",
            )
        )

        bot.send_message(cid, text, parse_mode="Markdown", reply_markup=kb)


def _admin_ticket_card(ticket_id, ticket):
    """Формирует текст карточки тикета для администратора."""
    username = escape_md(str(ticket.get("username", "Unknown")))
    topic = escape_md(str(ticket.get("topic", "Без темы")))
    description = escape_md(str(ticket.get("description", "Без описания")))
    created = escape_md(str(ticket.get("created_at", "Неизвестно")))

    return (
        f"🎫 *Тикет #{ticket_id}*\n"
        f"👤 Клиент: @{username}\n"
        f"📝 Тема: {topic}\n"
        f"📄 Описание:\n{description}\n"
        f"📅 Создан: {created}"
    )


def handle_admin_tickets(bot, cid, call, data):
    """Показывает главное меню тикетов администратора."""
    if not is_admin(cid):
        return CallbackResponse("⛔ Доступ запрещён.")

    callback_response = CallbackResponse()

    tickets = ticket_service.get_all_tickets()

    new_count = sum(1 for ticket in tickets.values() if ticket.get("status") == "open")

    working_count = sum(
        1 for ticket in tickets.values() if ticket.get("status") == "answered"
    )

    closed_count = sum(
        1 for ticket in tickets.values() if ticket.get("status") == "closed"
    )

    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.add(
        types.InlineKeyboardButton(
            f"🆕 Новые тикеты ({new_count})",
            callback_data=NAV_ADMIN_TICKETS_NEW_CALLBACK,
        ),
        types.InlineKeyboardButton(
            f"🛠 В работе ({working_count})",
            callback_data=NAV_ADMIN_TICKETS_WORKING_CALLBACK,
        ),
    )

    kb.add(
        types.InlineKeyboardButton(
            f"📚 История закрытых ({closed_count})",
            callback_data=NAV_ADMIN_TICKETS_CLOSED_CALLBACK,
        ),
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_CLIENTS_CALLBACK,
        ),
    )

    try:
        bot.edit_message_text(
            chat_id=cid,
            message_id=call.message.message_id,
            text="🎫 *Управление тикетами*",
            parse_mode="Markdown",
            reply_markup=kb,
        )
    except Exception:
        bot.send_message(
            cid,
            "🎫 *Управление тикетами*",
            parse_mode="Markdown",
            reply_markup=kb,
        )

    return callback_response


def show_new_tickets(bot, cid, call=None, data=None):
    """Показывает новые тикеты."""
    if call is not None:
        cid = call.message.chat.id

    if not is_admin(cid):
        if call is not None:
            return CallbackResponse("⛔ Доступ запрещён.")
        bot.send_message(cid, "⛔ Доступ запрещён.")
        return CallbackResponse()

    callback_response = CallbackResponse()

    tickets = ticket_service.get_all_tickets()
    new_tickets = {
        tid: ticket for tid, ticket in tickets.items() if ticket.get("status") == "open"
    }

    if not new_tickets:
        if call is not None:
            return CallbackResponse("✅ Новых тикетов нет.")
        bot.send_message(cid, "✅ Новых тикетов нет.")
        return CallbackResponse()

    for tid, ticket in new_tickets.items():
        text = _admin_ticket_card(tid, ticket)

        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(
                "✏️ Ответить",
                callback_data=f"admin_reply_ticket:{tid}",
            )
        )
        kb.add(
            types.InlineKeyboardButton(
                "✅ Закрыть",
                callback_data=f"admin_close_ticket:{tid}",
            )
        )
        kb.add(
            types.InlineKeyboardButton(
                "↩️ Назад",
                callback_data=NAV_ADMIN_TICKETS_CALLBACK,
            )
        )

        bot.send_message(
            cid,
            text,
            parse_mode="Markdown",
            reply_markup=kb,
        )

    return callback_response


def show_working_tickets(bot, cid, call=None, data=None):
    """Показывает тикеты, на которые администратор уже ответил."""
    if call is not None:
        cid = call.message.chat.id

    if not is_admin(cid):
        if call is not None:
            return CallbackResponse("⛔ Доступ запрещён.")
        bot.send_message(cid, "⛔ Доступ запрещён.")
        return CallbackResponse()

    callback_response = CallbackResponse()

    tickets = ticket_service.get_all_tickets()
    working_tickets = {
        tid: ticket
        for tid, ticket in tickets.items()
        if ticket.get("status") == "answered"
    }

    if not working_tickets:
        if call is not None:
            return CallbackResponse("✅ Тикетов в работе нет.")
        bot.send_message(cid, "✅ Тикетов в работе нет.")
        return CallbackResponse()

    for tid, ticket in working_tickets.items():
        text = _admin_ticket_card(tid, ticket)

        messages = ticket.get("messages", [])
        if messages:
            text += "\n\n💬 *История:*"
            for item in messages:
                role = item.get("role", "unknown")
                message_text = escape_md(str(item.get("text", "")))
                message_time = escape_md(str(item.get("time", "")))

                if role == "client":
                    author = "👤 Клиент"
                elif role == "admin":
                    author = "👨‍💼 Админ"
                else:
                    author = str(role)

                text += f"\n\n{author} [{message_time}]:\n{message_text}"

        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(
                "✏️ Ответить ещё раз",
                callback_data=f"admin_reply_ticket:{tid}",
            )
        )
        kb.add(
            types.InlineKeyboardButton(
                "✅ Закрыть",
                callback_data=f"admin_close_ticket:{tid}",
            )
        )
        kb.add(
            types.InlineKeyboardButton(
                "↩️ Назад",
                callback_data=NAV_ADMIN_TICKETS_CALLBACK,
            )
        )

        bot.send_message(
            cid,
            text,
            parse_mode="Markdown",
            reply_markup=kb,
        )

    return callback_response


def _get_closed_tickets():
    tickets = ticket_service.get_all_tickets()
    closed_tickets = [
        (tid, ticket)
        for tid, ticket in tickets.items()
        if ticket.get("status") == "closed"
    ]
    closed_tickets.sort(
        key=lambda item: str(item[1].get("closed_at", "")),
        reverse=True,
    )
    return closed_tickets


def _closed_ticket_history_text(ticket_id, ticket):
    text = _admin_ticket_card(ticket_id, ticket)

    closed_at = escape_md(str(ticket.get("closed_at", "Неизвестно")))
    text += f"\n🔒 Закрыт: {closed_at}"

    messages = ticket.get("messages", [])
    if messages:
        text += "\n\n💬 *История:*"
        for item in messages:
            role = item.get("role", "unknown")
            message_text = escape_md(str(item.get("text", "")))
            message_time = escape_md(str(item.get("time", "")))

            if role == "client":
                author = "👤 Клиент"
            elif role == "admin":
                author = "👨‍💼 Админ"
            else:
                author = str(role)

            text += f"\n\n{author} [{message_time}]:\n{message_text}"

    return text


def show_closed_tickets(bot, cid, call=None, data=None):
    """Показывает страницу истории закрытых тикетов."""
    if call is not None:
        cid = call.message.chat.id

    if not is_admin(cid):
        if call is not None:
            return CallbackResponse("⛔ Доступ запрещён.")
        bot.send_message(cid, "⛔ Доступ запрещён.")
        return CallbackResponse()

    callback_response = CallbackResponse()

    closed_tickets = _get_closed_tickets()

    if not closed_tickets:
        if call is not None:
            return CallbackResponse("📭 Закрытых тикетов пока нет.")
        bot.send_message(cid, "📭 Закрытых тикетов пока нет.")
        return CallbackResponse()

    page = 0
    if isinstance(data, str) and data.startswith("admin_closed_page:"):
        try:
            page = max(0, int(data.split(":", 1)[1]))
        except (TypeError, ValueError):
            page = 0

    page_size = 2
    total_pages = (len(closed_tickets) + page_size - 1) // page_size
    page = min(page, total_pages - 1)

    start_index = page * page_size
    recent_tickets = closed_tickets[start_index : start_index + page_size]

    sections = [f"📚 *Закрытые тикеты — страница {page + 1}/{total_pages}*"]

    for tid, ticket in recent_tickets:
        closed_at = escape_md(str(ticket.get("closed_at", "Неизвестно")))
        sections.append(
            f"{_admin_ticket_card(tid, ticket)}\n"
            f"🔒 Закрыт: {closed_at}\n"
            f"💬 Сообщений: {len(ticket.get('messages', []))}"
        )

    text = "\n\n━━━━━━━━━━━━━━\n\n".join(sections)

    kb = types.InlineKeyboardMarkup()

    navigation_buttons = []
    if page > 0:
        navigation_buttons.append(
            types.InlineKeyboardButton(
                "◀️ Предыдущие",
                callback_data=f"admin_closed_page:{page - 1}",
            )
        )
    if page < total_pages - 1:
        navigation_buttons.append(
            types.InlineKeyboardButton(
                "Следующие ▶️",
                callback_data=f"admin_closed_page:{page + 1}",
            )
        )

    if navigation_buttons:
        kb.row(*navigation_buttons)

    for tid, _ticket in recent_tickets:
        kb.add(
            types.InlineKeyboardButton(
                f"👁 Открыть #{tid}",
                callback_data=f"admin_closed_ticket:{tid}",
            )
        )

    kb.add(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_ADMIN_TICKETS_CALLBACK,
        )
    )

    if call is not None:
        try:
            bot.edit_message_text(
                chat_id=cid,
                message_id=call.message.message_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        except Exception:
            bot.send_message(
                cid,
                text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
    else:
        bot.send_message(
            cid,
            text,
            parse_mode="Markdown",
            reply_markup=kb,
        )

    return callback_response


def show_closed_ticket(bot, cid, call=None, data=None):
    """Показывает полную историю одного закрытого тикета."""
    if call is not None:
        cid = call.message.chat.id

    if not is_admin(cid):
        return CallbackResponse("⛔ Доступ запрещён.")

    if not isinstance(data, str) or not data.startswith("admin_closed_ticket:"):
        return CallbackResponse("⛔ Некорректный тикет.")

    ticket_id = data.split(":", 1)[1]
    tickets = ticket_service.get_all_tickets()
    ticket = tickets.get(ticket_id)

    if ticket is None or ticket.get("status") != "closed":
        return CallbackResponse("📭 Закрытый тикет не найден.")

    text = _closed_ticket_history_text(ticket_id, ticket)

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data="admin_closed_page:0",
        )
    )

    if call is not None:
        try:
            bot.edit_message_text(
                chat_id=cid,
                message_id=call.message.message_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        except Exception:
            bot.send_message(
                cid,
                text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
    else:
        bot.send_message(
            cid,
            text,
            parse_mode="Markdown",
            reply_markup=kb,
        )

    return CallbackResponse()


def handle_admin_reply(bot, cid, call, data):
    cid = call.message.chat.id
    if not is_admin(cid):
        return CallbackResponse("⛔ Доступ запрещён.")

    ticket_id = data.split(":", 1)[1]
    tickets = ticket_service.get_all_tickets()

    if ticket_id not in tickets:
        return CallbackResponse("⚠️ Тикет не найден.")

    callback_response = CallbackResponse("Введите текст ответа")

    msg = bot.send_message(
        cid,
        (
            f"💬 *Ответ на тикет #{ticket_id}*\n\n"
            "Введите текст сообщения для клиента:\n\n"
            "_Для отмены введите /cancel_",
        ),
        parse_mode="Markdown",
    )

    _admin_reply_drafts[cid] = ticket_id
    bot.register_next_step_handler(msg, process_admin_reply)
    return callback_response


def process_admin_reply(message):
    cid = message.chat.id

    if message.text and message.text.lower() == "/cancel":
        bot.send_message(cid, "❌ Ответ отменён.")
        bot.clear_step_handler_by_chat_id(cid)
        if cid in _admin_reply_drafts:
            del _admin_reply_drafts[cid]
        return

    reply_text = message.text.strip()
    if not reply_text:
        bot.send_message(cid, "⚠️ Текст ответа не может быть пустым.")
        bot.register_next_step_handler(message, process_admin_reply)
        return

    ticket_id = _admin_reply_drafts.get(cid)

    if not ticket_id:
        bot.send_message(cid, "⚠️ Ошибка: контекст тикета потерян.")
        bot.clear_step_handler_by_chat_id(cid)
        return

    tickets = ticket_service.get_all_tickets()
    if ticket_id not in tickets:
        bot.send_message(cid, "⚠️ Тикет был удалён.")
        bot.clear_step_handler_by_chat_id(cid)
        del _admin_reply_drafts[cid]
        return

    ticket = tickets[ticket_id]
    client_cid = ticket["chat_id"]

    # Изменение тикета полностью принадлежит ticket_service.
    updated_ticket = ticket_service.add_message(
        ticket_id,
        "admin",
        reply_text,
    )

    if updated_ticket is None:
        bot.send_message(cid, "⚠️ Не удалось обновить тикет.")
        bot.clear_step_handler_by_chat_id(cid)
        del _admin_reply_drafts[cid]
        return

    ticket_service.set_status(ticket_id, "answered")

    bot.clear_step_handler_by_chat_id(cid)
    if cid in _admin_reply_drafts:
        del _admin_reply_drafts[cid]

    bot.send_message(cid, f"✅ Ответ на тикет #{ticket_id} отправлен клиенту.")

    # Отправляем сообщение клиенту
    try:
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(
                "📝 Ответить в тикет",
                callback_data=f"ticket_reply:{ticket_id}",
            )
        )
        bot.send_message(
            client_cid,
            f"🔔 *Новый ответ по тикету #{ticket_id}*\n\n"
            f"👨‍💼 *Администратор:* {escape_md(reply_text)}\n\n"
            f"Вы можете ответить в этот тикет или дождаться его закрытия.",
            parse_mode="Markdown",
            reply_markup=kb,
        )
    except Exception as e:
        logger.error(
            "ticket.reply.delivery_failed | ticket_id=%s | "
            "client_id=%s | admin_id=%s | error=%s",
            ticket_id,
            client_cid,
            cid,
            e,
        )
        bot.send_message(
            cid,
            (
                f"⚠️ Не удалось доставить сообщение клиенту "
                f"(возможно, он заблокировал бота): {e}",
            ),
        )


def handle_admin_close(bot, cid, call, data):
    cid = call.message.chat.id
    if not is_admin(cid):
        return CallbackResponse("⛔ Доступ запрещён.")

    ticket_id = data.split(":", 1)[1]
    tickets = ticket_service.get_all_tickets()

    if ticket_id not in tickets:
        return CallbackResponse("⚠️ Тикет не найден.")

    ticket = tickets[ticket_id]
    client_cid = ticket["chat_id"]

    updated_ticket = ticket_service.close_ticket(ticket_id)

    if updated_ticket is None:
        return CallbackResponse("⚠️ Не удалось закрыть тикет.")

    callback_response = CallbackResponse("Тикет закрыт")

    # Пересобираем карточку из данных тикета, а не дописываем Markdown
    # к уже отрендеренному сообщению. Это защищает от пользовательских
    # символов Markdown (например, "_" в username).
    text = _admin_ticket_card(ticket_id, updated_ticket)
    closed_at = escape_md(str(updated_ticket.get("closed_at", "Неизвестно")))
    text += f"\n🔒 Закрыт: {closed_at}"

    messages = updated_ticket.get("messages", [])
    if messages:
        text += "\n\n💬 *История:*"
        for item in messages:
            role = item.get("role", "unknown")
            message_text = escape_md(str(item.get("text", "")))
            message_time = escape_md(str(item.get("time", "")))

            if role == "client":
                author = "👤 Клиент"
            elif role == "admin":
                author = "👨‍💼 Админ"
            else:
                author = str(role)

            text += f"\n\n{author} [{message_time}]:\n{message_text}"

    bot.edit_message_text(
        chat_id=cid,
        message_id=call.message.message_id,
        text=text,
        parse_mode="Markdown",
    )

    try:
        bot.send_message(
            client_cid,
            (
                f"✅ *Тикет #{ticket_id} был закрыт администратором.*\n\n"
                "Если проблема осталась, пожалуйста, создайте новый тикет."
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(
            "ticket.close.notification_failed | ticket_id=%s | "
            "client_id=%s | admin_id=%s | error=%s",
            ticket_id,
            client_cid,
            cid,
            e,
        )

    return callback_response
