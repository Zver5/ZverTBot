"""
Центральный роутер callback-кнопок ZverTBot.

Единый registry содержит:
- точные callback-маршруты;
- динамические prefix-маршруты;
- обработчик;
- политику доступа.

Правила маршрутизации:
1. exact callback имеет приоритет над prefix;
2. среди prefix побеждает самый длинный;
3. доступ определяется самим маршрутом;
4. router не зависит от callback-логики в core.access.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from core.callback_response import CallbackResponse
from core.navigation import (
    CLIENT_CONF_CALLBACK_PREFIX,
    CLIENT_CONF_RU_CALLBACK_PREFIX,
    FAIL2BAN_LOGS_CALLBACK,
    FAIL2BAN_MENU_CALLBACK,
    FAIL2BAN_UNBAN_CALLBACK,
    NAV_ADMIN_TICKETS_CALLBACK,
    NAV_ADMIN_TICKETS_CLOSED_CALLBACK,
    NAV_ADMIN_TICKETS_NEW_CALLBACK,
    NAV_ADMIN_TICKETS_WORKING_CALLBACK,
    NAV_AI_LOGS_CALLBACK,
    NAV_ANALYTICS_CALLBACK,
    NAV_BACK_CALLBACK,
    NAV_BACKUP_HISTORY_CALLBACK,
    NAV_BACKUPS_CALLBACK,
    NAV_CLIENT_BACK_CALLBACK,
    NAV_CLIENT_HELP_CALLBACK,
    NAV_CLIENT_HOME_CALLBACK,
    NAV_CLIENTS_AWG_CALLBACK,
    NAV_CLIENTS_CALLBACK,
    NAV_CLIENTS_MANAGE_CALLBACK,
    NAV_CLIENTS_RENAME_CALLBACK,
    NAV_CLIENTS_SEARCH_AWG_CALLBACK,
    NAV_CLIENTS_SEARCH_VLESS_CALLBACK,
    NAV_CLIENTS_VLESS_CALLBACK,
    NAV_CREATE_CALLBACK,
    NAV_HOME_CALLBACK,
    NAV_MANAGE_CALLBACK,
    NAV_NETWORK_CALLBACK,
    NAV_SYSTEM_CALLBACK,
    PROCESS_KILL_CALLBACK,
    PROCESS_MENU_CALLBACK,
    PROCESS_SEARCH_CALLBACK,
    PROCESS_TOP_CALLBACK,
    PROCESS_TOP_CPU_CALLBACK,
    PROCESS_TOP_RAM_CALLBACK,
)
from handlers.admin.bindings import (
    handle_bind_existing_callback,
    handle_bindings_part1_callback,
    handle_bindings_part2_callback,
    handle_bindings_part3_callback,
)
from handlers.admin.clients import (
    handle_create_client_callback,
    handle_lists_delete_callback,
    handle_qr_config_callback,
    handle_search_callback,
)
from handlers.admin.management import (
    handle_ai_diagnosis_callback,
    handle_management_part1_callback,
    handle_management_part2_callback,
    handle_management_part3_callback,
    handle_management_part4_callback,
)
from handlers.admin.navigation import handle_navigation_callback
from handlers.admin.tickets import (
    handle_admin_close,
    handle_admin_reply,
    handle_admin_tickets,
    show_closed_ticket,
    show_closed_tickets,
    show_new_tickets,
    show_working_tickets,
)
from handlers.client.menu import handle_request_bind
from handlers.client.navigation import handle_client_navigation_callback
from handlers.client.tickets import (
    handle_create_ticket,
    handle_ticket_reply,
    handle_ticket_reply_cancel,
)
from handlers.features.fail2ban import handle_fail2ban_callback
from handlers.features.ip_reputation import handle_ip_reputation_callback
from handlers.features.network import handle_network_callback
from handlers.features.passport_check import handle_passport_check
from handlers.features.portscan import handle_portscan_callback
from handlers.features.processes import handle_processes_callback
from handlers.features.ssh_keys import handle_ssh_callback
from utils.helpers import safe_answer_callback
from utils.logger import logger


class CallbackAccess(str, Enum):
    """Политика доступа callback-маршрута."""

    PUBLIC = "public"
    CLIENT = "client"
    ADMIN = "admin"
    CLIENT_OR_ADMIN = "client_or_admin"


@dataclass(frozen=True)
class CallbackRoute:
    """Полное описание callback-маршрута."""

    pattern: str
    handler: Callable
    access: CallbackAccess
    prefix: bool = False


# ==========================================================
# ЕДИНЫЙ CALLBACK REGISTRY
# ==========================================================


CALLBACK_ROUTES = (
    # ------------------------------------------------------
    # Навигация
    # ------------------------------------------------------
    CallbackRoute(
        NAV_BACK_CALLBACK,
        handle_navigation_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_HOME_CALLBACK,
        handle_navigation_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_MANAGE_CALLBACK,
        handle_navigation_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_CLIENTS_CALLBACK,
        handle_navigation_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_CLIENTS_MANAGE_CALLBACK,
        handle_navigation_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_CLIENTS_VLESS_CALLBACK,
        handle_navigation_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_CLIENTS_AWG_CALLBACK,
        handle_navigation_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_CLIENTS_RENAME_CALLBACK,
        handle_navigation_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_CREATE_CALLBACK,
        handle_navigation_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_SYSTEM_CALLBACK,
        handle_navigation_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_NETWORK_CALLBACK,
        handle_navigation_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_ANALYTICS_CALLBACK,
        handle_navigation_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_BACKUPS_CALLBACK,
        handle_navigation_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_BACKUP_HISTORY_CALLBACK,
        handle_navigation_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_AI_LOGS_CALLBACK,
        handle_navigation_callback,
        CallbackAccess.ADMIN,
    ),
    # ------------------------------------------------------
    # Fail2Ban
    # ------------------------------------------------------
    CallbackRoute(
        FAIL2BAN_MENU_CALLBACK,
        handle_fail2ban_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        FAIL2BAN_LOGS_CALLBACK,
        handle_fail2ban_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        FAIL2BAN_UNBAN_CALLBACK,
        handle_fail2ban_callback,
        CallbackAccess.ADMIN,
    ),
    # ------------------------------------------------------
    # Processes
    # ------------------------------------------------------
    CallbackRoute(
        PROCESS_MENU_CALLBACK,
        handle_processes_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        PROCESS_TOP_CALLBACK,
        handle_processes_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        PROCESS_TOP_CPU_CALLBACK,
        handle_processes_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        PROCESS_TOP_RAM_CALLBACK,
        handle_processes_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        PROCESS_SEARCH_CALLBACK,
        handle_processes_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        PROCESS_KILL_CALLBACK,
        handle_processes_callback,
        CallbackAccess.ADMIN,
    ),
    # ------------------------------------------------------
    # Port Scanner / Passport
    # ------------------------------------------------------
    CallbackRoute(
        "port_scan",
        handle_portscan_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "passport_check",
        handle_passport_check,
        CallbackAccess.ADMIN,
    ),
    # ------------------------------------------------------
    # SSH
    # ------------------------------------------------------
    CallbackRoute("ssh_menu", handle_ssh_callback, CallbackAccess.ADMIN),
    CallbackRoute("ssh_list", handle_ssh_callback, CallbackAccess.ADMIN),
    CallbackRoute("ssh_history", handle_ssh_callback, CallbackAccess.ADMIN),
    CallbackRoute("ssh_delete", handle_ssh_callback, CallbackAccess.ADMIN),
    CallbackRoute("ssh_export", handle_ssh_callback, CallbackAccess.ADMIN),
    # ------------------------------------------------------
    # Network
    # ------------------------------------------------------
    CallbackRoute("net_mtr", handle_network_callback, CallbackAccess.ADMIN),
    CallbackRoute(
        "my_external_ip",
        handle_management_part2_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "speedtest",
        handle_management_part2_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "ip_reputation",
        handle_ip_reputation_callback,
        CallbackAccess.ADMIN,
    ),
    # ------------------------------------------------------
    # Bindings
    # ------------------------------------------------------
    CallbackRoute(
        "bindings_menu",
        handle_bindings_part2_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "bindings_pending",
        handle_bindings_part2_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "bindings_active",
        handle_bindings_part2_callback,
        CallbackAccess.ADMIN,
    ),
    # ------------------------------------------------------
    # Management Part 1
    # ------------------------------------------------------
    CallbackRoute(
        "log_bot",
        handle_management_part1_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "log_awg",
        handle_management_part1_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "log_xray",
        handle_management_part1_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "restart_xray",
        handle_management_part1_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "restart_awg",
        handle_management_part1_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "restart_bot",
        handle_management_part1_callback,
        CallbackAccess.ADMIN,
    ),
    # ------------------------------------------------------
    # AI Diagnostics
    # ------------------------------------------------------
    CallbackRoute(
        "ai_log_bot",
        handle_ai_diagnosis_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "ai_log_xray",
        handle_ai_diagnosis_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "ai_log_awg",
        handle_ai_diagnosis_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "ai_server_health",
        handle_ai_diagnosis_callback,
        CallbackAccess.ADMIN,
    ),
    # ------------------------------------------------------
    # Management Part 2
    # ------------------------------------------------------
    CallbackRoute(
        "close_log",
        handle_management_part2_callback,
        CallbackAccess.ADMIN,
    ),
    # ------------------------------------------------------
    # Management Part 3
    # ------------------------------------------------------
    CallbackRoute(
        "confirm_cleanup",
        handle_management_part3_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "exec_cleanup",
        handle_management_part3_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "show_history",
        handle_management_part3_callback,
        CallbackAccess.ADMIN,
    ),
    # ------------------------------------------------------
    # Management Part 4
    # ------------------------------------------------------
    CallbackRoute(
        "weekly_report",
        handle_management_part4_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "bot_stats",
        handle_management_part4_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "create_backup",
        handle_management_part4_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "status",
        handle_management_part4_callback,
        CallbackAccess.ADMIN,
    ),
    # ------------------------------------------------------
    # Clients
    # ------------------------------------------------------
    CallbackRoute(
        NAV_CLIENTS_SEARCH_VLESS_CALLBACK,
        handle_search_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_CLIENTS_SEARCH_AWG_CALLBACK,
        handle_search_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "add_vless",
        handle_create_client_callback,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        "add_awg",
        handle_create_client_callback,
        CallbackAccess.ADMIN,
    ),
    # ------------------------------------------------------
    # Client menu / public flow
    # ------------------------------------------------------
    CallbackRoute(
        "request_bind",
        handle_request_bind,
        CallbackAccess.PUBLIC,
    ),
    CallbackRoute(
        "create_ticket",
        handle_create_ticket,
        CallbackAccess.PUBLIC,
    ),
    CallbackRoute(
        "ticket_topic_internet",
        handle_create_ticket,
        CallbackAccess.PUBLIC,
    ),
    CallbackRoute(
        "ticket_topic_vpn",
        handle_create_ticket,
        CallbackAccess.PUBLIC,
    ),
    CallbackRoute(
        "ticket_topic_config",
        handle_create_ticket,
        CallbackAccess.PUBLIC,
    ),
    CallbackRoute(
        "ticket_topic_other",
        handle_create_ticket,
        CallbackAccess.PUBLIC,
    ),
    CallbackRoute(
        "ticket_cancel",
        handle_create_ticket,
        CallbackAccess.PUBLIC,
    ),
    CallbackRoute(
        NAV_ADMIN_TICKETS_CALLBACK,
        handle_admin_tickets,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_ADMIN_TICKETS_NEW_CALLBACK,
        show_new_tickets,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_ADMIN_TICKETS_WORKING_CALLBACK,
        show_working_tickets,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_ADMIN_TICKETS_CLOSED_CALLBACK,
        show_closed_tickets,
        CallbackAccess.ADMIN,
    ),
    CallbackRoute(
        NAV_CLIENT_HOME_CALLBACK,
        handle_client_navigation_callback,
        CallbackAccess.CLIENT,
    ),
    CallbackRoute(
        NAV_CLIENT_BACK_CALLBACK,
        handle_client_navigation_callback,
        CallbackAccess.CLIENT,
    ),
    CallbackRoute(
        NAV_CLIENT_HELP_CALLBACK,
        handle_client_navigation_callback,
        CallbackAccess.CLIENT,
    ),
    # ------------------------------------------------------
    # Dynamic callbacks
    # ------------------------------------------------------
    CallbackRoute(
        "get_passport_file:",
        handle_passport_check,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "admin_reply_ticket:",
        handle_admin_reply,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "admin_close_ticket:",
        handle_admin_close,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "ticket_reply:",
        handle_ticket_reply,
        CallbackAccess.PUBLIC,
        prefix=True,
    ),
    CallbackRoute(
        "admin_closed_page:",
        show_closed_tickets,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "admin_closed_ticket:",
        show_closed_ticket,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "ticket_reply_cancel:",
        handle_ticket_reply_cancel,
        CallbackAccess.PUBLIC,
        prefix=True,
    ),
    CallbackRoute(
        "approve_bind_",
        handle_bindings_part1_callback,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "reject_bind_",
        handle_bindings_part1_callback,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "do_bind_",
        handle_bindings_part1_callback,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "bind_existing_",
        handle_bind_existing_callback,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "unbind_select_",
        handle_bindings_part3_callback,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "unbind_confirm_",
        handle_bindings_part3_callback,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "stats_",
        handle_management_part4_callback,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "mtr_target_",
        handle_network_callback,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "ssh_delete_confirm_",
        handle_ssh_callback,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "ssh_delete_final_",
        handle_ssh_callback,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "qr:",
        handle_qr_config_callback,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "qr_select_",
        handle_qr_config_callback,
        CallbackAccess.CLIENT_OR_ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "conf:",
        handle_qr_config_callback,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "ask_del:",
        handle_lists_delete_callback,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "confirm_del:",
        handle_lists_delete_callback,
        CallbackAccess.ADMIN,
        prefix=True,
    ),
    CallbackRoute(
        "client:account:",
        handle_client_navigation_callback,
        CallbackAccess.CLIENT,
        prefix=True,
    ),
    CallbackRoute(
        "client:stats:",
        handle_client_navigation_callback,
        CallbackAccess.CLIENT,
        prefix=True,
    ),
    CallbackRoute(
        CLIENT_CONF_CALLBACK_PREFIX,
        handle_client_navigation_callback,
        CallbackAccess.CLIENT,
        prefix=True,
    ),
    CallbackRoute(
        CLIENT_CONF_RU_CALLBACK_PREFIX,
        handle_client_navigation_callback,
        CallbackAccess.CLIENT,
        prefix=True,
    ),
)


# ==========================================================
# INDEXES
# ==========================================================


def _build_exact_index() -> dict[str, CallbackRoute]:
    """Построить индекс exact-маршрутов из единого registry."""
    return {route.pattern: route for route in CALLBACK_ROUTES if not route.prefix}


def _build_prefix_index() -> tuple[CallbackRoute, ...]:
    """Построить индекс prefix-маршрутов из единого registry."""
    return tuple(
        sorted(
            (route for route in CALLBACK_ROUTES if route.prefix),
            key=lambda route: len(route.pattern),
            reverse=True,
        )
    )


EXACT_ROUTES = _build_exact_index()
PREFIX_ROUTES = _build_prefix_index()


# ==========================================================
# REGISTRY VIEWS
# ==========================================================


def all_callbacks() -> dict[str, CallbackRoute]:
    """Вернуть exact-маршруты."""
    return dict(EXACT_ROUTES)


def all_prefixes() -> dict[str, CallbackRoute]:
    """Вернуть prefix-маршруты."""
    return {route.pattern: route for route in PREFIX_ROUTES}


# ==========================================================
# ROUTING
# ==========================================================


def resolve(data: str) -> CallbackRoute | None:
    """
    Найти полный маршрут callback.

    Exact всегда проверяется первым.
    Затем prefix в порядке длины от большего к меньшему.
    """
    route = EXACT_ROUTES.get(data)

    if route is not None:
        return route

    for route in PREFIX_ROUTES:
        if data.startswith(route.pattern):
            return route

    return None


def get(data: str):
    """Найти обработчик callback."""
    route = resolve(data)
    return route.handler if route else None


# ==========================================================
# ACCESS
# ==========================================================


def authorize(chat_id: int, route: CallbackRoute, data: str = "") -> bool:
    """
    Проверить доступ к уже найденному callback-маршруту.

    Поиск маршрута выполняется только через resolve().
    Авторизация работает с готовым CallbackRoute.

    PUBLIC:
        callback доступен без авторизации.

    CLIENT:
        callback доступен только привязанному клиенту.
        Дополнительно динамический callback с username проверяется
        на принадлежность аккаунта текущему chat_id.

    ADMIN:
        callback доступен только администратору.
    """
    if route.access is CallbackAccess.PUBLIC:
        return True

    from core.access import is_admin, is_client

    if route.access is CallbackAccess.ADMIN:
        return is_admin(chat_id)

    if route.access is CallbackAccess.CLIENT_OR_ADMIN:
        if is_admin(chat_id):
            return True
        if not is_client(chat_id):
            return False

        if route.prefix and route.pattern == "qr_select_":
            payload = data.removeprefix("qr_select_")
            if payload.endswith("_both"):
                username = payload[:-5]
            elif "*" in payload:
                username, _ = payload.rsplit("*", 1)
            else:
                username = payload

            if not username:
                return False

            from ui.client_menu import get_client_list

            return username in get_client_list(chat_id)

        return True

    if route.access is CallbackAccess.CLIENT:
        if not is_client(chat_id):
            return False

        if route.prefix and route.pattern in {
            "client:account:",
            "client:stats:",
            CLIENT_CONF_CALLBACK_PREFIX,
            CLIENT_CONF_RU_CALLBACK_PREFIX,
        }:
            username = data.removeprefix(route.pattern)

            if not username:
                return False

            from ui.client_menu import get_client_list

            return username in get_client_list(chat_id)

        return True

    return False


# ==========================================================
# TELEBOT DISPATCH
# ==========================================================


def register_callback_router(bot):
    """Зарегистрировать единый callback-router в TeleBot."""

    @bot.callback_query_handler(func=lambda call: True)
    def callback_handler(call):
        result = None
        started_at = time.perf_counter()

        try:
            data = call.data
            cid = call.message.chat.id

            logger.debug(
                "callback.received | chat_id=%s | data=%s",
                cid,
                data,
            )

            route = resolve(data)

            if route is None:
                logger.debug(
                    "callback.unmatched | chat_id=%s | data=%s",
                    cid,
                    data,
                )
                return

            logger.debug(
                "callback.routed | chat_id=%s | data=%s | pattern=%s | access=%s",
                cid,
                data,
                route.pattern,
                route.access.value,
            )

            authorized = authorize(cid, route, data)

            if not authorized:
                logger.warning(
                    "callback.denied | chat_id=%s | data=%s | pattern=%s | "
                    "access=%s",
                    cid,
                    data,
                    route.pattern,
                    route.access.value,
                )
                result = CallbackResponse("❌ Недостаточно прав.")
                return

            result = route.handler(bot, cid, call, data)

            logger.debug(
                (
                    "callback.completed | chat_id=%s | data=%s | pattern=%s | "
                    "result=%r | elapsed_ms=%.1f"
                ),
                cid,
                data,
                route.pattern,
                result,
                (time.perf_counter() - started_at) * 1000,
            )

            if result is False:
                return False

        except Exception:
            logger.exception(
                "callback.failed | callback_id=%s | data=%r | elapsed_ms=%.1f",
                getattr(call, "id", None),
                getattr(call, "data", None),
                (time.perf_counter() - started_at) * 1000,
            )
            return False

        finally:
            response = locals().get("result")

            if isinstance(response, CallbackResponse):
                safe_answer_callback(
                    bot,
                    getattr(call, "id", None),
                    response.text,
                    response.show_alert,
                )
            else:
                safe_answer_callback(
                    bot,
                    getattr(call, "id", None),
                )

    return callback_handler
