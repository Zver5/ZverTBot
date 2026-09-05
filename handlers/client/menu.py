"""
Обработчики клиентских функций.
"""

import contextlib
import os
import threading
from datetime import datetime

from telebot import types

from config.paths import RU_GEO_CONF
from config.secrets import ADMIN_CHATS
from core.access import is_admin, is_client
from core.callback_response import CallbackResponse
from core.navigation import NAV_CLIENT_BACK_CALLBACK
from services.bindings import (
    add_pending_binding,
    get_client_bindings,
    get_pending_bindings,
)
from services.client_service import (
    get_client_protocol,
    get_users_list,
    send_qr_or_conf,
)
from services.stats import get_client_stats_text
from ui.client_menu import (
    get_client_account_screen,
    get_client_menu,
)
from utils.helpers import (
    escape_md,
    safe_delete,
    safe_edit_message,
    safe_send_document,
    safe_send_message,
)
from utils.logger import logger


def render_client_home(bot, cid, message_id):
    """Отрисовать главное меню клиента."""
    kb, text, _ = get_client_menu(cid)

    safe_edit_message(
        bot,
        text,
        cid,
        message_id,
        parse_mode="Markdown",
        reply_markup=kb,
    )
    return True


def render_client_account(bot, cid, message_id, username):
    """Отрисовать экран конкретного аккаунта."""
    screen = get_client_account_screen(username)

    if screen is None:
        safe_send_message(
            bot,
            cid,
            "❌ Клиент не найден.",
        )
        return False

    kb, text, _ = screen

    safe_edit_message(
        bot,
        text,
        cid,
        message_id,
        parse_mode="Markdown",
        reply_markup=kb,
    )
    return True


def render_client_help(bot, cid, message_id):
    client_list = get_client_bindings(str(cid))
    if not isinstance(client_list, list):
        client_list = [client_list] if client_list else []

    users_vless = get_users_list("vless")
    users_awg = get_users_list("awg")

    has_vless = any(acc in users_vless for acc in client_list)
    has_awg = any(acc in users_awg for acc in client_list)

    text = "📖 *ИНСТРУКЦИЯ ПО ПОДКЛЮЧЕНИЮ*\n\n"

    if has_vless:
        text += "🚀 Протокол *VLESS+Xray*\n"
        text += (
            "*Приложение:* Shadowrocket / Hidiify\n"
            "*Установка:* App Store или Google Play.\n\n"
        )
        text += (
            "1️⃣ Откройте свой аккаунт и нажмите *«QR-код»*.\n"
            "2️⃣ Отсканируйте QR-код в Shadowrocket / Hidiify: "
            "*«+»* → импорт через QR-код.\n"
            "3️⃣ Если используете *ссылку VLESS*, скопируйте ссылку "
            "из сообщения с конфигурацией и импортируйте её в "
            "Shadowrocket / Hidiify.\n"
            "4️⃣ Для корректной маршрутизации нажмите "
            "*«Конфигурация + RU»*, скачайте файл *ru_geo.conf* "
            "и импортируйте его в Shadowrocket / Hidiify.\n"
            "5️⃣ Готово — выберите профиль и включите VPN.\n\n"
        )

    if has_awg:
        text += "🛡 Протокол *AmneziaWG*\n"
        text += "*Приложение:* AmneziaWG\n*Установка:* App Store или Google Play.\n\n"
        text += (
            "1️⃣ Откройте свой аккаунт и нажмите *«QR-код»*.\n"
            "2️⃣ Отсканируйте QR-код в Amnezia VPN: "
            "*«+»* → *«Импортировать»*.\n"
            "3️⃣ Также можно импортировать полученный *файл конфигурации*.\n"
            "4️⃣ Готово — выберите подключение и включите VPN.\n\n"
        )

    text += "💡 Если возникли проблемы — создайте тикет, и администратор вам ответит."

    kb_help = types.InlineKeyboardMarkup(row_width=2)
    kb_help.add(
        types.InlineKeyboardButton(
            "🆘 Создать тикет",
            callback_data="create_ticket",
        ),
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_CLIENT_BACK_CALLBACK,
        ),
    )

    safe_edit_message(
        bot,
        text,
        cid,
        message_id,
        parse_mode="Markdown",
        reply_markup=kb_help,
    )
    return True


def handle_client_conf(bot, cid, call, data):
    username = data.split(":", 2)[2]

    proto = get_client_protocol(username)
    if proto is None:
        safe_send_message(
            bot,
            cid,
            "❌ Клиент не найден.",
        )
        return CallbackResponse()

    send_qr_or_conf(bot, cid, username, proto)

    return CallbackResponse()


def handle_request_bind(bot, cid, call, data):
    if is_admin(cid):
        return CallbackResponse("Вы администратор!")

    if is_client(cid):
        safe_send_message(
            bot,
            cid,
            f"✅ Ваш chat_id: {cid}\nВы уже привязаны к клиенту.",
        )
        return CallbackResponse("Вы уже привязаны!")

    user_info = (
        f"@{call.from_user.username}"
        if call.from_user.username
        else call.from_user.first_name
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
    msg = (
        f"🔗 Запрос на привязку\n{escape_md(user_info)}\n"
        f"🆔 Chat ID: {cid}\n🕒 {pending[str(cid)]['time']}"
    )
    for admin_chat in ADMIN_CHATS:
        safe_send_message(
            bot,
            admin_chat,
            msg,
            parse_mode="Markdown",
            reply_markup=kb,
        )
    safe_send_message(
        bot,
        cid,
        "✅ Ваш chat_id: "
        f"{cid}\nЗаявка на привязку отправлена администратору. "
        "Ожидайте подтверждения.",
    )
    return CallbackResponse("Заявка отправлена администратору!")


def handle_client_conf_ru(bot, cid, call, data):
    username = data.split(":", 2)[2]

    with contextlib.suppress(Exception):
        safe_delete(bot, cid, call.message.message_id)

    try:
        # Используем ту же проверенную логику отправки VLESS,
        # что и административное меню.
        send_qr_or_conf(
            bot,
            cid,
            username,
            "vless",
            config_only=True,
        )

        # Отправляем правила RU.
        if os.path.exists(RU_GEO_CONF):
            with open(RU_GEO_CONF, "rb") as f:
                safe_send_document(
                    bot,
                    cid,
                    f,
                    caption=(
                        "📋 *Правила маршрутизации для Shadowrocket*\n\n"
                        "💡 *Как применить:*\n"
                        "1️⃣ Скачайте файл 👆 на телефон\n"
                        "2️⃣ Откройте Shadowrocket\n"
                        "3️⃣ ⚙️ Перейдите: *Маршрутизация* → *Настройка*\n"
                        "4️⃣ 📂 Откройте: *Настройка* → *Импортировать...*\n"
                        "5️⃣ Выберите файл (🟠 точка)\n\n"
                        "🎉 *Готово!*\n"
                        "🇷🇺 Ru-сайты идут напрямую,\n"
                        "🌐 остальной трафик — через туннель"
                    ),
                    parse_mode="Markdown",
                )

    except Exception as e:
        logger.exception("client.config.send_failed | error=%s", e)
        safe_send_message(
            bot,
            cid,
            "❌ Ошибка отправки конфигурации.",
        )

    return CallbackResponse()


def handle_client_stats(bot, cid, call, data):
    username = data.split(":", 2)[2]

    proto = get_client_protocol(username)

    if proto is None:
        return CallbackResponse("❌ Клиент не найден")

    def _send_client_stats():
        try:
            text = get_client_stats_text(username, proto)
            kb = types.InlineKeyboardMarkup()
            kb.add(
                types.InlineKeyboardButton(
                    "↩️ Назад", callback_data=f"client:account:{username}"
                )
            )
            safe_edit_message(
                bot,
                text,
                cid,
                call.message.id,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        except Exception as e:
            logger.exception(
                "client.stats.failed | username=%s | error=%s",
                username,
                e,
            )
            safe_edit_message(
                bot,
                f"❌ Ошибка получения статистики: {e}",
                cid,
                call.message.id,
            )

    threading.Thread(target=_send_client_stats, daemon=True).start()

    return CallbackResponse()
