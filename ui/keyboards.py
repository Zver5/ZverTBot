"""Модуль клавиатур Telegram-бота.
Все функции создания InlineKeyboardMarkup вынесены из zvertbot.py.
"""

from telebot import types

from core.navigation import (
    CLIENT_CONF_CALLBACK_PREFIX,
    CLIENT_CONF_RU_CALLBACK_PREFIX,
    FAIL2BAN_LOGS_CALLBACK,
    FAIL2BAN_MENU_CALLBACK,
    FAIL2BAN_UNBAN_CALLBACK,
    NAV_ADMIN_TICKETS_CALLBACK,
    NAV_AI_LOGS_CALLBACK,
    NAV_ANALYTICS_CALLBACK,
    NAV_BACK_CALLBACK,
    NAV_BACKUP_HISTORY_CALLBACK,
    NAV_BACKUPS_CALLBACK,
    NAV_CLIENT_HELP_CALLBACK,
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
)
from services.xray.link_generator import xray_get_ports


def main_menu_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.add(
        types.InlineKeyboardButton("👥 Клиенты", callback_data=NAV_CLIENTS_CALLBACK),
        types.InlineKeyboardButton("🖥 Статус", callback_data="status"),
    )

    kb.add(
        types.InlineKeyboardButton(
            "🌐 Сеть и безопасность",
            callback_data=NAV_MANAGE_CALLBACK,
        ),
        types.InlineKeyboardButton(
            "🔧 Службы",
            callback_data=NAV_SYSTEM_CALLBACK,
        ),
    )

    kb.add(
        types.InlineKeyboardButton(
            "📊 Аналитика",
            callback_data=NAV_ANALYTICS_CALLBACK,
        ),
        types.InlineKeyboardButton("💾 Бэкапы", callback_data=NAV_BACKUPS_CALLBACK),
    )

    return kb


def create_menu_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.add(
        types.InlineKeyboardButton("⚡ VLESS", callback_data="add_vless"),
        types.InlineKeyboardButton("🛡 AWG", callback_data="add_awg"),
    )

    kb.add(types.InlineKeyboardButton("↩️ Назад", callback_data=NAV_BACK_CALLBACK))

    return kb


def clients_menu_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.add(
        types.InlineKeyboardButton("👤 Создать", callback_data=NAV_CREATE_CALLBACK),
        types.InlineKeyboardButton(
            "👥 Управление", callback_data=NAV_CLIENTS_MANAGE_CALLBACK
        ),
    )

    kb.add(
        types.InlineKeyboardButton(
            "✏️ Сменить имя",
            callback_data=NAV_CLIENTS_RENAME_CALLBACK,
        ),
        types.InlineKeyboardButton("🔗 Привязки", callback_data="bindings_menu"),
    )

    kb.add(
        types.InlineKeyboardButton(
            "🎫 Тикеты", callback_data=NAV_ADMIN_TICKETS_CALLBACK
        ),
        types.InlineKeyboardButton(
            "🏠 Главное меню",
            callback_data=NAV_HOME_CALLBACK,
        ),
    )

    return kb


def clients_manage_menu_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.add(
        types.InlineKeyboardButton(
            "⚡ VLESS",
            callback_data=NAV_CLIENTS_VLESS_CALLBACK,
        ),
        types.InlineKeyboardButton(
            "🛡 AWG",
            callback_data=NAV_CLIENTS_AWG_CALLBACK,
        ),
    )

    kb.add(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        )
    )

    return kb


def manage_menu_kb():
    """Подменю: Сеть и безопасность."""
    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.add(
        types.InlineKeyboardButton(
            "🔐 SSH",
            callback_data="ssh_menu",
        ),
        types.InlineKeyboardButton(
            "🔒 Fail2ban",
            callback_data=FAIL2BAN_MENU_CALLBACK,
        ),
    )

    kb.add(
        types.InlineKeyboardButton(
            "🌐 Сеть",
            callback_data=NAV_NETWORK_CALLBACK,
        ),
        types.InlineKeyboardButton(
            "🏠 Главное меню",
            callback_data=NAV_HOME_CALLBACK,
        ),
    )

    return kb


def system_menu_kb():
    """Подменю: Службы (все рестарты + логи + процессы + AI-диагностика)"""
    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.add(
        types.InlineKeyboardButton("🔁 Рестарт ZverTBot", callback_data="restart_bot"),
        types.InlineKeyboardButton("📜 Логи ZverTBot", callback_data="log_bot"),
    )

    kb.add(
        types.InlineKeyboardButton("🔁 Рестарт AWG", callback_data="restart_awg"),
        types.InlineKeyboardButton("📜 Логи AWG", callback_data="log_awg"),
    )

    kb.add(
        types.InlineKeyboardButton("🔁 Рестарт Xray", callback_data="restart_xray"),
        types.InlineKeyboardButton("📜 Логи Xray", callback_data="log_xray"),
    )

    kb.add(
        types.InlineKeyboardButton("📊 Процессы", callback_data=PROCESS_MENU_CALLBACK),
        types.InlineKeyboardButton(
            "🤖 AI-диагностика",
            callback_data=NAV_AI_LOGS_CALLBACK,
        ),
    )

    kb.add(
        types.InlineKeyboardButton("🧹 Очистка диска", callback_data="confirm_cleanup"),
        types.InlineKeyboardButton("🏠 Главное меню", callback_data=NAV_HOME_CALLBACK),
    )

    return kb


def ssh_menu_kb():
    """Подменю: SSH-управление (2 колонки)"""
    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.add(
        types.InlineKeyboardButton("🔑 Список ключей", callback_data="ssh_list"),
        types.InlineKeyboardButton("📜 История входов", callback_data="ssh_history"),
    )

    kb.add(
        types.InlineKeyboardButton("🗑️ Удалить ключ", callback_data="ssh_delete"),
        types.InlineKeyboardButton("📥 Экспорт", callback_data="ssh_export"),
    )

    kb.add(
        types.InlineKeyboardButton("↩️ Назад", callback_data=NAV_BACK_CALLBACK),
    )

    return kb


def processes_menu_kb():
    """Подменю: Мониторинг процессов (одна кнопка + переключатель)"""
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(
            "📊 Топ процессов",
            callback_data=PROCESS_TOP_CALLBACK,
        )
    )
    kb.add(
        types.InlineKeyboardButton(
            "🔍 Поиск процесса",
            callback_data=PROCESS_SEARCH_CALLBACK,
        ),
        types.InlineKeyboardButton(
            "🛑 Завершить процесс",
            callback_data=PROCESS_KILL_CALLBACK,
        ),
    )
    kb.add(types.InlineKeyboardButton("↩️ Назад", callback_data=NAV_BACK_CALLBACK))
    return kb


def fail2ban_menu_kb():
    """Подменю: Fail2ban."""
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(
            "📜 Логи банов",
            callback_data=FAIL2BAN_LOGS_CALLBACK,
        ),
        types.InlineKeyboardButton(
            "🔓 Разбан IP",
            callback_data=FAIL2BAN_UNBAN_CALLBACK,
        ),
    )
    kb.add(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        )
    )
    return kb


def network_menu_kb():
    """Подменю: Сетевые инструменты (4 кнопки)"""
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🚀 Speedtest", callback_data="speedtest"),
        types.InlineKeyboardButton(
            "🔍 Мой внешний IP",
            callback_data="my_external_ip",
        ),
    )
    kb.add(
        types.InlineKeyboardButton(
            "🔍 Сканирование портов",
            callback_data="port_scan",
        ),
        types.InlineKeyboardButton(
            "📡 MTR диагностика",
            callback_data="net_mtr",
        ),
    )
    kb.add(
        types.InlineKeyboardButton("🌐 Репутация IP", callback_data="ip_reputation"),
        types.InlineKeyboardButton("↩️ Назад", callback_data=NAV_BACK_CALLBACK),
    )
    return kb


def backups_menu_kb():
    """Подменю: Резервное копирование (2 кнопки в ряд)"""
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(
            "💾 Создать бэкап",
            callback_data="create_backup",
        ),
        types.InlineKeyboardButton(
            "📜 История бэкапов",
            callback_data=NAV_BACKUP_HISTORY_CALLBACK,
        ),
    )
    kb.add(
        types.InlineKeyboardButton(
            "🏠 Главное меню",
            callback_data=NAV_HOME_CALLBACK,
        )
    )
    return kb


def analytics_menu_kb():
    """Подменю: Аналитика и отчёты (4 кнопки + Назад)"""
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(
            "📊 Отчёт по трафику",
            callback_data="weekly_report",
        ),
        types.InlineKeyboardButton(
            "📈 Статистика бота",
            callback_data="bot_stats",
        ),
    )
    kb.add(
        types.InlineKeyboardButton(
            "📜 История действий",
            callback_data="show_history",
        ),
        types.InlineKeyboardButton(
            "🛡 Паспорт сервера",
            callback_data="passport_check",
        ),
    )
    kb.add(
        types.InlineKeyboardButton(
            "🏠 Главное меню",
            callback_data=NAV_HOME_CALLBACK,
        )
    )
    return kb


def log_close_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("❌ Закрыть", callback_data="close_log"))
    return kb


def protocol_list_kb(proto, users):
    """Клавиатура списка клиентов протокола.

    AWG: 3 кнопки (🗑 | 📤 QR | 📊 Статистика) — без конфига.
    VLESS: 4 кнопки (🗑 | 📤 QR | 📄 Config + rules | 📊 Stats).
    """
    kb = types.InlineKeyboardMarkup(row_width=4 if proto == "vless" else 3)

    for u in users:
        if proto == "vless":
            vless_ports = xray_get_ports(u)
            port_text = ", ".join(map(str, vless_ports))
            kb.add(
                types.InlineKeyboardButton(
                    f"{u} [{port_text}] 🗑" if port_text else f"{u} 🗑",
                    callback_data=f"ask_del:{proto}:{u}",
                ),
                types.InlineKeyboardButton(
                    "📤 QR",
                    callback_data=f"qr:{proto}:{u}",
                ),
                types.InlineKeyboardButton(
                    "📄 Сonfig + rules",
                    callback_data=f"conf:{proto}:{u}",
                ),
                types.InlineKeyboardButton(
                    "📊 Stats",
                    callback_data=f"stats_{proto}_{u}",
                ),
            )
        else:
            kb.add(
                types.InlineKeyboardButton(
                    f"{u} 🗑",
                    callback_data=f"ask_del:{proto}:{u}",
                ),
                types.InlineKeyboardButton(
                    "📤 QR + config",
                    callback_data=f"qr:{proto}:{u}",
                ),
                types.InlineKeyboardButton(
                    "📊 Статистика",
                    callback_data=f"stats_{proto}_{u}",
                ),
            )

    # Поиск и возврат — в одной строке
    kb.add(
        types.InlineKeyboardButton(
            "🔍 Поиск",
            callback_data=(
                NAV_CLIENTS_SEARCH_VLESS_CALLBACK
                if proto == "vless"
                else NAV_CLIENTS_SEARCH_AWG_CALLBACK
            ),
        ),
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        ),
    )

    return kb


def client_card_kb(proto, username):
    kb = types.InlineKeyboardMarkup(row_width=2)

    if proto == "awg":
        # AWG: QR уже выдаёт QR + конфиг.
        kb.add(
            types.InlineKeyboardButton(
                "📤 QR + Конфиг",
                callback_data=f"qr:{proto}:{username}",
            )
        )
    else:
        # VLESS: QR и конфиг остаются отдельными действиями.
        kb.add(
            types.InlineKeyboardButton(
                "📤 QR",
                callback_data=f"qr:{proto}:{username}",
            ),
            types.InlineKeyboardButton(
                "📄 Конфиг",
                callback_data=f"conf:{proto}:{username}",
            ),
        )

    kb.add(
        types.InlineKeyboardButton(
            "🏠 Главное меню",
            callback_data=NAV_HOME_CALLBACK,
        )
    )
    return kb


# ============================================================
# CLIENT MENUS
# ============================================================


def client_accounts_kb(client_list, users_vless=None, users_awg=None):
    """
    Главное меню клиента: выбор аккаунтов.
    """

    from telebot import types

    users_vless = users_vless or []
    users_awg = users_awg or []

    kb = types.InlineKeyboardMarkup(row_width=2)

    buttons = []

    for acc in client_list:
        icon = "🚀" if acc in users_vless else "🛡️"
        buttons.append(
            types.InlineKeyboardButton(
                f"{icon} {acc}", callback_data=f"client:account:{acc}"
            )
        )

    if buttons:
        kb.add(*buttons)

    kb.add(
        types.InlineKeyboardButton("🆘 Создать тикет", callback_data="create_ticket"),
        types.InlineKeyboardButton(
            "📖 Инструкция", callback_data=NAV_CLIENT_HELP_CALLBACK
        ),
    )

    return kb


def client_account_kb(username, proto):
    """
    Меню выбранного аккаунта.
    """

    from telebot import types

    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.add(
        types.InlineKeyboardButton(
            "📊 Статистика", callback_data=f"client:stats:{username}"
        ),
        types.InlineKeyboardButton(
            "📱 QR-код", callback_data=f"{CLIENT_CONF_CALLBACK_PREFIX}{username}"
        ),
    )

    if proto == "vless":
        kb.add(
            types.InlineKeyboardButton(
                "🆘 Создать тикет", callback_data="create_ticket"
            ),
            types.InlineKeyboardButton(
                "📦 Конфигурация + RU",
                callback_data=f"{CLIENT_CONF_RU_CALLBACK_PREFIX}{username}",
            ),
        )
    else:
        kb.add(
            types.InlineKeyboardButton(
                "🆘 Создать тикет", callback_data="create_ticket"
            ),
            types.InlineKeyboardButton(
                "📖 Инструкция", callback_data=NAV_CLIENT_HELP_CALLBACK
            ),
        )

    if proto == "vless":
        kb.add(
            types.InlineKeyboardButton(
                "📖 Инструкция", callback_data=NAV_CLIENT_HELP_CALLBACK
            )
        )

    return kb


def ai_diagnosis_menu_kb():
    """Подменю: AI-диагностика логов (ZverTBot/AWG/Xray)"""
    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.add(
        types.InlineKeyboardButton("🤖 ZverTBot", callback_data="ai_log_bot"),
        types.InlineKeyboardButton("🛡 AWG", callback_data="ai_log_awg"),
    )

    kb.add(
        types.InlineKeyboardButton("⚡ Xray", callback_data="ai_log_xray"),
        types.InlineKeyboardButton("🖥 Сервер", callback_data="ai_server_health"),
    )

    kb.add(
        types.InlineKeyboardButton("↩️ Назад", callback_data=NAV_BACK_CALLBACK),
    )

    return kb
