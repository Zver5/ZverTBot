"""Центральная регистрация navigation screens при старте приложения."""

from core.navigation import navigation
from handlers.admin.bindings import (
    render_bindings_active,
    render_bindings_menu,
    render_bindings_pending,
)
from handlers.admin.clients import (
    _render_awg_screen,
    _render_rename_screen,
    _render_vless_screen,
)
from handlers.admin.management import (
    render_action_history,
    render_backup_history,
    render_cleanup,
    render_speedtest,
)
from handlers.admin.navigation import _STATIC_SCREENS
from handlers.client.menu import (
    render_client_help,
    render_client_home,
)
from handlers.client.navigation import _render_client_account
from handlers.features.fail2ban import (
    render_fail2ban_logs,
    render_fail2ban_menu,
    render_fail2ban_unban_input,
)
from handlers.features.ip_reputation import render_ip_reputation
from handlers.features.network import render_net_mtr
from handlers.features.portscan import render_port_scan
from handlers.features.processes import (
    render_processes_kill_input,
    render_processes_menu,
    render_processes_search_input,
    render_processes_top,
    render_processes_top_cpu,
    render_processes_top_ram,
)
from handlers.features.ssh_keys import (
    render_ssh_delete,
    render_ssh_history,
    render_ssh_list,
    render_ssh_menu,
)
from ui.screens import (
    ACTION_HISTORY,
    ADMIN_CLIENTS_AWG,
    ADMIN_CLIENTS_RENAME,
    ADMIN_CLIENTS_VLESS,
    BACKUP_HISTORY,
    BINDINGS_ACTIVE,
    BINDINGS_MENU,
    BINDINGS_PENDING,
    CLEANUP,
    CLIENT_ACCOUNT,
    CLIENT_HELP,
    CLIENT_HOME,
    FAIL2BAN_LOGS,
    FAIL2BAN_MENU,
    FAIL2BAN_UNBAN_INPUT,
    IP_REPUTATION,
    NET_MTR,
    PORT_SCAN,
    PROCESS_KILL_INPUT,
    PROCESS_MENU,
    PROCESS_SEARCH_INPUT,
    PROCESS_TOP,
    PROCESS_TOP_CPU,
    PROCESS_TOP_RAM,
    SPEEDTEST,
    SSH_DELETE,
    SSH_HISTORY,
    SSH_LIST,
    SSH_MENU,
)


def register_navigation_screens():
    """Зарегистрировать все navigation screens ровно один раз при старте."""

    # Client.
    navigation.register(CLIENT_HOME, render_client_home)
    navigation.register(CLIENT_HELP, render_client_help)
    navigation.register(CLIENT_ACCOUNT, _render_client_account)

    # Admin static screens.
    for _screen_id, _renderer in _STATIC_SCREENS.items():
        navigation.register(_screen_id, _renderer)

    # Admin client screens.
    navigation.register(ADMIN_CLIENTS_VLESS, _render_vless_screen)
    navigation.register(ADMIN_CLIENTS_AWG, _render_awg_screen)
    navigation.register(ADMIN_CLIENTS_RENAME, _render_rename_screen)

    # Bindings.
    navigation.register(BINDINGS_MENU, render_bindings_menu)
    navigation.register(BINDINGS_ACTIVE, render_bindings_active)
    navigation.register(BINDINGS_PENDING, render_bindings_pending)

    # Management.
    navigation.register(SPEEDTEST, render_speedtest)
    navigation.register(CLEANUP, render_cleanup)
    navigation.register(ACTION_HISTORY, render_action_history)
    navigation.register(BACKUP_HISTORY, render_backup_history)

    # Fail2ban.
    navigation.register(FAIL2BAN_MENU, render_fail2ban_menu)
    navigation.register(FAIL2BAN_LOGS, render_fail2ban_logs)
    navigation.register(FAIL2BAN_UNBAN_INPUT, render_fail2ban_unban_input)

    # Network.
    navigation.register(NET_MTR, render_net_mtr)

    # Port scan.
    navigation.register(PORT_SCAN, render_port_scan)

    # Processes.
    navigation.register(PROCESS_MENU, render_processes_menu)
    navigation.register(PROCESS_TOP, render_processes_top)
    navigation.register(PROCESS_TOP_CPU, render_processes_top_cpu)
    navigation.register(PROCESS_TOP_RAM, render_processes_top_ram)
    navigation.register(PROCESS_SEARCH_INPUT, render_processes_search_input)
    navigation.register(PROCESS_KILL_INPUT, render_processes_kill_input)

    # IP reputation.
    navigation.register(IP_REPUTATION, render_ip_reputation)

    # SSH.
    navigation.register(SSH_MENU, render_ssh_menu)
    navigation.register(SSH_LIST, render_ssh_list)
    navigation.register(SSH_HISTORY, render_ssh_history)
    navigation.register(SSH_DELETE, render_ssh_delete)
