"""Обработчики создания серверных VPN-конфигураций."""

from __future__ import annotations

from services.vpn_config_status import get_missing_config_protocols
from services.vpn_server_setup import setup_awg_server, setup_xray_server
from ui.keyboards import vpn_config_menu_kb, vpn_config_mode_kb


def _protocol_name(protocol: str) -> str:
    return {
        "xray": "Xray",
        "awg": "AmneziaWG",
    }.get(protocol, protocol)


def handle_vpn_config_callback(call, bot):
    """Обрабатывает callbacks мастера создания VPN-конфига."""
    data = call.data

    if not data.startswith("vpn_config:"):
        return False

    parts = data.split(":")
    if len(parts) < 2:
        return True

    action = parts[1]

    if action == "protocol" and len(parts) == 3:
        protocol = parts[2]

        if protocol not in get_missing_config_protocols():
            bot.answer_callback_query(
                call.id,
                "Этот конфиг уже создан или протокол недоступен.",
                show_alert=True,
            )
            return True

        bot.edit_message_text(
            f"⚙️ Создание конфига {_protocol_name(protocol)}\n\n"
            "Выберите способ:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=vpn_config_mode_kb(protocol),
        )
        bot.answer_callback_query(call.id)
        return True

    if action == "back":
        protocols = get_missing_config_protocols()
        bot.edit_message_text(
            "⚙️ Создание серверного конфига\n\nВыберите протокол:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=vpn_config_menu_kb(protocols),
        )
        bot.answer_callback_query(call.id)
        return True

    if action == "auto" and len(parts) == 3:
        protocol = parts[2]

        if protocol not in get_missing_config_protocols():
            bot.answer_callback_query(
                call.id,
                "Конфиг уже создан или протокол недоступен.",
                show_alert=True,
            )
            return True

        if protocol == "xray":
            result = setup_xray_server()
        elif protocol == "awg":
            result = setup_awg_server()
        else:
            bot.answer_callback_query(call.id, "Неизвестный протокол", show_alert=True)
            return True

        bot.edit_message_text(
            f"{'✅' if result.created else 'ℹ️'} {_protocol_name(protocol)}\n\n"
            f"{result.message}",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.answer_callback_query(call.id)
        return True

    if action == "custom" and len(parts) == 3:
        bot.answer_callback_query(
            call.id,
            "Ввод своих параметров подключим следующим шагом.",
            show_alert=True,
        )
        return True

    return True
