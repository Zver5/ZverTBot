"""
Сервис работы с VPN-клиентами.
Бизнес-логика: списки, переименование, отправка конфигов, история.
"""

import os
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path  # noqa: F401
from urllib.parse import urlsplit

from telebot import types

from config import (
    AWG_CONF,
    SERVER_IP,
)
from core.navigation import NAV_BACK_CALLBACK
from data.storage import (
    load_awg_registry,
    load_client_bindings,
    load_history,
    save_awg_registry,
    save_client_bindings,
)
from data.traffic import (
    remove_client_from_usage,
    rename_client_in_usage,
)
from services.awg.client_manager import awg_del_user
from services.awg.config_generator import awg_get_config
from services.awg.config_manager import rename_peer_in_config
from services.bindings import remove_client_from_all_bindings
from services.xray.client_manager import reload_xray
from services.xray.config_manager import (
    get_all_vless_clients,
    get_vless_inbounds,
    load_xray_config,
    remove_client_from_all_inbounds,
    rename_client_in_config,
    save_xray_config,
)
from services.xray.link_generator import xray_get_link
from utils.client_operation_lock import client_operation_lock
from utils.helpers import escape_md
from utils.logger import logger
from utils.perf import profile


@profile()
def get_users_list(proto):
    """Получить список имён клиентов для протокола"""
    users = []
    if proto == "vless":
        users = get_all_vless_clients(load_xray_config())
    elif proto == "awg":
        users = list(load_awg_registry().keys())
    return list(set(users))


def get_client_protocol(username: str) -> str | None:
    """Определить протокол клиента по его имени."""
    vless_users = set(get_users_list("vless"))
    awg_users = set(get_users_list("awg"))

    in_vless = username in vless_users
    in_awg = username in awg_users

    if in_vless and in_awg:
        raise ValueError(f"Клиент {username!r} одновременно присутствует в VLESS и AWG")

    if in_vless:
        return "vless"

    if in_awg:
        return "awg"

    return None


@profile()
@client_operation_lock
def rename_client(old_name, new_name):
    """Переименовать клиента во всех хранилищах атомарно."""
    logger.info(
        "client.rename.started | old_name=%s | new_name=%s",
        old_name,
        new_name,
    )

    errors = []
    success = False

    # Проверка нового имени
    if old_name.lower() != new_name.lower():
        try:
            from utils.validators import (
                is_username_unique_awg,
                is_username_unique_vless,
            )

            if not is_username_unique_vless(new_name):
                return [f"❌ Имя {new_name} уже занято в Xray (без учёта регистра)"]

            if not is_username_unique_awg(new_name):
                return [f"❌ Имя {new_name} уже занято в AWG (без учёта регистра)"]

        except Exception as e:
            return [f"❌ Ошибка проверки имени: {e}"]

    # Сначала читаем все состояния, чтобы rollback мог вернуть
    # исходное состояние каждого хранилища.
    import copy

    usage_changed = False
    xray_changed = False
    awg_changed = False
    awg_config_changed = False

    original_xray = None
    original_awg = None
    original_bindings = None

    try:
        original_xray = copy.deepcopy(load_xray_config())
    except Exception as e:
        errors.append(f"Xray: {e}")

    try:
        original_awg = copy.deepcopy(load_awg_registry())
    except Exception as e:
        errors.append(f"AWG: {e}")

    try:
        original_bindings = copy.deepcopy(load_client_bindings())
    except Exception as e:
        errors.append(f"bindings: {e}")

    # Если не удалось получить состояние критических хранилищ,
    # ничего не меняем.
    if errors:
        logger.info(
            "client.rename.completed | old_name=%s | new_name=%s | "
            "success=%s | errors=%s",
            old_name,
            new_name,
            False,
            len(errors),
        )
        return errors

    try:
        # usage.json
        try:
            if rename_client_in_usage(old_name, new_name):
                usage_changed = True
                success = True
        except Exception as e:
            errors.append(f"usage: {e}")
            raise

        # Xray
        try:
            xray = copy.deepcopy(original_xray)
            if rename_client_in_config(xray, old_name, new_name):
                save_xray_config(xray)
                xray_changed = True
                reload_xray()
                success = True
        except Exception as e:
            errors.append(f"Xray: {e}")
            raise

        # AWG
        try:
            reg = copy.deepcopy(original_awg)
            if old_name in reg:
                reg[new_name] = reg.pop(old_name)
                save_awg_registry(reg)
                awg_changed = True

                if not rename_peer_in_config(old_name, new_name):
                    raise RuntimeError(
                        f"Не удалось переименовать клиента {old_name!r} в awg0.conf"
                    )

                awg_config_changed = True
                success = True
        except Exception as e:
            errors.append(f"AWG: {e}")
            raise

        # bindings
        try:
            bindings = copy.deepcopy(original_bindings)
            updated = False

            for cid, clients in list(bindings.items()):
                if not isinstance(clients, list):
                    clients = [clients] if clients else []

                if old_name in clients:
                    bindings[cid] = [new_name if c == old_name else c for c in clients]
                    updated = True

            if updated:
                save_client_bindings(bindings)
                success = True
        except Exception as e:
            errors.append(f"bindings: {e}")
            raise

    except Exception:
        # Rollback в обратном порядке.
        if awg_changed:
            try:
                save_awg_registry(copy.deepcopy(original_awg))

                if awg_config_changed:
                    if not rename_peer_in_config(new_name, old_name):
                        raise RuntimeError(
                            f"Не удалось откатить переименование клиента "
                            f"{new_name!r} → {old_name!r} в awg0.conf"
                        )
            except Exception as rollback_error:
                errors.append(f"rollback AWG: {rollback_error}")

        if xray_changed:
            try:
                save_xray_config(copy.deepcopy(original_xray))
                reload_xray()
            except Exception as rollback_error:
                errors.append(f"rollback Xray: {rollback_error}")

        if usage_changed:
            try:
                rename_client_in_usage(new_name, old_name)
            except Exception as rollback_error:
                errors.append(f"rollback usage: {rollback_error}")

        success = False

    if not success and not errors:
        errors.append("Клиент не найден ни в одном хранилище")

    logger.info(
        "client.rename.completed | old_name=%s | new_name=%s | "
        "success=%s | errors=%s",
        old_name,
        new_name,
        success,
        len(errors),
    )

    return errors


@profile()
@client_operation_lock
def delete_client(username: str, proto: str) -> None:
    """Удалить клиента из конфигурации и связанных хранилищ."""
    if proto == "vless":
        config = load_xray_config()
        remove_client_from_all_inbounds(config, username)
        save_xray_config(config)
        reload_xray()
    elif proto == "awg":
        ok, message = awg_del_user(username)
        if not ok:
            raise RuntimeError(message)
    else:
        raise ValueError(f"Unknown protocol: {proto}")

    remove_client_from_usage(username)
    remove_client_from_all_bindings(username)


@profile()
def send_qr_or_conf(bot, chat_id, username, proto, config_only=False):
    """
    Отправляет QR или конфигурацию.

    VLESS:
        - config_only=False — QR;
        - config_only=True — VLESS-ссылки без QR.

    AWG:
        - QR + конфигурация.

    VLESS:
        - если есть несколько ссылок/портов — показывает выбор порта;
        - выбранный QR отправляется через handle_qr_config_callback.

    AWG:
        - сразу отправляет QR + конфигурацию.
    """
    qr_file = tempfile.NamedTemporaryFile(
        prefix=f"qr_{username}_",
        suffix=".png",
        delete=False,
    )
    qr_path = qr_file.name
    qr_file.close()

    try:
        if proto == "vless":
            link = xray_get_link(username)

            if not link:
                raise ValueError("Link not found")

            if config_only:
                links = [item.strip() for item in link.split("\n") if item.strip()]

                if not links:
                    raise ValueError("VLESS links not found")

                message_parts = [f"🔗 *Конфигурация для {username}*"]

                for item in links:
                    try:
                        port = urlsplit(item).port

                        if port == 443:
                            title = "📱 VLESS 443"
                        elif port == 2096:
                            title = "📱 VLESS 2096"
                        else:
                            title = f"📱 VLESS {port}"

                    except Exception:
                        title = "🔗 VLESS"

                    message_parts.append(f"\n*{title}:*\n```{item}```")

                message_parts.append(
                    "\n💡 Скопируйте нужную ссылку и добавьте её в Shadowrocket."
                )

                bot.send_message(
                    chat_id,
                    "\n".join(message_parts),
                    parse_mode="Markdown",
                )
                return

        if proto == "vless":
            # У VLESS может быть несколько inbound/link.
            # В этом случае сначала выбираем нужный QR.
            if "\n" in link:
                kb = types.InlineKeyboardMarkup(row_width=1)

                vless_inbounds = get_vless_inbounds(load_xray_config())
                vless_ports = [
                    inbound.get("port")
                    for inbound in vless_inbounds
                    if inbound.get("port")
                ]

                buttons = []

                for index, port in enumerate(vless_ports):
                    if index == 0:
                        title = f"📱 MTS/Мегафон/Tele2:{port}"
                    elif index == 1:
                        title = f"🐝 Билайн:{port}"
                    else:
                        title = f"📱 VLESS:{port}"

                    buttons.append(
                        types.InlineKeyboardButton(
                            title,
                            callback_data=f"qr_select_{username}*{port}",
                        )
                    )

                if len(buttons) > 1:
                    buttons.append(
                        types.InlineKeyboardButton(
                            "📤 Оба QR-кода",
                            callback_data=f"qr_select_{username}_both",
                        )
                    )

                kb.add(*buttons)

                bot.send_message(
                    chat_id,
                    f"📱 *Выберите QR-код для {username}:*",
                    parse_mode="Markdown",
                    reply_markup=kb,
                )
                return

            subprocess.run(
                [
                    "qrencode",
                    "-t",
                    "png",
                    "-o",
                    qr_path,
                    "-l",
                    "L",
                    "-s",
                    "3",
                    link,
                ],
                check=True,
            )

            caption = (
                f"📤 *VLESS QR: {username}*\n"
                f"🌐 Сервер: `{SERVER_IP}`\n"
                f"🔹 Поток: `xtls-rprx-vision`\n"
                "📱 Shadowrocket: Proxy + Настройки + Туннель + Все сети"
            )

        elif proto == "awg":
            conf = awg_get_config(username)

            if not conf:
                raise ValueError("Config not found")

            subprocess.run(
                [
                    "qrencode",
                    "-t",
                    "png",
                    "-o",
                    qr_path,
                    "-l",
                    "L",
                    "-s",
                    "3",
                    conf,
                ],
                check=True,
            )

            listen_port = "N/A"

            try:
                with open(AWG_CONF, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("ListenPort"):
                            _, value = line.split("=", 1)
                            listen_port = value.strip()
                            break
            except OSError:
                pass

            client_ip = load_awg_registry().get(username, {}).get("ip", "N/A")

            caption = (
                f"📤 *AWG QR + Конфиг: {username}*\n"
                f"🔹 Сервер: `{SERVER_IP}:{listen_port}`\n"
                f"📍 Ваш IP: `{client_ip}`\n"
                "Amnezia VPN: Импорт QR"
            )

        else:
            raise ValueError(f"Unknown protocol: {proto}")

        with open(qr_path, "rb") as photo:
            bot.send_photo(
                chat_id,
                photo,
                caption=caption,
                parse_mode="Markdown",
            )

        # AWG дополнительно отдаёт сам .conf-файл.
        if proto == "awg":
            conf = awg_get_config(username)

            if not conf:
                raise ValueError("AWG config not found")

            document = BytesIO(conf.encode("utf-8"))
            document.name = f"{username}.awg.conf"
            document.seek(0)

            bot.send_document(
                chat_id,
                document,
                caption=f"📄 Конфигурация AWG: `{username}`",
                parse_mode="Markdown",
            )

    finally:
        if os.path.exists(qr_path):
            os.remove(qr_path)


def show_history_action(bot, cid, mid=None):
    """Показать последние действия бота."""
    try:
        history = load_history()

        if not history:
            text = "📜 История пуста. Совершите любое действие."
        else:
            text = "📜 *ИСТОРИЯ ДЕЙСТВИЙ БОТА* (Последние 5)\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n"

            for entry in history[-5:]:
                icon = "✅" if entry["status"] == "SUCCESS" else "❌"
                act = entry["action"].upper()

                if act == "СОЗДАНИЕ":
                    act = "СОЗДАН КЛИЕНТ"
                elif act == "УДАЛЕНИЕ":
                    act = "УДАЛЁН КЛИЕНТ"
                elif act == "ПЕРЕИМЕНОВАНИЕ":
                    act = "ПЕРЕИМЕНОВАН КЛИЕНТ"
                elif act == "СОЗДАНИЕ БЭКАПА":
                    act = "СОЗДАН БЭКАП"
                elif act == "УДАЛЕНИЕ SSH-КЛЮЧА":
                    act = "УДАЛЁН SSH-КЛЮЧ"
                elif act == "ЗАВЕРШЕНИЕ ПРОЦЕССА":
                    act = "ЗАВЕРШЁН ПРОЦЕСС"
                elif act == "РАЗБАН IP":
                    act = "РАЗБАНЕН IP"
                elif act == "ПРИВЯЗКА":
                    act = "ПРИВЯЗАН КЛИЕНТ"
                elif act == "ОТВЯЗКА":
                    act = "ОТВЯЗАН КЛИЕНТ"

                text += f"\n🕐 {entry['time']}\n"
                text += f"🎯 Цель: `{entry['target']}`\n"
                text += f"{icon} *Действие:* {escape_md(act)}\n"

                if entry["details"]:
                    text += f"📝 {entry['details']}\n"

                text += "━━━━━━━━━━━━━━━━━━━━"

        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(
                "↩️ Назад",
                callback_data=NAV_BACK_CALLBACK,
            )
        )

        if mid is not None:
            from utils.helpers import safe_edit_message

            safe_edit_message(
                bot,
                text,
                cid,
                mid,
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

    except Exception as e:
        logger.exception("client.history.failed | error=%s", e)

        try:
            if mid is not None:
                from utils.helpers import safe_edit_message

                safe_edit_message(
                    bot,
                    f"❌ Ошибка: {e}",
                    cid,
                    mid,
                )
            else:
                bot.send_message(cid, f"❌ Ошибка: {e}")
        except Exception as send_error:
            logger.exception("client.history.send_failed | error=%s", send_error)
