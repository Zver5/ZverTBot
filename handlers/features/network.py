"""
handlers/features/network.py
Обработчик сетевых инструментов: MTR диагностика.
"""

import asyncio
import shutil
import threading

from telebot import types

from config import SERVER_IP
from core.callback_response import CallbackResponse
from core.navigation import NAV_BACK_CALLBACK, navigation
from services.network.mtr import diagnose
from ui.screens import NET_MTR
from utils.error_handler import handle_errors
from utils.logger import logger


def render_net_mtr(bot, cid, message_id):
    """Отрисовать экран выбора цели для MTR."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            "🎯 8.8.8.8 (Google DNS)", callback_data="mtr_target_8.8.8.8"
        )
    )
    kb.add(
        types.InlineKeyboardButton(
            "🎯 1.1.1.1 (Cloudflare)", callback_data="mtr_target_1.1.1.1"
        )
    )
    kb.add(
        types.InlineKeyboardButton(
            f"🎯 {SERVER_IP} (Этот VPS)", callback_data=f"mtr_target_{SERVER_IP}"
        )
    )
    kb.add(types.InlineKeyboardButton("↩️ Назад", callback_data=NAV_BACK_CALLBACK))
    bot.edit_message_text(
        "📡 *MTR диагностика*\n\nВыберите цель или введите IP/домен:",
        cid,
        message_id,
        parse_mode="Markdown",
        reply_markup=kb,
    )

    bot.register_next_step_handler_by_chat_id(cid, process_mtr_input, bot, cid)


@handle_errors("Ошибка в handle_network_callback")
def handle_network_callback(bot, cid, call, data):
    """Обрабатывает callback'и сетевых инструментов."""

    if data == "net_mtr":
        if navigation.current(cid) != NET_MTR:
            navigation.go(cid, NET_MTR)
        navigation.render(NET_MTR, bot, cid, call.message.message_id)
        return CallbackResponse()

    if data.startswith("mtr_target_"):
        target = data.replace("mtr_target_", "")

        bot.answer_callback_query(
            call.id,
            "📡 MTR запущен",
        )

        bot.edit_message_text(
            f"📡 Запуск MTR для `{target}`...\n⏳ Ожидание ~25 сек...",
            cid,
            call.message.message_id,
            parse_mode="Markdown",
        )

        _run_mtr(bot, cid, call.message.message_id, target)
        return CallbackResponse()

    return False


def process_mtr_input(message, bot, cid):
    """Обрабатывает текстовый ввод цели для MTR"""
    target = message.text.strip()
    if not target or len(target) < 3:
        bot.send_message(cid, "❌ Некорректный ввод. Попробуйте ещё раз:")
        return

    # Запускаем MTR
    msg = bot.send_message(
        cid,
        f"📡 Запуск MTR для `{target}`...\n⏳ Ожидание ~25 сек...",
        parse_mode="Markdown",
    )
    _run_mtr(bot, cid, msg.message_id, target)


def _run_mtr(bot, cid, message_id, target):
    """Запускает MTR в отдельном потоке (asyncio внутри threading)"""

    def _worker():
        try:
            # Проверка что mtr установлен
            if not shutil.which("mtr"):
                kb = types.InlineKeyboardMarkup()
                kb.add(
                    types.InlineKeyboardButton(
                        "↩️ Назад", callback_data=NAV_BACK_CALLBACK
                    )
                )
                bot.edit_message_text(
                    (
                        "❌ MTR не установлен на сервере\n\n"
                        "Установите: apt install mtr-tiny"
                    ),
                    cid,
                    message_id,
                    reply_markup=kb,
                )
                return

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(diagnose(target))
            loop.close()

            kb = types.InlineKeyboardMarkup(row_width=1)
            kb.add(
                types.InlineKeyboardButton(
                    "↩️ Назад",
                    callback_data=NAV_BACK_CALLBACK,
                )
            )
            bot.edit_message_text(
                result, cid, message_id, parse_mode="HTML", reply_markup=kb
            )
        except Exception as e:
            logger.error("network.mtr.failed | error=%s", e)
            kb = types.InlineKeyboardMarkup()
            kb.add(
                types.InlineKeyboardButton("↩️ Назад", callback_data=NAV_BACK_CALLBACK)
            )
            bot.edit_message_text(
                f"❌ Ошибка MTR: {str(e)[:200]}", cid, message_id, reply_markup=kb
            )

    threading.Thread(target=_worker, daemon=True).start()
