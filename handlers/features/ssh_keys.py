"""
Обработчики подменю SSH-ключей.
"""

import os
import subprocess

from telebot import types

from config.paths import SSH_AUTHORIZED_KEYS
from core.callback_response import CallbackResponse
from core.navigation import NAV_BACK_CALLBACK, navigation
from services.ssh_keys import (
    SSH_KEY_MAP,
    delete_ssh_key,
    get_authorized_keys_path,
    get_ssh_history,
    get_ssh_keys_list,
    get_ssh_status,
)
from ui.keyboards import ssh_menu_kb
from ui.screens import (
    SSH_DELETE,
    SSH_HISTORY,
    SSH_LIST,
    SSH_MENU,
)
from utils.error_handler import handle_errors
from utils.helpers import safe_edit_message
from utils.logger import logger
from utils.notifications import log_action


@handle_errors("Ошибка в handle_ssh_callback")
def render_ssh_menu(bot, cid, message_id):
    """Отрисовать главное меню SSH."""
    return safe_edit_message(
        bot,
        get_ssh_status(),
        cid,
        message_id,
        parse_mode="Markdown",
        reply_markup=ssh_menu_kb(),
    )


def _back_keyboard():
    """Клавиатура экрана с возвратом."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("↩️ Назад", callback_data=NAV_BACK_CALLBACK),
    )
    return kb


def render_ssh_list(bot, cid, message_id):
    """Отрисовать список SSH-ключей."""
    text = get_ssh_keys_list()
    return safe_edit_message(
        bot,
        text,
        cid,
        message_id,
        parse_mode="Markdown",
        reply_markup=_back_keyboard(),
    )


def render_ssh_history(bot, cid, message_id):
    """Отрисовать историю SSH."""
    text = get_ssh_history(limit=10)
    return safe_edit_message(
        bot,
        text,
        cid,
        message_id,
        parse_mode="Markdown",
        reply_markup=_back_keyboard(),
    )


def render_ssh_delete(bot, cid, message_id):
    """Отрисовать экран выбора SSH-ключа для удаления."""
    try:
        result = subprocess.run(
            ["ssh-keygen", "-lf", SSH_AUTHORIZED_KEYS],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout.strip()

        if not output:
            return safe_edit_message(
                bot,
                "🔑 SSH-ключи для удаления не найдены.",
                cid,
                message_id,
                reply_markup=ssh_menu_kb(),
            )

        kb = types.InlineKeyboardMarkup(row_width=1)
        for line in output.split("\n"):
            parts = line.split()
            if len(parts) >= 3:
                comment = parts[2]
                key_info = SSH_KEY_MAP.get(parts[1], {"name": comment, "emoji": "🔑"})
                kb.add(
                    types.InlineKeyboardButton(
                        f"🗑️ {key_info['emoji']} {key_info['name']}",
                        callback_data=f"ssh_delete_confirm_{comment}",
                    )
                )

        kb.add(
            types.InlineKeyboardButton(
                "↩️ Назад",
                callback_data=NAV_BACK_CALLBACK,
            )
        )
        return safe_edit_message(
            bot,
            (
                "🗑️ *Удаление SSH-ключа*\n"
                "Выберите ключ для удаления:\n"
                "⚠️ Действие необратимо!"
            ),
            cid,
            message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )
    except Exception as e:
        return safe_edit_message(
            bot,
            f"❌ Ошибка: {e}",
            cid,
            message_id,
        )


@handle_errors("Ошибка в handle_ssh_callback")
def handle_ssh_callback(bot, cid, call, data):
    """Обрабатывает действия SSH-ключей."""
    try:
        screens = {
            "ssh_menu": (SSH_MENU, None),
            "ssh_list": (SSH_LIST, "Загружаю список ключей..."),
            "ssh_history": (SSH_HISTORY, "Загружаю историю..."),
            "ssh_delete": (SSH_DELETE, None),
        }

        if data in screens:
            screen_id, notice = screens[data]

            # Повторный callback текущего экрана не должен повторно
            # редактировать сообщение: Telegram вернёт 400 message is not modified.
            if navigation.current(cid) == screen_id:
                return CallbackResponse(notice)

            navigation.go(cid, screen_id)
            navigation.render(screen_id, bot, cid, call.message.message_id)
            return CallbackResponse(notice)

        if data.startswith("ssh_delete_confirm_"):
            comment = data.replace("ssh_delete_confirm_", "")
            key_info = SSH_KEY_MAP.get("", {"name": comment, "emoji": "🔑"})
            for _fp, info in SSH_KEY_MAP.items():
                if info["name"] == comment:
                    key_info = info
                    break
            kb = types.InlineKeyboardMarkup(row_width=2)
            kb.add(
                types.InlineKeyboardButton(
                    "🔴 УДАЛИТЬ", callback_data=f"ssh_delete_final_{comment}"
                ),
                types.InlineKeyboardButton("❌ Отмена", callback_data="ssh_delete"),
            )
            bot.edit_message_text(
                (
                    "⚠️ *Удаление SSH-ключа*\n"
                    "Вы собираетесь удалить:\n"
                    f"🔑 *{key_info['name']}*\n"
                    f"📍 {key_info['desc']}\n"
                    "Это действие необратимо!\n"
                    "💾 Будет создан автоматический бэкап."
                ),
                cid,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=kb,
            )
            return CallbackResponse()

        if data.startswith("ssh_delete_final_"):
            comment = data.replace("ssh_delete_final_", "")
            ok, result = delete_ssh_key(comment)
            kb = types.InlineKeyboardMarkup(row_width=1)
            kb.add(
                types.InlineKeyboardButton("↩️ Назад", callback_data=NAV_BACK_CALLBACK)
            )
            bot.edit_message_text(
                result,
                cid,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=kb,
            )
            if ok:
                log_action("УДАЛЕНИЕ SSH-КЛЮЧА", comment, "SUCCESS")
            return CallbackResponse("Удаляю ключ...")

        if data == "ssh_export":
            auth_keys = get_authorized_keys_path()
            if os.path.exists(auth_keys):
                with open(auth_keys, "rb") as f:
                    bot.send_document(
                        cid,
                        f,
                        caption=(
                            " *authorized_keys*\n"
                            "Файл SSH-ключей доступа.\n"
                            "⚠️ Храните в безопасном месте!"
                        ),
                        parse_mode="Markdown",
                    )
                try:
                    navigation.go(cid, SSH_MENU)
                    navigation.render(
                        SSH_MENU,
                        bot,
                        cid,
                        call.message.message_id,
                    )
                except Exception as e:
                    logger.error(
                        "ssh.handler.navigation_failed | error=%s",
                        e,
                    )
            else:
                bot.edit_message_text(
                    "❌ Файл authorized_keys не найден", cid, call.message.message_id
                )
            return CallbackResponse("Отправляю файл...")

    except Exception as e:
        err_text = str(e)
        if "message is not modified" not in err_text and not (
            "400" in err_text and "message" in err_text.lower()
        ):
            logger.error(
                "ssh.handler.callback_failed | error=%s",
                e,
            )
    return False
