"""
services/stats.py
Модуль для формирования текстов статистики через Telegram-бот.
Функции: статистика бота, статистика клиента, статус VPS.
"""

from config import BOT_NAME, BOT_VERSION
from core.navigation import NAV_BACK_CALLBACK, NAV_HOME_CALLBACK
from data.storage import load_awg_registry, load_stats
from data.traffic import get_client_traffic, load_usage
from services.awg.runtime import get_runtime_peers
from services.vps_status_source import load_prepared_vps_payload
from utils.helpers import fmt_traffic
from utils.logger import logger


def _build_status_text():
    BT = chr(96)
    NL = chr(10)

    try:
        data = load_prepared_vps_payload()
        if not data:
            return "❌ Ошибка: не удалось загрузить VPS статистику"

        uptime_seconds = int(data.get("uptime_seconds", 0))
        d, remainder = divmod(uptime_seconds, 86400)
        h, remainder = divmod(remainder, 3600)
        m, _ = divmod(remainder, 60)

        cpu_pct = f"{data.get('cpu', 0):.1f}%"
        ram_pct = f"{data.get('mem', 0):.1f}%"

        disk_val = data.get("disk", {})
        disk_pct = (
            f"{disk_val.get('percent', 0):.1f}%"
            if isinstance(disk_val, dict)
            else f"{disk_val:.1f}%"
        )

        traffic = f"{BT}{data.get('vpn_total_gb', 0):.2f} GB{BT}"

        swap = data.get("swap", {})
        if isinstance(swap, dict):
            swap_used_mb = swap.get("used_mb", 0)
            swap_pct = f"{swap.get('percent', 0):.1f}%"
        else:
            swap_used_mb = 0
            swap_pct = "0.0%"

        procs = data.get("processes", 0)

        svc_dict = data.get("services", {})
        svc_lines = []

        for service, service_data in svc_dict.items():
            if isinstance(service_data, dict):
                state = service_data.get("status", -1)
                uptime = service_data.get("uptime")
            else:
                state = service_data
                uptime = None

            if state == 1:
                icon = "🟢"
                status = uptime or "работает"
            elif state == 0:
                icon = "🟡"
                status = "остановлен"
            else:
                icon = "⚪"
                status = "не установлен"

            svc_lines.append(f"{icon} {BT}{service}{BT} — {status}")

        return (
            f"📊 *VPS ОТЧЕТ:*{NL}"
            f"🐺 {BOT_NAME}: v{BOT_VERSION}{NL}{NL}"
            f"🟢 Uptime: {BT}{int(d)}д {int(h)}ч {int(m)}м{BT}{NL}"
            f"🌡 CPU: {BT}{cpu_pct}{BT}{NL}"
            f"💾 RAM: {BT}{ram_pct}{BT}{NL}"
            f"🔄 Swap: {BT}{swap_used_mb}MB ({swap_pct}){BT}{NL}"
            f"⌚ Процессы: {BT}{procs}{BT}{NL}"
            f"💿 Disk: {BT}{disk_pct}{BT}{NL}"
            f"📈 Трафик: {traffic}{NL}"
            f"🔹 Службы:{NL}{NL.join(svc_lines)}"
        )
    except Exception as e:
        return f"❌ Ошибка: {BT}{e!s}{BT}"


def get_status_text():
    return _build_status_text()


def get_bot_stats_text():
    CMD_NAMES = {
        "services_menu": "🔧 Службы",
        "network_menu": "🌐 Сеть",
        "backups_menu": "💾 Бэкапы",
        "analytics_menu": "📊 Аналитика",
        "restart_xray": "🔁 Перезапуск Xray",
        "restart_awg": "🔁 Перезапуск AWG",
        "restart_bot": "🔁 Перезапуск бота",
        "log_xray": "📜 Лог Xray",
        "log_awg": "📜 Лог AWG",
        "log_bot": "📜 Лог бота",
        "speedtest": "🚀 Speedtest",
        "my_external_ip": "🔍 Мой внешний IP",
        "create_backup": "💾 Создать бэкап",
        "backup_history": "📜 История бэкапов",
        "weekly_report": "📊 Недельный отчёт",
        "bot_stats": "📈 Статистика бота",
        "add_vless": "➕ Создать VLESS",
        "add_awg": "➕ Создать AWG",
        "confirm_cleanup": "🧹 Очистка диска",
        "exec_cleanup": "🧹 Выполнить очистку",
        "show_history": "📜 История действий",
        "list_menu": "📋 Список",
        "manage_menu": "⚙️ Меню управления",
        "status": "🖥️ Статус VPS",
        "bindings_menu": "🔗 Меню привязок",
        "hide": "🚫 Скрыть меню",
        "fail2ban_menu": "🔒 Fail2ban",
        "fail2ban_status": "📊 Статус Fail2ban",
        "fail2ban_logs": "📜 Логи банов",
        "fail2ban_unban": "🔓 Разбан IP",
        "processes_menu": "📊 Процессы",
        "process_search": "🔍 Поиск процесса",
        "process_kill": "🛑 Завершить процесс",
        "port_scan": "🔍 Сканировать порты",
        "ssh_menu": "🔐 SSH-ключи",
        "ssh_list": "🔑 Список ключей",
        "ssh_history": "📜 История входов",
        "ssh_delete": "🗑️ Удалить ключ",
        "ssh_export": "📥 Экспорт ключей",
        "bindings_active": "🔗 Активные привязки",
        "bindings_pending": "⏳ Ожидающие привязки",
        "client_back_menu": "↩️ Назад к клиенту",
        "client_help": "❓ Помощь по клиенту",
        "client_rules": "📏 Правила клиента",
        "close_log": "❌ Закрыть лог",
        "request_bind": "🔗 Запрос привязки",
        NAV_BACK_CALLBACK: "↩️ Назад",
        NAV_HOME_CALLBACK: "🏠 Главное меню",
        "system_menu": "⚙️ Системное меню",
    }
    try:
        stats = load_stats()
        commands = stats.get("commands", {})
        total = stats.get("total_commands", 0)
        start_date = stats.get("start_date", "N/A")
        if not commands:
            return (
                "📊 *Статистика бота*\n"
                "❌ Статистика пуста\n"
                "💡 Используйте бота — статистика будет собираться автоматически"
            )
        sorted_commands = sorted(
            commands.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]
        NL = chr(10)
        BT = chr(96)
        text = f"📊 *Статистика использования бота*{NL}"
        text += f"📅 *Сбор данных с:* {BT}{start_date}{BT}{NL}"
        text += f"🔢 *Всего команд:* {BT}{total}{BT}{NL}"
        text += f"🏆 *Топ-10 команд:*{NL}"
        for i, (cmd, count) in enumerate(sorted_commands, 1):
            cmd_display = CMD_NAMES.get(cmd, cmd.replace("_", " ").title())
            percent = (count / total * 100) if total > 0 else 0
            text += f"{i}. {cmd_display} — {count} ({percent:.1f}%){NL}"
        return text
    except Exception as e:
        logger.error(
            "stats.bot.generate_failed | error=%s",
            e,
        )
        return f"❌ Ошибка чтения статистики: {e}"


def get_client_stats_text(username, proto):
    NL = chr(10)
    BT = chr(96)
    if proto == "awg":
        reg = load_awg_registry()
        if username not in reg:
            return "❌ Клиент не найден"
        ip = reg[username].get("ip")
        if not ip:
            return "❌ Нет IP"
        traffic = get_client_traffic(username)
        up, down, total = traffic["uplink"], traffic["downlink"], traffic["total"]
        handshake = "Не в сети"
        is_online = False
        try:
            runtime_peers = get_runtime_peers()
            for peer in runtime_peers.values():
                if peer.allowed_ip == ip:
                    if peer.latest_handshake and peer.latest_handshake != "never":
                        handshake = peer.latest_handshake
                        is_online = True
                    break
        except Exception as e:
            logger.exception(
                "stats.client.awg_status_failed | username=%s | error=%s",
                username,
                e,
            )
        if is_online:
            return (
                f"📊 *Статистика: {username}*{NL}"
                f"🔹 Статус: ✅ Активен{NL}"
                f"🔹 IP: {BT}{ip}{BT}{NL}"
                f"🔹 Рукопожатие: {BT}{handshake}{BT}{NL}"
                f"⬇️ Получено: {BT}{fmt_traffic(down)}{BT}{NL}"
                f"⬆️ Отправлено: {BT}{fmt_traffic(up)}{BT}{NL}"
                f"🔹 Итого: {BT}{fmt_traffic(total)}{BT}"
            )
        else:
            return (
                f"📊 *Статистика: {username}*{NL}"
                f"🔹 Статус: ⚫ Оффлайн{NL}"
                f"🔹 IP: {BT}{ip}{BT}{NL}"
                f"⬇️ Получено: {BT}{fmt_traffic(down)}{BT}{NL}"
                f"⬆️ Отправлено: {BT}{fmt_traffic(up)}{BT}{NL}"
                f"🔹 Итого: {BT}{fmt_traffic(total)}{BT}"
            )
    elif proto == "vless":
        data = load_usage()
        if not data:
            return "⏳ Ожидание сбора..."
        client = data.get("clients", {}).get(username)
        if client is None:
            return f"⏳ Сбор данных... ({data.get('updated', 'N/A').split('T')[0]})"
        up = client.get("uplink", 0)
        down = client.get("downlink", 0)
        total = client.get("total", 0)
        return (
            f"📊 *Статистика: {username}*{NL}"
            f"⬆️ Отправлено: {BT}{fmt_traffic(up)}{BT}{NL}"
            f"⬇️ Получено: {BT}{fmt_traffic(down)}{BT}{NL}"
            f"🔹 Итого: {BT}{fmt_traffic(total)}{BT}"
        )
    return "❌ Неизвестный протокол"
