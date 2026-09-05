"""
Обработчики команд бота:
/start, /rename, /bind, /unbind, /pending, /history, /my_id, /status
"""

from datetime import datetime

from telebot import types

from config.secrets import ADMIN_CHATS
from core.access import is_admin, is_client
from core.bot import bot
from core.navigation import navigation
from core.state import (
    LAST_CLIENT_MENU_MSGS,
    LAST_MAIN_MENU_MSGS,
    LAST_MY_ID_ADMIN_MSGS,
    LAST_MY_ID_MSGS,
)
from services.bindings import (
    add_client_binding,
    add_pending_binding,
    get_client_bindings,
    get_pending_bindings,
    remove_client_binding,
)
from services.client_service import (
    get_client_protocol,
    get_users_list,
    rename_client,
    show_history_action,
)
from services.stats import get_status_text
from ui.client_menu import get_client_menu
from ui.keyboards import (
    main_menu_kb,
)
from ui.screens import ADMIN_HOME, CLIENT_HOME
from utils.formatters import get_help_text
from utils.helpers import escape_md, safe_delete
from utils.logger import logger
from utils.notifications import log_action
from utils.validators import validate_chat_id, validate_username


@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    try:
        bot.clear_step_handler_by_chat_id(message.chat.id)
    except Exception as e:
        logger.exception("commands.start.clear_step_handler_failed | error=%s", e)

    if is_admin(message.chat.id):
        cid = message.chat.id
        navigation.start(cid, ADMIN_HOME)
        if cid in LAST_MAIN_MENU_MSGS:
            safe_delete(bot, cid, LAST_MAIN_MENU_MSGS[cid])
        msg = bot.send_message(
            cid, get_help_text(), parse_mode="Markdown", reply_markup=main_menu_kb()
        )
        LAST_MAIN_MENU_MSGS[cid] = msg.message_id
    elif is_client(message.chat.id):
        cid = message.chat.id

        # /start всегда начинает новую клиентскую навигацию
        # с корневого экрана — по той же схеме, что и админское меню.
        navigation.start(cid, CLIENT_HOME)

        if cid in LAST_CLIENT_MENU_MSGS:
            safe_delete(bot, cid, LAST_CLIENT_MENU_MSGS[cid])

        kb, text, markdown = get_client_menu(cid)

        parse_mode = "Markdown" if markdown else None
        msg = bot.send_message(
            cid,
            text,
            parse_mode=parse_mode,
            reply_markup=kb,
        )
        LAST_CLIENT_MENU_MSGS[cid] = msg.message_id
    else:
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton(
                "🔒 Запросить привязку", callback_data="request_bind"
            )
        )
        bot.send_message(
            message.chat.id,
            "🔒 Доступ ограничен.\nНажмите кнопку ниже.",
            reply_markup=kb,
        )


@bot.message_handler(commands=["rename"])
def cmd_rename(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split()[1:]
    if len(args) != 2:
        bot.reply_to(message, "Использование: /rename СтароеИмя НовоеИмя")
        return
    old_name, new_name = args
    if not validate_username(new_name):
        bot.reply_to(
            message, "❌ Новое имя должно содержать только латиницу, цифры, _ или -"
        )
        return
    users_vless = get_users_list("vless")
    users_awg = get_users_list("awg")
    if old_name not in users_vless and old_name not in users_awg:
        bot.reply_to(message, f"❌ Клиент {old_name} не найден")
        return
    if new_name in users_vless or new_name in users_awg:
        bot.reply_to(message, f"❌ Имя {new_name} уже занято")
        return
    bot.reply_to(message, f"Переименовываю {old_name} -> {new_name}...")
    errors = rename_client(old_name, new_name)
    if errors:
        bot.send_message(
            message.chat.id, "⚠️ Частично выполнено. Ошибки:\n" + "\n".join(errors)
        )
    else:
        log_action("ПЕРЕИМЕНОВАНИЕ", f"{old_name}->{new_name}", "SUCCESS")
        bot.send_message(
            message.chat.id,
            (
                f"✅ Успешно переименовано: {old_name} -> {new_name}\n"
                " Службы перезапущены, трафик сохранён."
            ),
        )


@bot.message_handler(commands=["pending"])
def cmd_pending(message):
    if not is_admin(message.chat.id):
        return
    pending = get_pending_bindings()
    if not pending:
        bot.reply_to(message, "📭 Ожидающих заявок нет.")
        return
    text = " **ОЖИДАЮЩИЕ ЗАЯВКИ:**\n"
    for cid, info in pending.items():
        text += (
            f" {escape_md(info['name'])} |  `{cid}` | 🕒 {escape_md(info['time'])}\n"
        )
    kb = types.InlineKeyboardMarkup(row_width=1)
    for cid in pending:
        kb.add(
            types.InlineKeyboardButton(
                f"✅ Привязать {pending[cid]['name']}",
                callback_data=f"approve_bind_{cid}",
            )
        )
    bot.reply_to(message, text, reply_markup=kb)


@bot.message_handler(commands=["status"])
def cmd_status(message):
    if not is_admin(message.chat.id):
        return
    bot.send_message(message.chat.id, get_status_text(), parse_mode="Markdown")


@bot.message_handler(commands=["history"])
def cmd_history(message):
    if not is_admin(message.chat.id):
        return
    show_history_action(bot, message.chat.id)


def get_client_accounts_by_chat(cid: int) -> dict:
    """
    Возвращает аккаунты клиента, сгруппированные по протоколам.
    Формат: {'xray': ['Zver', 'Zver1'], 'awg': ['ZverAWG']}
    """
    usernames = get_client_bindings(str(cid))

    if not usernames:
        return {"xray": [], "awg": []}

    result = {"xray": [], "awg": []}

    for username in usernames:
        proto = get_client_protocol(username)

        if proto == "vless":
            result["xray"].append(username)
        elif proto == "awg":
            result["awg"].append(username)

    return result


@bot.message_handler(commands=["my_id"])
def cmd_my_id(message):

    cid = message.chat.id

    # удаляем старое сообщение /my_id
    if cid in LAST_MY_ID_MSGS:
        try:
            safe_delete(bot, cid, LAST_MY_ID_MSGS[cid])
        except Exception as e:
            logger.exception(
                "commands.my_id.delete_message_failed | chat_id=%s | "
                "message_id=%s | error=%s",
                cid,
                LAST_MY_ID_MSGS[cid],
                e,
            )

    # удаляем старые уведомления администраторов с кнопками
    old_admin_msgs = LAST_MY_ID_ADMIN_MSGS.pop(cid, {})
    for admin_chat_id, message_id in old_admin_msgs.items():
        try:
            safe_delete(bot, admin_chat_id, message_id)
        except Exception as e:
            logger.exception(
                "commands.my_id.delete_admin_message_failed | chat_id=%s | "
                "message_id=%s | error=%s",
                admin_chat_id,
                message_id,
                e,
            )

    # если уже клиент
    if is_client(cid):
        accounts = get_client_accounts_by_chat(cid)

        # Формируем список аккаунтов по протоколам
        accounts_text = ""
        if accounts["xray"] or accounts["awg"]:
            accounts_text = "\n📱 Ваши аккаунты:"

            if accounts["xray"]:
                accounts_text += "\n🚀 Xray : " + ", ".join(accounts["xray"])

            if accounts["awg"]:
                accounts_text += "\n🛡️ AmneziaWG: " + ", ".join(accounts["awg"])

        msg = bot.send_message(
            cid, f"✅ Вы уже привязаны!\n🆔 Ваш chat_id: {cid}{accounts_text}"
        )

    else:
        msg = bot.send_message(
            cid,
            (
                f"🆔 Ваш chat_id: {cid}\n"
                "Заявка на привязку отправлена администратору. Ожидайте подтверждения."
            ),
        )

        user_info = (
            f"@{message.from_user.username}"
            if message.from_user.username
            else message.from_user.first_name
        )

        pending_time = datetime.now().strftime("%d.%m %H:%M")
        add_pending_binding(str(cid), user_info, pending_time)
        pending = get_pending_bindings()

        kb = types.InlineKeyboardMarkup(row_width=2)

        kb.add(
            types.InlineKeyboardButton(
                f"✅ Привязать {user_info}",
                callback_data=f"approve_bind_{cid}",
            ),
            types.InlineKeyboardButton(
                f"❌ Отклонить {user_info}",
                callback_data=f"reject_bind_{cid}",
            ),
        )

        admin_msg = (
            f"🔗 Запрос на привязку\n"
            f"👤 {user_info}\n"
            f"🆔 Chat ID: {cid}\n"
            f"🕒 {pending[str(cid)]['time']}"
        )

        admin_messages = {}
        for admin_chat in ADMIN_CHATS:
            try:
                admin_msg_obj = bot.send_message(
                    admin_chat,
                    admin_msg,
                    reply_markup=kb,
                )
                admin_messages[admin_chat] = admin_msg_obj.message_id
            except Exception as e:
                print("ADMIN TG ERROR:", e)

        if admin_messages:
            LAST_MY_ID_ADMIN_MSGS[cid] = admin_messages

    LAST_MY_ID_MSGS[cid] = msg.message_id


@bot.message_handler(commands=["bind"])
def cmd_bind(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split()[1:]
    if len(args) != 2:
        bot.reply_to(message, "Использование: /bind <username> <chat_id>")
        return
    username, chat_id = args
    if not validate_username(username):
        bot.reply_to(message, "❌ Некорректное имя пользователя")
        return
    if not validate_chat_id(chat_id):
        bot.reply_to(message, "❌ chat_id должен состоять только из цифр")
        return
    users_vless = get_users_list("vless")
    users_awg = get_users_list("awg")
    if username not in users_vless and username not in users_awg:
        bot.reply_to(message, f"❌ Клиент `{username}` не найден")
        return
    binding_result = add_client_binding(chat_id, username)

    if binding_result == "limit":
        bot.reply_to(
            message,
            (
                "️ Превышен лимит привязок (4 аккаунта на один Telegram-аккаунт). "
                f"Используйте /unbind {chat_id} <username> "
                "для удаления старой привязки."
            ),
        )
        return

    if binding_result == "duplicate":
        bot.reply_to(message, f"️ Клиент `{username}` уже привязан к этому chat_id.")
        return
    log_action("ПРИВЯЗКА", username, "SUCCESS", f"chat_id: {chat_id}")
    bot.reply_to(
        message, f"✅ Клиент `{username}` успешно привязан к chat_id `{chat_id}`"
    )
    try:
        bot.send_message(
            chat_id,
            (
                f"✅ Ваш аккаунт `{username}` успешно привязан!\n"
                "Теперь вы можете использовать команду /start "
                "для доступа к личному меню."
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.exception(
            "commands.bind.send_failed | chat_id=%s | error=%s",
            chat_id,
            e,
        )


@bot.message_handler(commands=["unbind"])
def cmd_unbind(message):
    if not is_admin(message.chat.id):
        return
    args = message.text.split()[1:]
    if len(args) != 2:
        bot.reply_to(message, "Использование: /unbind <chat_id> <username>")
        return
    chat_id, username = args
    removal_result = remove_client_binding(chat_id, username)
    if removal_result:
        log_action("ОТВЯЗКА", username, "SUCCESS", f"chat_id: {chat_id}")
        bot.reply_to(
            message,
            f"✅ Привязка для `{username}` (chat_id: `{chat_id}`) удалена.",
        )
    else:
        bot.reply_to(message, "❌ Привязка не найдена.")
