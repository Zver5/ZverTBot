"""
Клиентская часть системы тикетов поддержки.
"""

from telebot import types

from config.secrets import ADMIN_CHATS
from core.bot import bot
from core.callback_response import CallbackResponse
from services import ticket_service
from services.bindings import get_client_bindings
from utils.helpers import (
    escape_md,
    safe_edit_message,
    safe_edit_message_reply_markup,
    safe_send_message,
)
from utils.logger import logger
from utils.ttl_dict import TTLDict

# Черновики создаваемых клиентских тикетов. TTL: 30 минут.
_ticket_drafts = TTLDict(ttl=1800)
_ticket_reply_drafts = TTLDict(ttl=1800)


def handle_create_ticket(bot, cid, call, data):
    cid = call.message.chat.id

    # Отмена создания тикета обрабатывается первой.
    if data == "ticket_cancel":
        bot.clear_step_handler_by_chat_id(cid)
        _ticket_drafts.pop(cid, None)
        safe_edit_message(
            bot,
            "❌ Создание тикета отменено.",
            cid,
            call.message.message_id,
        )
        return CallbackResponse("Создание тикета отменено.")

    # Проверяем, является ли пользователь клиентом
    bindings = get_client_bindings(str(cid))
    if not bindings:
        return CallbackResponse("⚠️ Вы не привязаны к аккаунту!")

    # У клиента может быть только один активный тикет.
    active_ticket = ticket_service.get_client_active_ticket(cid)

    if active_ticket:
        ticket_id, _ticket = active_ticket
        return CallbackResponse(
            f"У вас уже есть активный тикет #{ticket_id}.",
            show_alert=True,
        )

    # Выбор готовой темы
    topics = {
        "ticket_topic_internet": "Не работает интернет",
        "ticket_topic_vpn": "Не подключается VPN",
        "ticket_topic_config": "Не пришёл QR / конфиг",
        "ticket_topic_other": "Другая проблема",
    }

    if data in topics:
        topic = topics[data]

        # Используем то же сообщение: после выбора темы просто
        # переходим к следующему шагу, не создавая новое сообщение.
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton(
                "❌ Отмена",
                callback_data="ticket_cancel",
            )
        )

        safe_edit_message(
            bot,
            f"📝 *Создание тикета*\n\n"
            f"*Тема:* {escape_md(topic)}\n\n"
            "✏️ Опишите вашу проблему одним сообщением:",
            cid,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )

        _ticket_drafts[cid] = {
            "topic": topic,
            "prompt_message_id": call.message.message_id,
        }

        bot.register_next_step_handler(
            call.message,
            process_ticket_description,
        )
        return CallbackResponse()

    # Первый экран создания тикета

    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.add(
        types.InlineKeyboardButton(
            "🌐 Не работает интернет",
            callback_data="ticket_topic_internet",
        ),
        types.InlineKeyboardButton(
            "🔌 Не подключается VPN",
            callback_data="ticket_topic_vpn",
        ),
        types.InlineKeyboardButton(
            "📄 Не пришёл QR / конфиг",
            callback_data="ticket_topic_config",
        ),
        types.InlineKeyboardButton(
            "❓ Другая проблема",
            callback_data="ticket_topic_other",
        ),
    )

    kb.add(
        types.InlineKeyboardButton(
            "❌ Отмена",
            callback_data="ticket_cancel",
        )
    )

    safe_edit_message(
        bot,
        "📝 *Создание тикета*\n\nВыберите тему:",
        cid,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=kb,
    )
    return CallbackResponse("Создание тикета")


def handle_ticket_reply(bot, cid, call, data):
    """Начинает ответ клиента в существующий тикет."""

    ticket_id = data.split(":", 1)[1] if ":" in data else ""

    ticket = ticket_service.get_ticket(ticket_id)

    if ticket is None:
        return CallbackResponse(
            "⚠️ Тикет не найден или уже закрыт.",
            show_alert=True,
        )

    if ticket.get("chat_id") != cid:
        return CallbackResponse(
            "⛔ Этот тикет вам недоступен.",
            show_alert=True,
        )

    if ticket.get("status") == "closed":
        return CallbackResponse(
            "⚠️ Тикет уже закрыт.",
            show_alert=True,
        )

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            "❌ Отмена",
            callback_data=f"ticket_reply_cancel:{ticket_id}",
        )
    )

    _ticket_reply_drafts[cid] = {
        "ticket_id": ticket_id,
    }

    msg = bot.send_message(
        cid,
        f"💬 *Ответ в тикет #{ticket_id}*\n\nВведите ваше сообщение:",
        parse_mode="Markdown",
        reply_markup=kb,
    )

    _ticket_reply_drafts[cid]["prompt_message_id"] = msg.message_id
    bot.register_next_step_handler(msg, process_ticket_reply)

    return CallbackResponse()


def handle_ticket_reply_cancel(bot, cid, call, data):
    """Отменяет ввод ответа клиента в тикет."""

    draft = _ticket_reply_drafts.pop(cid, None)
    bot.clear_step_handler_by_chat_id(cid)

    if isinstance(draft, dict):
        prompt_message_id = draft.get("prompt_message_id")
        if prompt_message_id:
            try:
                bot.edit_message_text(
                    "❌ Ответ отменён.",
                    cid,
                    prompt_message_id,
                )
            except Exception as e:
                logger.warning(
                    "ticket.reply.cancel_message_update_failed | "
                    "chat_id=%s | error=%s",
                    cid,
                    e,
                )

    return CallbackResponse()


def process_ticket_reply(message):
    """Сохраняет ответ клиента в существующий тикет."""

    cid = message.chat.id

    draft = _ticket_reply_drafts.get(cid)
    ticket_id = draft.get("ticket_id") if isinstance(draft, dict) else draft

    if not ticket_id:
        safe_send_message(
            bot,
            cid,
            "⚠️ Контекст тикета потерян. Попробуйте открыть ответ ещё раз.",
        )
        bot.clear_step_handler_by_chat_id(cid)
        return

    if message.text and message.text.lower() == "/cancel":
        safe_send_message(bot, cid, "❌ Ответ отменён.")
        bot.clear_step_handler_by_chat_id(cid)
        del _ticket_reply_drafts[cid]
        return

    reply_text = (message.text or "").strip()

    if not reply_text:
        safe_send_message(
            bot,
            cid,
            "⚠️ Сообщение не может быть пустым. Попробуйте ещё раз.",
        )
        bot.register_next_step_handler(message, process_ticket_reply)
        return

    ticket = ticket_service.get_ticket(ticket_id)

    if ticket is None:
        safe_send_message(bot, cid, "⚠️ Тикет не найден.")
        bot.clear_step_handler_by_chat_id(cid)
        del _ticket_reply_drafts[cid]
        return

    if ticket.get("chat_id") != cid:
        safe_send_message(bot, cid, "⛔ Этот тикет вам недоступен.")
        bot.clear_step_handler_by_chat_id(cid)
        del _ticket_reply_drafts[cid]
        return

    if ticket.get("status") == "closed":
        safe_send_message(
            bot,
            cid,
            f"⚠️ Тикет #{ticket_id} уже закрыт. "
            f"Создайте новый тикет, если проблема осталась.",
        )
        bot.clear_step_handler_by_chat_id(cid)
        del _ticket_reply_drafts[cid]
        return

    updated_ticket = ticket_service.add_message(
        ticket_id,
        "client",
        reply_text,
    )

    if updated_ticket is None:
        safe_send_message(bot, cid, "⚠️ Не удалось сохранить ответ в тикет.")
        bot.clear_step_handler_by_chat_id(cid)
        del _ticket_reply_drafts[cid]
        return

    ticket_service.set_status(ticket_id, "open")

    bot.clear_step_handler_by_chat_id(cid)
    del _ticket_reply_drafts[cid]

    safe_send_message(
        bot,
        cid,
        f"✅ *Ответ в тикет #{ticket_id} отправлен.*\n\n"
        f"Администратор получит ваше сообщение.",
        parse_mode="Markdown",
    )

    safe_username = escape_md(str(message.from_user.username or cid))
    safe_reply = escape_md(reply_text)

    admin_text = (
        f"💬 *ОТВЕТ КЛИЕНТА В ТИКЕТЕ #{ticket_id}*\n"
        f"👤 Клиент: @{safe_username}\n"
        f"📄 *Сообщение:*\n"
        f"{safe_reply}"
    )

    for admin_id in ADMIN_CHATS:
        try:
            kb = types.InlineKeyboardMarkup()
            kb.add(
                types.InlineKeyboardButton(
                    "✏️ Ответить",
                    callback_data=f"admin_reply_ticket:{ticket_id}",
                )
            )
            kb.add(
                types.InlineKeyboardButton(
                    "✅ Закрыть",
                    callback_data=f"admin_close_ticket:{ticket_id}",
                )
            )

            bot.send_message(
                admin_id,
                admin_text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        except Exception as e:
            logger.error(
                "ticket.reply.notification_failed | ticket_id=%s | "
                "admin_id=%s | error=%s",
                ticket_id,
                admin_id,
                e,
            )


def process_ticket_description(message):
    cid = message.chat.id

    if message.text and message.text.lower() == "/cancel":
        draft = _ticket_drafts.get(cid, {})
        prompt_message_id = draft.get("prompt_message_id")

        if prompt_message_id:
            try:
                bot.edit_message_text(
                    "❌ Создание тикета отменено.",
                    cid,
                    prompt_message_id,
                )
            except Exception as e:
                logger.warning(
                    "ticket.creation.cancel_message_update_failed | "
                    "chat_id=%s | error=%s",
                    cid,
                    e,
                )

        bot.clear_step_handler_by_chat_id(cid)

        if cid in _ticket_drafts:
            del _ticket_drafts[cid]

        return

    description = message.text.strip()
    if not description:
        safe_send_message(
            bot,
            cid,
            "⚠️ Описание не может быть пустым. Попробуйте ещё раз или введите /cancel",
        )
        bot.register_next_step_handler(message, process_ticket_description)
        return

    topic = _ticket_drafts.get(cid, {}).get("topic", "Без темы")

    # Создание тикета полностью принадлежит ticket_service.
    username = message.from_user.username or f"user_{cid}"

    new_ticket = ticket_service.create_ticket(
        chat_id=cid,
        username=username,
        topic=topic,
        description=description,
    )

    if new_ticket is None:
        active_ticket = ticket_service.get_client_active_ticket(cid)
        active_ticket_id = active_ticket[0] if active_ticket else "неизвестен"

        if "_ticket_drafts" in globals() and cid in _ticket_drafts:
            del _ticket_drafts[cid]

        bot.clear_step_handler_by_chat_id(cid)

        safe_send_message(
            bot,
            cid,
            f"⚠️ У вас уже есть активный тикет #{active_ticket_id}.\n\n"
            "Сначала дождитесь его закрытия.",
        )
        return

    ticket_id = new_ticket["id"]

    # Убираем кнопки с сообщения, в котором вводилось описание.
    draft = _ticket_drafts.get(cid, {})
    prompt_message_id = draft.get("prompt_message_id")

    if prompt_message_id:
        try:
            safe_edit_message_reply_markup(
                bot,
                cid,
                prompt_message_id,
                reply_markup=None,
            )
        except Exception as e:
            logger.warning(
                "ticket.creation.cleanup_message_failed | "
                "ticket_id=%s | chat_id=%s | error=%s",
                ticket_id,
                cid,
                e,
            )

    # Очищаем черновик
    if "_ticket_drafts" in globals() and cid in _ticket_drafts:
        del _ticket_drafts[cid]
    bot.clear_step_handler_by_chat_id(cid)

    safe_send_message(
        bot,
        cid,
        (
            f"✅ *Тикет #{ticket_id} создан!*\n\n"
            "Администратор получил уведомление и скоро ответит вам."
        ),
        parse_mode="Markdown",
    )

    # Уведомляем админов.
    # Пользовательские данные обязательно экранируем для Markdown.
    safe_username = escape_md(str(message.from_user.username or cid))
    safe_topic = escape_md(str(topic))
    safe_description = escape_md(str(description))

    admin_text = (
        f"🆕 *НОВЫЙ ТИКЕТ #{ticket_id}*\n"
        f"👤 Клиент: @{safe_username}\n"
        f"📝 Тема: {safe_topic}\n"
        f"📄 *Описание:*\n"
        f"{safe_description}\n\n"
        f"Тикет готов к обработке."
    )

    for admin_id in ADMIN_CHATS:
        try:
            # Добавляем инлайн-кнопки для быстрого ответа админу
            kb = types.InlineKeyboardMarkup()
            kb.add(
                types.InlineKeyboardButton(
                    "✏️ Ответить",
                    callback_data=f"admin_reply_ticket:{ticket_id}",
                )
            )
            kb.add(
                types.InlineKeyboardButton(
                    "✅ Закрыть",
                    callback_data=f"admin_close_ticket:{ticket_id}",
                )
            )
            safe_send_message(
                bot,
                admin_id,
                admin_text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        except Exception as e:
            logger.error(
                "ticket.creation.notification_failed | "
                "ticket_id=%s | admin_id=%s | error=%s",
                ticket_id,
                admin_id,
                e,
            )
