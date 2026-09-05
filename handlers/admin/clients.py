"""
Обработчики работы с клиентами: списки, поиск, создание, QR, переименование.
"""

import os
import subprocess
import threading

from telebot import types

from config.paths import RU_GEO_CONF
from core.access import is_admin
from core.bot import bot
from core.callback_response import CallbackResponse
from core.navigation import (
    NAV_BACK_CALLBACK,
    NAV_CLIENTS_SEARCH_AWG_CALLBACK,
    NAV_CLIENTS_SEARCH_VLESS_CALLBACK,
    navigation,
)
from core.state import INPUT_REQUEST_MSGS
from services.client_service import delete_client as delete_client_service
from services.client_service import (
    get_users_list,
    rename_client,
    send_qr_or_conf,
)
from services.xray.config_manager import (
    get_vless_inbounds,
    load_xray_config,
)
from services.xray.link_generator import xray_get_link_for_port
from ui.keyboards import (
    client_card_kb,
    clients_menu_kb,
    main_menu_kb,
    protocol_list_kb,
)
from ui.messages import build_client_card
from utils.error_handler import handle_errors
from utils.helpers import escape_md, safe_delete
from utils.logger import logger
from utils.notifications import log_action
from utils.validators import validate_username


@handle_errors("Ошибка в handle_lists_delete_callback")
def handle_lists_delete_callback(bot, cid, call, data):
    """Обрабатывает callbacks удаления клиентов."""
    if data.startswith("ask_del:"):
        payload = data[8:]
        proto, username = payload.split(":", 1)
        kb_confirm = types.InlineKeyboardMarkup(row_width=2)
        kb_confirm.add(
            types.InlineKeyboardButton(
                "✅ Да, удалить", callback_data=f"confirm_del:{proto}:{username}"
            )
        )
        kb_confirm.add(
            types.InlineKeyboardButton(
                "↩️ Назад",
                callback_data=NAV_BACK_CALLBACK,
            )
        )
        bot.edit_message_text(
            (
                f"⚠️ *Вы уверены, что хотите безвозвратно удалить клиента?*\n"
                f"👤 Имя: `{escape_md(username)}`\n"
                f"📡 Протокол: {proto.upper()}\n"
                "❗ Это действие удалит конфигурацию и обнулит статистику."
            ),
            cid,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=kb_confirm,
        )
        return CallbackResponse()
    if data.startswith("confirm_del:"):
        callback_response = CallbackResponse("⏳ Удаляю...")
        payload = data[12:]
        proto, username = payload.split(":", 1)

        def delete_client():
            try:
                delete_client_service(username, proto)
                users = get_users_list(proto)
                kb = protocol_list_kb(proto, users) if users else main_menu_kb()

                log_action("УДАЛЕНИЕ", username, "SUCCESS", f"Protocol: {proto}")

                bot.edit_message_text(
                    f"✅ `{escape_md(username)}` успешно удалён",
                    cid,
                    call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=kb,
                )

            except Exception as e:
                bot.edit_message_text(
                    f"❌ {e}",
                    cid,
                    call.message.message_id,
                )

        bot.edit_message_text(
            f"⏳ Удаляю клиента `{escape_md(username)}`...",
            cid,
            call.message.message_id,
            parse_mode="Markdown",
        )

        threading.Thread(
            target=delete_client,
            daemon=True,
        ).start()

        return callback_response

    return False


def render_protocol_screen(bot, cid, message_id, proto):
    """Отрисовать список клиентов выбранного протокола."""
    try:
        users = get_users_list(proto)
    except Exception:
        logger.exception("admin_clients.list.failed | protocol=%s", proto)
        users = []

    text = f"📭 {proto.upper()} список пуст" if not users else "👥 Управление клиентами"

    kb = protocol_list_kb(proto, users)

    try:
        bot.edit_message_text(
            text,
            cid,
            message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            logger.exception("admin_clients.render.failed | protocol=%s", proto)
            return False

    return True


def _render_vless_screen(bot, cid, message_id):
    return render_protocol_screen(
        bot,
        cid,
        message_id,
        "vless",
    )


def _render_awg_screen(bot, cid, message_id):
    return render_protocol_screen(
        bot,
        cid,
        message_id,
        "awg",
    )


def handle_search_callback(bot, cid, call, data):
    """Обрабатывает поиск клиентов через навигационный callback."""
    search_protocols = {
        NAV_CLIENTS_SEARCH_VLESS_CALLBACK: "vless",
        NAV_CLIENTS_SEARCH_AWG_CALLBACK: "awg",
    }

    proto = search_protocols.get(data)
    if proto is None:
        return False

    search_kb = types.InlineKeyboardMarkup()
    search_kb.add(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        )
    )

    bot.edit_message_text(
        "🔍 Введите имя клиента для поиска:\n💡 Можно ввести часть имени.",
        cid,
        call.message.message_id,
        reply_markup=search_kb,
    )
    INPUT_REQUEST_MSGS[cid] = call.message.message_id
    bot.register_next_step_handler(
        call.message,
        process_search_input,
        proto,
    )
    return CallbackResponse()


def process_search_input(message, proto):
    """Обрабатывает ввод имени для поиска"""
    cid = message.chat.id
    if not is_admin(cid):
        return
    query = message.text.strip().lower()
    input_message_id = INPUT_REQUEST_MSGS.pop(cid, None)
    if input_message_id is not None:
        try:
            safe_delete(bot, cid, input_message_id)
        except Exception as e:
            logger.exception("admin_clients.operation.failed | error=%s", e)
    users = get_users_list(proto)
    filtered = [u for u in users if query in u.lower()]
    if filtered:
        bot.send_message(
            cid,
            f"🔍 Найдено {len(filtered)} клиентов:",
            reply_markup=protocol_list_kb(proto, filtered),
        )
    else:
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(
                "↩️ Назад",
                callback_data=NAV_BACK_CALLBACK,
            )
        )
        bot.send_message(
            cid, f"❌ Клиенты не найдены по запросу '{query}'", reply_markup=kb
        )


def handle_create_client_callback(bot, cid, call, data):
    """Обрабатывает создание клиентов: add_vless, add_awg"""
    if data in ["add_vless", "add_awg"]:
        proto = "VLESS" if data == "add_vless" else "AmneziaWG"
        bot.clear_step_handler_by_chat_id(cid)

        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(
                "↩️ Назад",
                callback_data=NAV_BACK_CALLBACK,
            )
        )

        bot.edit_message_text(
            (
                f"✏️ Введите имя пользователя {proto}:\n"
                "🔣 Только латиница: a-z\n"
                "🔢 Цифры и символы: 0-9 _ -\n"
                "👍 Пример: client_01, vpn-user"
            ),
            cid,
            call.message.message_id,
            reply_markup=kb,
        )

        INPUT_REQUEST_MSGS[cid] = call.message.message_id
        bot.register_next_step_handler(call.message, handle_add_input, data)
        return CallbackResponse()
    return False


def handle_add_input(message, add_type):
    if not is_admin(message.chat.id):
        return
    cid = message.chat.id
    if message.text and message.text.startswith("/"):
        from handlers.commands import cmd_start

        cmd_start(message)
        return
    username = message.text.strip()
    if not username:
        bot.send_message(cid, "❌ Пустое имя", reply_markup=main_menu_kb())
        return
    progress_msg = bot.send_message(cid, f"⏳ Создаю клиента {username}...")
    if add_type == "add_vless":
        logger.info(
            "admin_clients.add.started | protocol=vless | username=%s",
            username,
        )
        from services.xray.client_manager import xray_add_user

        proto, ok, res = "vless", *xray_add_user(username)
    elif add_type == "add_awg":
        logger.info("admin_clients.add.started | protocol=awg | username=%s", username)
        from services.awg.client_manager import awg_add_user

        proto, ok, res = "awg", *awg_add_user(username)
    else:
        safe_delete(bot, cid, progress_msg.message_id)
        bot.send_message(
            cid, "❌ Ошибка: неизвестный протокол", reply_markup=main_menu_kb()
        )
        return
    if not ok:
        safe_delete(bot, cid, progress_msg.message_id)
        bot.send_message(cid, res, reply_markup=main_menu_kb())
        return
    try:
        bot.clear_step_handler_by_chat_id(cid)
    except Exception as e:
        logger.exception("admin_clients.operation.failed | error=%s", e)

    input_message_id = INPUT_REQUEST_MSGS.pop(cid, None)
    if input_message_id is not None:
        safe_delete(bot, cid, input_message_id)

    log_action("СОЗДАНИЕ", username, "SUCCESS", f"Protocol: {proto}")
    safe_delete(bot, cid, progress_msg.message_id)
    bot.send_message(
        cid,
        build_client_card(username, proto),
        parse_mode="Markdown",
        reply_markup=client_card_kb(proto, username),
    )


def _render_rename_screen(bot, cid, message_id, error=None):
    """Отрисовать экран переименования клиента."""
    INPUT_REQUEST_MSGS[cid] = message_id

    text = (
        "✏️ *Смена имени клиента*\n\n"
        "Введите старое и новое имя через пробел:\n"
        "Пример: `client_01 client_02`"
    )

    if error:
        text = f"{error}\n\n{text}"

    bot.edit_message_text(
        text=text,
        chat_id=cid,
        message_id=message_id,
        parse_mode="Markdown",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(
                "↩️ Назад",
                callback_data=NAV_BACK_CALLBACK,
            )
        ),
    )

    bot.register_next_step_handler_by_chat_id(
        cid,
        process_rename_menu,
    )


def process_rename_menu(message):
    """Обработка переименования из меню списка"""
    if not is_admin(message.chat.id):
        return
    cid = message.chat.id
    input_message_id = INPUT_REQUEST_MSGS.get(cid)

    # Удаляем сообщение пользователя с введёнными именами.
    # Сам экран переименования (input_message_id) оставляем.
    safe_delete(bot, cid, message.message_id)

    args = message.text.strip().split()
    if len(args) != 2:
        error = "❌ Формат: `СтароеИмя НовоеИмя`"
        if input_message_id is not None:
            _render_rename_screen(bot, cid, input_message_id, error)
        else:
            bot.reply_to(message, error, parse_mode="Markdown")
        bot.register_next_step_handler_by_chat_id(cid, process_rename_menu)
        return
    old_name, new_name = args
    if not validate_username(new_name):
        error = "❌ Новое имя: только латиница, цифры, `_` или `-`"
        if input_message_id is not None:
            _render_rename_screen(bot, cid, input_message_id, error)
        else:
            bot.reply_to(message, error)
        bot.register_next_step_handler_by_chat_id(cid, process_rename_menu)
        return

    users_vless = get_users_list("vless")
    users_awg = get_users_list("awg")
    if old_name not in users_vless and old_name not in users_awg:
        error = f"❌ Клиент `{escape_md(old_name)}` не найден"
        if input_message_id is not None:
            _render_rename_screen(bot, cid, input_message_id, error)
        else:
            bot.reply_to(message, error, parse_mode="Markdown")
        bot.register_next_step_handler_by_chat_id(cid, process_rename_menu)
        return
    if any(new_name.lower() == u.lower() for u in users_vless) or any(
        new_name.lower() == u.lower() for u in users_awg
    ):
        error = f"❌ Имя `{escape_md(new_name)}` уже занято (без учёта регистра)"
        if input_message_id is not None:
            _render_rename_screen(bot, cid, input_message_id, error)
        else:
            bot.reply_to(message, error, parse_mode="Markdown")
        bot.register_next_step_handler_by_chat_id(cid, process_rename_menu)
        return

    INPUT_REQUEST_MSGS.pop(cid, None)

    progress_msg = bot.send_message(
        cid,
        f"🔄 Переименовываю `{escape_md(old_name)}` → `{escape_md(new_name)}`...",
        parse_mode="Markdown",
    )

    errors = rename_client(old_name, new_name)

    safe_delete(bot, cid, progress_msg.message_id)

    if errors:
        bot.send_message(message.chat.id, "⚠️ Частично выполнено:\n" + "\n".join(errors))
    else:
        log_action("ПЕРЕИМЕНОВАНИЕ", f"{old_name}->{new_name}", "SUCCESS")

        # Старое окно переименования превращаем в SUCCESS.
        # Новое сообщение с меню отправляем после него,
        # поэтому SUCCESS визуально находится выше меню.
        if input_message_id is not None:
            bot.edit_message_text(
                f"✅ Успешно переименовано: {old_name} → {new_name}",
                cid,
                input_message_id,
            )

        navigation.back(cid)

        bot.send_message(
            cid,
            "👥 *Клиенты*",
            parse_mode="Markdown",
            reply_markup=clients_menu_kb(),
        )


@handle_errors("Ошибка в handle_qr_config_callback")
def handle_qr_config_callback(bot, cid, call, data):
    """Обрабатывает QR/Конфиги."""

    # --------------------------------------------------------
    # Выбор VLESS QR по порту
    # Формат:
    # qr_select_USERNAME_443
    # qr_select_USERNAME_2096
    # qr_select_USERNAME_both
    # --------------------------------------------------------
    if data.startswith("qr_select_"):
        payload = data[len("qr_select_") :]

        if payload.endswith("_both"):
            username = payload[:-5]
            port_choice = "both"
        elif "*" in payload:
            username, port_choice = payload.rsplit("*", 1)
            if not port_choice.isdigit():
                raise ValueError("Invalid QR port")
        else:
            username = payload
            port_choice = "both"

        config = load_xray_config()
        vless_inbounds = get_vless_inbounds(config)

        if port_choice == "both":
            ports = [
                int(inbound["port"])
                for inbound in vless_inbounds
                if inbound.get("port")
            ]
        else:
            ports = [int(port_choice)]

        for index, port in enumerate(ports):
            link = xray_get_link_for_port(username, port)

            if not link:
                continue

            qr_path = f"/tmp/{username}_qr_{port}.png"

            try:
                subprocess.run(
                    ["qrencode", "-o", qr_path, link],
                    check=True,
                )

                caption = f"🗺️ *QR-код для {escape_md(username)}*\n"

                if index == 0:
                    caption += "📱 Оператор: MTS/Megafon/Tele2\n"
                    caption += "🎯 Zver_VPS для своих c 💝"
                elif index == 1:
                    caption += "🐝 Оператор: Beeline\n"
                    caption += "🎯 Zver_VPS для своих c 💘"
                else:
                    caption += f"📱 VLESS:{port}\n"
                    caption += "🎯 Zver_VPS для своих c 💘"

                with open(qr_path, "rb") as photo:
                    bot.send_photo(
                        cid,
                        photo,
                        caption=caption,
                    )
            finally:
                if os.path.exists(qr_path):
                    os.remove(qr_path)

        return CallbackResponse()

    # --------------------------------------------------------
    # Единый QR callback
    # qr:proto:username
    # --------------------------------------------------------
    if data.startswith("qr:"):
        parts = data.split(":", 2)

        if len(parts) != 3:
            return CallbackResponse("❌ Некорректный QR callback")

        _, proto, username = parts

        if proto not in ("vless", "awg"):
            return CallbackResponse("❌ Неизвестный протокол")

        callback_response = CallbackResponse(f"📤 Отправляю для {escape_md(username)}")

        send_qr_or_conf(
            bot,
            cid,
            username,
            proto,
        )
        return callback_response

    # --------------------------------------------------------
    # Единый CONF callback
    # conf:proto:username
    # --------------------------------------------------------
    if data.startswith("conf:"):
        parts = data.split(":", 2)

        if len(parts) != 3:
            return CallbackResponse("❌ Некорректный config callback")

        _, proto, username = parts

        if proto not in ("vless", "awg"):
            return CallbackResponse("❌ Неизвестный протокол")

        callback_response = CallbackResponse(
            f"📄 Отправляю конфиг для {escape_md(username)}"
        )

        send_qr_or_conf(
            bot,
            cid,
            username,
            proto,
            config_only=(proto == "vless"),
        )

        # Для VLESS вместе с конфигурацией отправляем правила RU.
        if proto == "vless" and os.path.isfile(RU_GEO_CONF):
            with open(RU_GEO_CONF, "rb") as f:
                bot.send_document(
                    cid,
                    f,
                    caption=(
                        "📋 *Правила маршрутизации для 🚀 Shadowrocket*\n\n"
                        "💡 *Как применить:*\n"
                        "1️⃣ Скачайте файл 👆 на 📱 телефон\n"
                        "2️⃣ Откройте 🚀 Shadowrocket\n"
                        "3️⃣ Перейдите: ⚙️ *Маршрутизация* → *Настройка*\n"
                        "4️⃣ Откройте: 📂 *Настройка* → *Импортировать...*\n"
                        "5️⃣ Выберите этот файл (🟠 точка)\n\n"
                        "🎉 *Готово!*\n"
                        "🇷🇺 Ru-сайты идут напрямую,\n"
                        "🌐 остальной трафик — через туннель"
                    ),
                    parse_mode="Markdown",
                )

        return callback_response
    return False
