"""Обработчики создания серверных VPN-конфигураций."""

from __future__ import annotations

from html import escape

from core.access import is_admin
from core.bot import bot as telegram_bot
from core.navigation import navigation
from services.awg.config_manager import get_awg_interface_params
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
    vpn_config_menu_kb,
    vpn_config_params_kb,
    vpn_config_result_kb,
)
from ui.screens import (
    ADMIN_VPN_CONFIG,
    ADMIN_VPN_CONFIG_CONFIRM,
    ADMIN_VPN_CONFIG_PARAMS,
    ADMIN_VPN_CONFIG_RESULT,
)
from utils.helpers import safe_delete
from utils.ttl_dict import TTLDict

_DRAFTS = TTLDict(ttl=1800)


def _protocol_name(protocol: str) -> str:
    return {"xray": "VLESS Reality", "awg": "AmneziaWG"}.get(protocol, protocol)


def parse_custom_parameters(protocol: str, raw: str, base_params=None) -> dict:
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

    values = {**defaults, **(base_params or {})}
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


def _initial_protocol_params(protocol: str, config_exists: bool) -> dict:
    """Загружает активные параметры протокола для нового черновика."""
    if protocol != "awg" or not config_exists:
        return parse_custom_parameters(protocol, "")

    fields = get_awg_interface_params()
    defaults = {"port": AWG_DEFAULT_PORT, **AWG_DEFAULT_PARAMS}

    try:
        base_params = {
            "port": int(fields.get("listenport", defaults["port"])),
            **{
                key: int(fields.get(key, default))
                for key, default in AWG_DEFAULT_PARAMS.items()
            },
        }
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "В существующем AWG-конфиге обнаружены некорректные параметры."
        ) from exc

    return parse_custom_parameters("awg", "", base_params=base_params)


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



_ACTIVE_USERS = TTLDict(ttl=1800)
_SCREEN_ERRORS = TTLDict(ttl=300)
_SCREEN_MESSAGES = TTLDict(ttl=1800)
_RESULTS = TTLDict(ttl=1800)


def _active_key(chat_id):
    user_id = _ACTIVE_USERS.get(str(chat_id))
    if user_id is None:
        return None
    return _draft_key(chat_id, user_id)


def _edit(bot, cid, message_id, text, keyboard):
    try:
        bot.edit_message_text(
            text=text,
            chat_id=cid,
            message_id=message_id,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception as exc:
        if "message is not modified" not in str(exc).lower():
            raise
    return True


def _parameter_text(protocol, params, error=None):
    if protocol == "xray":
        values = (
            f"port={params['port']}\n"
            f"sni={params['sni']}\n"
            f"dest={params['dest']}\n"
            f"flow={params['flow'] or 'none'}"
        )
        explanation = (
            "Параметры VLESS Reality.\n"
            "SNI — доменное имя TLS.\n"
            "Reality dest — адрес в формате host:port.\n"
            "Flow: vision или none."
        )
    else:
        values = (
            f"port={params['port']}\n"
            + "\n".join(
                f"{key}={params[key]}"
                for key in (
                    "jc", "jmin", "jmax", "s1", "s2", "s3", "s4",
                    "h1", "h2", "h3", "h4",
                )
            )
        )
        explanation = (
            "Параметры AmneziaWG.\n"
            f"Адрес сервера фиксирован: {AWG_DEFAULT_ADDRESS}."
        )

    error_text = f"❌ <b>{escape(error)}</b>\n\n" if error else ""
    return (
        f"⚙️ <b>Настройка {_protocol_name(protocol)}</b>\n\n"
        f"{error_text}"
        f"{explanation}\n\n"
        "Значения ниже уже заполнены стандартными настройками.\n"
        "Чтобы изменить параметры, отправь только нужные строки "
        "в формате <code>параметр=значение</code>.\n"
        "Изменения сохраняются в черновике. Можно отправлять несколько "
        "сообщений подряд.\n\n"
        f"<b>Текущие параметры:</b>\n<pre>{escape(values)}</pre>\n"
        "Нажми «Далее» для проверки и подтверждения."
    )


def _render_params_screen(bot, cid, message_id):
    key = _active_key(cid)
    draft = _DRAFTS.get(key) if key else None
    if not draft:
        return _edit(
            bot, cid, message_id,
            "Черновик настройки истёк. Выбери протокол заново.",
            vpn_config_menu_kb(),
        )

    _SCREEN_MESSAGES[str(cid)] = message_id
    error = _SCREEN_ERRORS.pop(str(cid), None)
    bot.clear_step_handler_by_chat_id(cid)
    bot.register_next_step_handler_by_chat_id(cid, _handle_custom_input)

    return _edit(
        bot,
        cid,
        message_id,
        _parameter_text(draft["protocol"], draft["params"], error),
        vpn_config_params_kb(draft["protocol"]),
    )


def _render_confirm_screen(bot, cid, message_id):
    key = _active_key(cid)
    draft = _DRAFTS.get(key) if key else None
    if not draft:
        return _edit(
            bot, cid, message_id,
            "Черновик настройки истёк. Начни настройку заново.",
            vpn_config_menu_kb(),
        )

    protocol = draft["protocol"]
    replacing = draft["config_exists"]
    warning = (
        "\n\n⚠️ <b>ВНИМАНИЕ: конфигурация уже существует.</b>\n"
        "Будет выполнена перенастройка с сохранением ключей, "
        "идентификаторов и существующих клиентов."
        if replacing else
        "\n\nПосле подтверждения будет создан серверный конфиг."
    )
    return _edit(
        bot,
        cid,
        message_id,
        _format_summary(protocol, draft["params"]) + warning
        + "\n\nПроверь параметры перед запуском настройки.",
        vpn_config_confirm_kb(protocol, replacing=replacing),
    )


def _render_result_screen(bot, cid, message_id):
    result = _RESULTS.get(str(cid))
    if not result:
        return _edit(
            bot, cid, message_id,
            "Результат настройки больше недоступен.",
            vpn_config_result_kb(),
        )
    return _edit(
        bot,
        cid,
        message_id,
        result,
        vpn_config_result_kb(),
    )


def _handle_custom_input(message):
    cid = message.chat.id
    user_id = message.from_user.id
    key = _draft_key(cid, user_id)
    screen_message_id = _SCREEN_MESSAGES.get(str(cid))

    active_user_id = _ACTIVE_USERS.get(str(cid))
    if active_user_id != user_id:
        if active_user_id is not None and is_admin(cid):
            telegram_bot.register_next_step_handler_by_chat_id(
                cid, _handle_custom_input
            )
        return

    if not is_admin(cid):
        telegram_bot.clear_step_handler_by_chat_id(cid)
        _DRAFTS.pop(key, None)
        _ACTIVE_USERS.pop(str(cid), None)
        _SCREEN_MESSAGES.pop(str(cid), None)
        return

    safe_delete(telegram_bot, cid, message.message_id)

    draft = _DRAFTS.get(key)
    if not draft:
        telegram_bot.clear_step_handler_by_chat_id(cid)
        _SCREEN_MESSAGES.pop(str(cid), None)
        return

    raw = (message.text or "").strip()
    if raw.lower() in ("/cancel", "cancel", "отмена"):
        telegram_bot.clear_step_handler_by_chat_id(cid)
        _SCREEN_MESSAGES.pop(str(cid), None)
        _DRAFTS.pop(key, None)
        _ACTIVE_USERS.pop(str(cid), None)
        screen_id = navigation.back(cid) or ADMIN_VPN_CONFIG
        if screen_id == ADMIN_VPN_CONFIG:
            navigation.start(cid, ADMIN_VPN_CONFIG)
        navigation.render(screen_id, telegram_bot, cid, screen_message_id)
        return

    try:
        params = parse_custom_parameters(
            draft["protocol"],
            raw,
            base_params=draft["params"],
        )
    except ValueError as exc:
        _SCREEN_ERRORS[str(cid)] = str(exc)
        if screen_message_id is not None:
            _render_params_screen(telegram_bot, cid, screen_message_id)
        return

    draft["params"] = params
    _DRAFTS[key] = draft

    if screen_message_id is not None:
        _render_params_screen(telegram_bot, cid, screen_message_id)


def handle_vpn_config_callback(bot, cid, call, data):
    """Callbacks мастера VPN-конфигурации; экраны ведёт NavigationManager."""
    if not data.startswith("vpn_config:"):
        return False

    if not is_admin(cid):
        bot.answer_callback_query(
            call.id, "Недостаточно прав", show_alert=True
        )
        return True

    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    key = _draft_key(cid, call.from_user.id)
    message_id = call.message.message_id

    if action == "protocol" and len(parts) == 3:
        protocol = parts[2]
        if protocol not in get_configurable_protocols():
            bot.answer_callback_query(
                call.id,
                "Протокол не установлен или недоступен.",
                show_alert=True,
            )
            return True

        bot.clear_step_handler_by_chat_id(cid)
        _SCREEN_MESSAGES.pop(str(cid), None)

        config_exists = protocol_config_exists(protocol)
        try:
            params = _initial_protocol_params(protocol, config_exists)
        except (OSError, ValueError) as exc:
            bot.answer_callback_query(
                call.id,
                f"Не удалось загрузить параметры: {exc}",
                show_alert=True,
            )
            return True

        _DRAFTS[key] = {
            "protocol": protocol,
            "params": params,
            "config_exists": config_exists,
        }
        _ACTIVE_USERS[str(cid)] = call.from_user.id
        _SCREEN_ERRORS.pop(str(cid), None)

        navigation.go(cid, ADMIN_VPN_CONFIG_PARAMS)
        navigation.render(
            ADMIN_VPN_CONFIG_PARAMS, bot, cid, message_id
        )
        bot.answer_callback_query(call.id)
        return True

    if action == "review" and len(parts) == 3:
        protocol = parts[2]
        draft = _DRAFTS.get(key)
        if not draft or draft.get("protocol") != protocol:
            bot.answer_callback_query(
                call.id, "Черновик не найден. Начни настройку заново.",
                show_alert=True,
            )
            return True

        bot.clear_step_handler_by_chat_id(cid)
        _SCREEN_MESSAGES.pop(str(cid), None)
        navigation.go(cid, ADMIN_VPN_CONFIG_CONFIRM)
        navigation.render(
            ADMIN_VPN_CONFIG_CONFIRM, bot, cid, message_id
        )
        bot.answer_callback_query(call.id)
        return True

    if action == "confirm" and len(parts) == 3:
        protocol = parts[2]
        draft = _DRAFTS.get(key)

        if not draft or draft.get("protocol") != protocol:
            bot.answer_callback_query(
                call.id,
                "Черновик не найден или устарел. Начни настройку заново.",
                show_alert=True,
            )
            return True

        if protocol not in get_configurable_protocols():
            _DRAFTS.pop(key, None)
            navigation.start(cid, ADMIN_VPN_CONFIG)
            navigation.render(ADMIN_VPN_CONFIG, bot, cid, message_id)
            bot.answer_callback_query(
                call.id, "Протокол больше недоступен.", show_alert=True
            )
            return True

        if protocol_config_exists(protocol) != draft.get("config_exists"):
            _DRAFTS.pop(key, None)
            navigation.start(cid, ADMIN_VPN_CONFIG)
            navigation.render(ADMIN_VPN_CONFIG, bot, cid, message_id)
            bot.answer_callback_query(
                call.id,
                "Состояние конфигурации изменилось. Начни настройку заново.",
                show_alert=True,
            )
            return True

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

        _DRAFTS.pop(key, None)
        _ACTIVE_USERS.pop(str(cid), None)
        _RESULTS[str(cid)] = (
            f"{'✅' if result.created else 'ℹ️'} "
            f"<b>{_protocol_name(protocol)}</b>\n\n"
            f"{escape(str(result.message))}"
        )

        navigation.replace(cid, ADMIN_VPN_CONFIG_RESULT)
        navigation.render(
            ADMIN_VPN_CONFIG_RESULT, bot, cid, message_id
        )
        bot.answer_callback_query(call.id)
        return True

    return True
