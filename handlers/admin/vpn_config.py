"""Обработчики создания серверных VPN-конфигураций."""

from __future__ import annotations

from core.access import is_admin
from services.vpn_config_status import (
    get_configurable_protocols,
    protocol_config_exists,
)
from services.vpn_server_setup import (
    AWG_DEFAULT_ADDRESS,
    AWG_DEFAULT_PARAMS,
    AWG_DEFAULT_PORT,
    XRAY_DEFAULT_DEST,
    XRAY_DEFAULT_PORT,
    XRAY_DEFAULT_SNI,
    setup_awg_server,
    setup_xray_server,
)
from ui.keyboards import (
    vpn_config_confirm_kb,
    vpn_config_custom_cancel_kb,
    vpn_config_menu_kb,
    vpn_config_mode_kb,
)
from utils.ttl_dict import TTLDict

_DRAFTS = TTLDict(ttl=1800)


def _protocol_name(protocol: str) -> str:
    return {"xray": "Xray", "awg": "AmneziaWG"}.get(protocol, protocol)


def parse_custom_parameters(protocol: str, raw: str) -> dict:
    """Разбирает пользовательские параметры, оставляя пропущенные defaults."""
    if protocol == "xray":
        defaults = {
            "port": XRAY_DEFAULT_PORT,
            "sni": XRAY_DEFAULT_SNI,
            "dest": XRAY_DEFAULT_DEST,
            "flow": "xtls-rprx-vision",
        }
    elif protocol == "awg":
        defaults = {"port": AWG_DEFAULT_PORT, **AWG_DEFAULT_PARAMS}
    else:
        raise ValueError("Неизвестный протокол")

    values = defaults.copy()
    seen = set()

    for line_number, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if "=" not in line:
            raise ValueError(
                f"Строка {line_number}: ожидается формат параметр=значение"
            )

        key, value = (part.strip().lower() for part in line.split("=", 1))
        if key not in defaults:
            raise ValueError(f"Неизвестный параметр: {key}")
        if key in seen:
            raise ValueError(f"Параметр {key} указан несколько раз")
        seen.add(key)

        if not value:
            continue

        if key == "flow":
            flow = value.lower()
            if flow in ("vision", "xtls-rprx-vision"):
                values[key] = "xtls-rprx-vision"
            elif flow in ("none", "без flow", "off"):
                values[key] = ""
            else:
                raise ValueError("Flow должен быть vision или none")
        elif key in ("sni", "dest"):
            values[key] = value
        else:
            try:
                values[key] = int(value, 10)
            except ValueError as exc:
                raise ValueError(
                    f"Параметр {key} должен быть целым числом"
                ) from exc

    port = values["port"]
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Порт должен быть в диапазоне 1–65535")

    if protocol == "xray":
        sni = values["sni"]
        dest = values["dest"]
        if not sni or any(ch.isspace() for ch in sni):
            raise ValueError("Некорректный SNI")
        if not dest or any(ch.isspace() for ch in dest) or ":" not in dest:
            raise ValueError("Reality dest должен иметь формат host:port")
        host, dest_port = dest.rsplit(":", 1)
        if not host:
            raise ValueError("В Reality dest отсутствует имя хоста")
        try:
            dest_port = int(dest_port)
        except ValueError as exc:
            raise ValueError("Порт Reality dest должен быть числом") from exc
        if not 1 <= dest_port <= 65535:
            raise ValueError("Порт Reality dest должен быть в диапазоне 1–65535")
    else:
        for key, value in values.items():
            if key != "port" and (type(value) is not int or value < 0):
                raise ValueError(f"{key} должен быть неотрицательным целым числом")
        if values["jmin"] > values["jmax"]:
            raise ValueError("Jmin не может быть больше Jmax")

    return values


def _draft_key(chat_id, user_id):
    return str(chat_id), str(user_id)


def _format_summary(protocol: str, params: dict) -> str:
    if protocol == "xray":
        return (
            "⚡ <b>VLESS Reality — параметры настройки</b>\n\n"
            f"Порт: <code>{params['port']}</code>\n"
            f"SNI: <code>{params['sni']}</code>\n"
            f"Reality dest: <code>{params['dest']}</code>\n"
            f"Flow: <code>{params['flow'] or 'None'}</code>\n"
        )

    lines = [
        "🛡 <b>AmneziaWG — параметры настройки</b>",
        "",
        f"Порт: <code>{params['port']}</code>",
        f"Адрес сервера: <code>{AWG_DEFAULT_ADDRESS}</code>",
    ]
    for key in ("jc", "jmin", "jmax", "s1", "s2", "s3", "s4",
                "h1", "h2", "h3", "h4"):
        lines.append(f"{key.upper()}: <code>{params[key]}</code>")
    return "\n".join(lines)


def _prompt_custom_input(bot, chat_id, protocol):
    if not is_admin(chat_id):
        return

    if protocol == "xray":
        example = (
            "port=8443\n"
            "sni=example.com\n"
            "dest=example.com:443\n"
            "flow=vision"
        )
        defaults = (
            f"port={XRAY_DEFAULT_PORT}\n"
            f"sni={XRAY_DEFAULT_SNI}\n"
            f"dest={XRAY_DEFAULT_DEST}\n"
            "flow=xtls-rprx-vision"
        )
        explanation = (
            "SNI — доменное имя TLS.\n"
            "Reality dest — целевой адрес в формате host:port.\n"
            "Flow: vision или none."
        )
    else:
        example = (
            "port=51820\n"
            "jc=5\n"
            "jmin=30\n"
            "jmax=80\n"
            "s1=101\n"
            "s2=102\n"
            "s3=103\n"
            "s4=104\n"
            "h1=11\n"
            "h2=12\n"
            "h3=13\n"
            "h4=14"
        )
        defaults = (
            f"port={AWG_DEFAULT_PORT}\n"
            + "\n".join(f"{k}={v}" for k, v in AWG_DEFAULT_PARAMS.items())
        )
        explanation = (
            f"Адрес сервера фиксирован: {AWG_DEFAULT_ADDRESS}.\n"
            "Подсеть здесь не меняется."
        )

    prompt = bot.send_message(
        chat_id,
        (
            f"⚙️ <b>Свои параметры — {_protocol_name(protocol)}</b>\n\n"
            f"{explanation}\n\n"
            "Отправь параметры по одному на строку в формате "
            "<code>параметр=значение</code>.\n"
            "Можно указать только изменяемые параметры. "
            "Пропущенные или пустые будут стандартными.\n\n"
            f"<b>Текущие значения:</b>\n<pre>{defaults}</pre>\n"
            f"<b>Пример:</b>\n<pre>{example}</pre>\n"
            "Для отмены отправь /cancel."
        ),
        parse_mode="HTML",
        reply_markup=vpn_config_custom_cancel_kb(),
    )
    bot.register_next_step_handler(
        prompt, _handle_custom_input, bot, protocol
    )


def _handle_custom_input(message, bot, protocol):
    chat_id = message.chat.id
    user_id = message.from_user.id
    key = _draft_key(chat_id, user_id)

    if not is_admin(chat_id):
        _DRAFTS.pop(key, None)
        return

    raw = (message.text or "").strip()
    if raw.lower() in ("/cancel", "cancel", "отмена"):
        _DRAFTS.pop(key, None)
        bot.clear_step_handler_by_chat_id(chat_id)
        bot.send_message(
            chat_id,
            "Настройка отменена.",
            reply_markup=vpn_config_menu_kb(),
        )
        return

    try:
        params = parse_custom_parameters(protocol, raw)
    except ValueError as exc:
        bot.send_message(
            chat_id,
            f"❌ {exc}\n\nИсправь параметры и отправь сообщение ещё раз.",
        )
        _prompt_custom_input(bot, chat_id, protocol)
        return

    if protocol not in get_configurable_protocols():
        bot.send_message(
            chat_id,
            "Протокол не установлен или недоступен.",
            reply_markup=vpn_config_menu_kb(),
        )
        return

    replacing = protocol_config_exists(protocol)
    _DRAFTS[key] = {
        "protocol": protocol,
        "params": params,
        "config_exists": replacing,
    }
    warning = (
        "\n\n⚠️ <b>ВНИМАНИЕ: конфигурация уже существует.</b> "
        "Будет выполнена перенастройка с сохранением ключей, "
        "идентификаторов и существующих клиентов."
        if replacing else
        "\n\nПроверь параметры. Конфиг будет создан после подтверждения."
    )
    bot.send_message(
        chat_id,
        _format_summary(protocol, params) + warning,
        parse_mode="HTML",
        reply_markup=vpn_config_confirm_kb(protocol, replacing=replacing),
    )


def handle_vpn_config_callback(bot, cid, call, data):
    """Обрабатывает callbacks мастера настройки VPN-конфига."""
    if not data.startswith("vpn_config:"):
        return False

    if not is_admin(cid):
        bot.answer_callback_query(call.id, "Недостаточно прав", show_alert=True)
        return True

    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    key = _draft_key(cid, call.from_user.id)

    if action == "protocol" and len(parts) == 3:
        protocol = parts[2]
        if protocol not in get_configurable_protocols():
            bot.answer_callback_query(
                call.id, "Протокол не установлен или недоступен.",
                show_alert=True,
            )
            return True

        bot.edit_message_text(
            f"⚙️ Настройка конфига {_protocol_name(protocol)}\n\nВыберите способ:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=vpn_config_mode_kb(protocol),
        )
        bot.answer_callback_query(call.id)
        return True

    if action in ("back", "cancel"):
        bot.clear_step_handler_by_chat_id(cid)
        _DRAFTS.pop(key, None)
        text = (
            "⚙️ Настройка серверного конфига\n\nВыберите протокол:"
            if action == "back" else "Настройка отменена."
        )
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=vpn_config_menu_kb(),
        )
        bot.answer_callback_query(call.id)
        return True

    if action in ("auto", "custom") and len(parts) == 3:
        protocol = parts[2]
        if protocol not in get_configurable_protocols():
            bot.answer_callback_query(
                call.id, "Протокол не установлен или недоступен.",
                show_alert=True,
            )
            return True

        bot.clear_step_handler_by_chat_id(cid)
        _DRAFTS.pop(key, None)

        if action == "custom":
            bot.answer_callback_query(call.id)
            _prompt_custom_input(bot, cid, protocol)
            return True

        params = parse_custom_parameters(protocol, "")
        replacing = protocol_config_exists(protocol)
        _DRAFTS[key] = {
            "protocol": protocol,
            "params": params,
            "config_exists": replacing,
        }
        warning = (
            "\n\n⚠️ <b>ВНИМАНИЕ: конфигурация уже существует.</b> "
            "Будет выполнена перенастройка с сохранением ключей, "
            "идентификаторов и существующих клиентов."
            if replacing else
            "\n\nПроверь параметры. Конфиг будет создан после подтверждения."
        )
        bot.edit_message_text(
            _format_summary(protocol, params) + warning,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=vpn_config_confirm_kb(protocol, replacing=replacing),
        )
        bot.answer_callback_query(call.id)
        return True

    if action == "confirm" and len(parts) == 3:
        protocol = parts[2]
        draft = _DRAFTS.get(key)

        if not draft or draft.get("protocol") != protocol:
            bot.answer_callback_query(
                call.id, "Черновик не найден или устарел. Начни настройку заново.",
                show_alert=True,
            )
            return True

        if protocol not in get_configurable_protocols():
            _DRAFTS.pop(key, None)
            bot.edit_message_text(
                "Протокол больше не установлен или недоступен.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=vpn_config_menu_kb(),
            )
            bot.answer_callback_query(call.id)
            return True

        if protocol_config_exists(protocol) != draft.get("config_exists"):
            _DRAFTS.pop(key, None)
            bot.edit_message_text(
                "Состояние конфигурации изменилось. "
                "Начни настройку заново для повторного подтверждения.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=vpn_config_menu_kb(),
            )
            bot.answer_callback_query(call.id)
            return True

        _DRAFTS.pop(key, None)
        params = draft["params"]

        if protocol == "xray":
            result = setup_xray_server(**params)
        elif protocol == "awg":
            result = setup_awg_server(**params)
        else:
            bot.answer_callback_query(
                call.id, "Неизвестный протокол", show_alert=True
            )
            return True

        bot.edit_message_text(
            f"{'✅' if result.created else 'ℹ️'} {_protocol_name(protocol)}\n\n"
            f"{result.message}",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.answer_callback_query(call.id)
        return True

    return True
