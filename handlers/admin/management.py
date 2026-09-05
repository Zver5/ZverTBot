"""
Обработчики управления службами: рестарты, логи, очистка, бэкапы, статистика.
Все долгие операции вынесены в потоки.
"""

import json
import subprocess
import sys
import threading
import time

from telebot import types

from config import SERVER_IP
from config.paths import (
    BACKUP_REMOTE,
    BACKUP_ROOT_DIR,
    BACKUP_SCRIPT,
    RCLONE_STATUS_JSON,
)
from core.bot import bot
from core.callback_response import CallbackResponse
from core.navigation import NAV_BACK_CALLBACK, navigation
from core.state import LAST_STATUS_MSGS
from data.traffic import load_usage
from handlers.admin.navigation import render_navigation_screen
from services.backup import format_msk_time, get_backup_history_text
from services.client_service import show_history_action
from services.ip_server import start_ip_server_once
from services.ip_tokens import create_ip_token
from services.llm_diagnosis import analyze_logs_with_llm
from services.server_health import collect_server_health
from services.stats import (
    get_bot_stats_text,
    get_client_stats_text,
    get_status_text,
)
from services.system import get_service_logs, run_disk_cleanup, run_speedtest_and_ip
from ui.keyboards import (
    ai_diagnosis_menu_kb,
    log_close_kb,
    manage_menu_kb,  # noqa: F401 — имя патчится тестами
    system_menu_kb,
)
from ui.screens import ACTION_HISTORY, CLEANUP, SPEEDTEST
from utils.error_handler import handle_errors
from utils.helpers import escape_md, fmt_traffic, safe_delete, safe_edit_message
from utils.logger import logger
from utils.notifications import log_action
from utils.service_control import (
    restart_service,
    restart_service_detached,
    service_exists,
)

BACKUP_TIMEOUT = 300
STATUS_AUTO_DELETE = 12

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ЗАПУСКА В ПОТОКЕ ----------


def _run_service_restart(service, name, cid, message_id):
    """Перезапуск службы в фоне"""
    try:
        if not service_exists(service):
            safe_edit_message(
                bot,
                f"⚠️ {name} не установлен.",
                cid,
                message_id,
                reply_markup=system_menu_kb(),
            )
            return

        safe_edit_message(bot, f"⏳ Перезапуск {name}...", cid, message_id)
        restart_service(service)
        log_action("РЕСТАРТ", name, "SUCCESS")
        safe_edit_message(
            bot,
            f"✅ {name} перезапущен!",
            cid,
            message_id,
            reply_markup=system_menu_kb(),
        )
    except subprocess.TimeoutExpired:
        safe_edit_message(
            bot,
            f"⚠️ Таймаут перезапуска {name}",
            cid,
            message_id,
            reply_markup=system_menu_kb(),
        )
    except Exception as e:
        log_action("ОШИБКА РЕСТАРТА", name, "ERROR", str(e))

        safe_edit_message(
            bot,
            f"❌ Ошибка перезапуска {name}: {str(e)[:150]}",
            cid,
            message_id,
            reply_markup=system_menu_kb(),
        )


def _run_speedtest(cid, message_id):
    """Запуск speedtest в фоне"""
    try:
        result = run_speedtest_and_ip()
        if "Speedtest Result" in result:
            log_action("SPEEDTEST", "Тест скорости", "SUCCESS")
        else:
            log_action("SPEEDTEST", "Тест скорости", "ERROR", result[:100])
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton(
                "↩️ Назад",
                callback_data=NAV_BACK_CALLBACK,
            )
        )
        safe_edit_message(
            bot,
            result,
            cid,
            message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )
    except Exception as e:
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton(
                "↩️ Назад",
                callback_data=NAV_BACK_CALLBACK,
            )
        )
        safe_edit_message(
            bot,
            f"❌ Ошибка speedtest: {e}",
            cid,
            message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )


def _run_status(cid, message_id):
    """Показывает статус VPS в фоне"""
    try:
        txt = get_status_text()
        # Удаляем предыдущее сообщение статуса (защита от дублей)
        if cid in LAST_STATUS_MSGS:
            safe_delete(bot, cid, LAST_STATUS_MSGS[cid])
        try:
            msg = bot.send_message(cid, txt, parse_mode="Markdown")
        except Exception as e:
            log_action("ОШИБКА ОТПРАВКИ СТАТУСА", str(cid), "ERROR", str(e))
            safe_edit_message(
                bot,
                f"❌ Ошибка отправки статуса: {e}",
                cid,
                message_id,
            )
            return
        LAST_STATUS_MSGS[cid] = msg.message_id
        threading.Timer(
            STATUS_AUTO_DELETE,
            lambda: safe_delete(bot, cid, msg.message_id),
        ).start()
        # Удаляем сообщение с кнопкой (оно уже не нужно)
        safe_delete(bot, cid, message_id)
    except Exception as e:
        safe_edit_message(bot, f"❌ Ошибка статуса: {e}", cid, message_id)


def _run_weekly_report(cid, message_id):
    """Формирует недельный отчёт в фоне"""
    try:
        # Показываем "формирую"
        safe_edit_message(bot, "⏳ Формирую отчёт...", cid, message_id)
        from config.paths import USAGE_JSON

        if not USAGE_JSON.exists():
            safe_edit_message(
                bot,
                "❌ Файл статистики usage.json не найден.",
                cid,
                message_id,
            )
            return

        data = load_usage()

        clients = data.get("clients", {})
        if not clients:
            safe_edit_message(bot, "📊 Клиентов для отчёта пока нет.", cid, message_id)
            return
        sorted_clients = sorted(
            clients.items(),
            key=lambda x: x[1].get("total", 0),
            reverse=True,
        )
        top_7 = sorted_clients[:7]
        total_server_traffic = sum(c.get("total", 0) for c in clients.values())
        text = "📊 *ОТЧЁТ ПО ТРАФИКУ*\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n"
        text += f"🗓 Обновлено: `{data.get('updated', 'N/A').split('T')[0]}`\n"
        text += f"🌐 Общий трафик Xray и AWG: `{fmt_traffic(total_server_traffic)}`\n"
        text += "\n🏆 *ТОП-7 КЛИЕНТОВ*\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n"
        for i, (name, stats) in enumerate(top_7, 1):
            traffic = stats.get("total", 0)
            up = stats.get("uplink", 0)
            down = stats.get("downlink", 0)
            text += f"\n{i}️⃣ *{escape_md(name)}*\n"
            text += f"├ 🔹 Всего: `{fmt_traffic(traffic)}`\n"
            text += f"└ ⬆️ `{fmt_traffic(up)}` | ⬇️ `{fmt_traffic(down)}`\n"
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(
                "↩️ Назад",
                callback_data=NAV_BACK_CALLBACK,
            )
        )
        safe_edit_message(
            bot,
            text,
            cid,
            message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )
    except Exception as e:
        safe_edit_message(bot, f"❌ Ошибка формирования отчёта: {e}", cid, message_id)


def _run_bot_stats(cid, message_id):
    """Показывает статистику бота в фоне"""
    try:
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(
                "↩️ Назад",
                callback_data=NAV_BACK_CALLBACK,
            )
        )
        text = get_bot_stats_text()
        safe_edit_message(
            bot,
            text,
            cid,
            message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )
    except Exception as e:
        safe_edit_message(bot, f"❌ Ошибка: {e}", cid, message_id)


def render_backup_history(bot_instance, cid, message_id):
    """Отрисовать экран истории бэкапов."""
    try:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton(
                "💾 Создать бэкап",
                callback_data="create_backup",
            ),
            types.InlineKeyboardButton(
                "↩️ Назад",
                callback_data=NAV_BACK_CALLBACK,
            ),
        )
        text = get_backup_history_text()
        safe_edit_message(
            bot_instance,
            text,
            cid,
            message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )
        return True
    except Exception as e:
        log_action("ОШИБКА ИСТОРИИ БЭКАПОВ", "backup_history", "ERROR", str(e))
        return False


def _run_client_stats(cid, message_id, proto, username):
    """Показывает статистику клиента в фоне"""
    try:
        text = get_client_stats_text(username, proto)
        safe_edit_message(bot, text, cid, message_id, parse_mode="Markdown")
    except Exception as e:
        log_action("ОШИБКА СТАТИСТИКИ КЛИЕНТА", username, "ERROR", str(e))
        safe_edit_message(
            bot,
            f"❌ Ошибка получения статистики: {e}",
            cid,
            message_id,
        )


def _run_show_history(cid, message_id):
    """Показывает историю действий в фоне"""
    try:
        show_history_action(bot, cid, message_id)
    except Exception as e:
        log_action("ОШИБКА ИСТОРИИ", "show_history", "ERROR", str(e))
        safe_edit_message(
            bot,
            f"❌ Ошибка загрузки истории: {e}",
            cid,
            message_id,
        )


def _run_cleanup(cid, message_id):
    """Запуск очистки диска в фоне"""
    try:
        result = run_disk_cleanup()
        log_action("ОЧИСТКА", "disk", "SUCCESS", result)
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton(
                "↩️ Назад",
                callback_data=NAV_BACK_CALLBACK,
            )
        )
        safe_edit_message(
            bot,
            result,
            cid,
            message_id,
            parse_mode="Markdown",
            reply_markup=kb,
        )
    except Exception as e:
        log_action("ОШИБКА ОЧИСТКИ", "disk", "ERROR", str(e))
        safe_edit_message(
            bot,
            f"❌ Ошибка очистки: {e}",
            cid,
            message_id,
        )


def render_speedtest(bot_instance, cid, message_id):
    """Renderer экрана Speedtest."""
    safe_edit_message(
        bot_instance,
        "⏳ Запуск Speedtest ...",
        cid,
        message_id,
    )
    threading.Thread(
        target=_run_speedtest,
        args=(cid, message_id),
        daemon=True,
    ).start()
    return True


def render_cleanup(bot_instance, cid, message_id):
    """Renderer экрана подтверждения очистки диска."""
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(
            "✅ Выполнить",
            callback_data="exec_cleanup",
        ),
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        ),
    )
    safe_edit_message(
        bot_instance,
        "🧹 *Очистка диска*\n🗑 Удалить кэш пакетов (apt clean) и старые логи?",
        cid,
        message_id,
        parse_mode="Markdown",
        reply_markup=kb,
    )
    return True


def render_action_history(bot_instance, cid, message_id):
    """Renderer экрана истории действий."""
    threading.Thread(
        target=_run_show_history,
        args=(cid, message_id),
        daemon=True,
    ).start()
    return True


# -------------------------------------------------------------------


@handle_errors("Ошибка в handle_management_part1_callback")
def handle_management_part1_callback(bot, cid, call, data):
    """Обрабатывает управление часть 1: restart_, log_"""
    if data.startswith("restart_"):
        srv_data = {
            "restart_xray": ("xray", "Xray"),
            "restart_awg": ("awg-quick@awg0", "AWG"),
            "restart_bot": ("zvertbot", "Бот"),
        }
        if data in srv_data:
            srv, name = srv_data[data]
            response = CallbackResponse(f"Перезапуск {name}...")
            if srv == "zvertbot":
                log_action("РЕСТАРТ", "Бот", "SUCCESS")
                safe_delete(bot, cid, call.message.message_id)
                time.sleep(1)
                restart_service_detached("zvertbot")
                sys.exit(0)
            else:
                threading.Thread(
                    target=_run_service_restart,
                    args=(srv, name, cid, call.message.message_id),
                    daemon=True,
                ).start()
            return response

    if data.startswith("log_"):
        bot.send_message(
            cid,
            get_service_logs(data.replace("log_", "")),
            parse_mode="Markdown",
            reply_markup=log_close_kb(),
        )
        return CallbackResponse()

    return False


@handle_errors("Ошибка в handle_management_part2_callback")
def handle_management_part2_callback(bot, cid, call, data):
    """Обрабатывает управление часть 2: close_log, my_external_ip, speedtest"""
    if data == "close_log":
        try:
            safe_delete(bot, cid, call.message.message_id)
        except Exception as e:
            logger.exception("management.log.close_failed | error=%s", e)
        return CallbackResponse()

    if data == "my_external_ip":
        token = create_ip_token(cid)

        start_ip_server_once(
            bot,
            port=8085,
        )

        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(
                "👉 Нажми, чтобы узнать IP",
                url=f"http://{SERVER_IP}:8085/ip?token={token}",
            )
        )
        safe_edit_message(
            bot,
            "🌍 Нажмите кнопку ниже:",
            cid,
            call.message.message_id,
            reply_markup=kb,
        )
        threading.Timer(
            15,
            lambda: safe_delete(bot, cid, call.message.message_id),
        ).start()
        return CallbackResponse()

    if data == "speedtest":
        navigation.go(cid, SPEEDTEST)
        navigation.render(SPEEDTEST, bot, cid, call.message.message_id)
        return CallbackResponse("Запуск speedtest...")

    return False


@handle_errors("Ошибка в handle_management_part3_callback")
def handle_management_part3_callback(bot, cid, call, data):
    """Обрабатывает управление часть 3: confirm_cleanup, exec_cleanup, show_history"""
    if data == "confirm_cleanup":
        navigation.go(cid, CLEANUP)
        return bool(navigation.render(CLEANUP, bot, cid, call.message.message_id))

    if data == "exec_cleanup":
        safe_edit_message(
            bot, "🧹 Выполняется очистка... ⏳", cid, call.message.message_id
        )
        threading.Thread(
            target=_run_cleanup, args=(cid, call.message.message_id), daemon=True
        ).start()
        return CallbackResponse("Запускаю очистку...")

    if data == "show_history":
        navigation.go(cid, ACTION_HISTORY)
        navigation.render(ACTION_HISTORY, bot, cid, call.message.message_id)
        return CallbackResponse()

    return False


def run_manual_backup(bot, cid, message_id):
    """Запуск бэкапа в фоне с уведомлением о результате"""

    def _do_backup():
        try:
            result = subprocess.run(
                ["bash", BACKUP_SCRIPT],
                capture_output=True,
                text=True,
                timeout=BACKUP_TIMEOUT,
            )

            try:
                with open(RCLONE_STATUS_JSON) as f:
                    status = json.load(f)
                backup_name = status.get("file_name", "N/A")
                size_mb = status.get("size_mb", 0)

                if status.get("status") == "local_only":
                    text = (
                        f"⚠️ *Бэкап создан локально*\n\n"
                        f"📦 Файл: `{backup_name}`\n"
                        f"📏 Размер: `{size_mb} MB`\n\n"
                        f"☁️ Backup remote не настроен.\n"
                        f"Бэкап сохранён только на сервере."
                    )
                    log_action(
                        "БЭКАП СОЗДАН ТОЛЬКО ЛОКАЛЬНО",
                        backup_name,
                        "WARNING",
                        "Backup remote не настроен",
                    )

                elif result.returncode == 0:
                    text = (
                        f"✅ *Бэкап создан успешно!*\n\n"
                        f"📦 Файл: `{backup_name}`\n"
                        f"📏 Размер: `{size_mb} MB`\n"
                        f"☁️ Загружен на: `{BACKUP_REMOTE}:{BACKUP_ROOT_DIR}/configs/`\n"
                        f"📅 Время: "
                        f"`{format_msk_time(status.get('last_backup', '')) or 'N/A'}`"
                    )
                    log_action(
                        "СОЗДАНИЕ БЭКАПА",
                        backup_name,
                        "SUCCESS",
                        f"Размер: {size_mb} MB",
                    )
                else:
                    stderr = (result.stderr or "").lower()

                    if result.returncode == 127 and "rclone" in stderr:
                        text = (
                            f"⚠️ *Бэкап создан локально*\n\n"
                            f"📦 Файл: `{backup_name}`\n"
                            f"📏 Размер: `{size_mb} MB`\n\n"
                            f"☁️ rclone не установлен.\n"
                            f"Облачная отправка пропущена."
                        )
                        log_action(
                            "СОЗДАНИЕ БЭКАПА",
                            backup_name,
                            "WARNING",
                            "rclone не установлен",
                        )
                    elif (
                        result.returncode == 2 and backup_name and backup_name != "N/A"
                    ):
                        text = (
                            f"⚠️ *Бэкап создан только локально*\n"
                            f"📦 Файл: `{backup_name}`\n"
                            f"📏 Размер: `{size_mb} MB`\n"
                            f"☁️ В Облако/Яндекс Диск не загружен: отсутствует токен"
                        )
                        log_action(
                            "БЭКАП СОЗДАН ТОЛЬКО ЛОКАЛЬНО",
                            backup_name,
                            "WARNING",
                            "Отсутствует токен облачного хранилища",
                        )
                    else:
                        text = (
                            f"⚠️ *Бэкап создан с предупреждениями*\n\n"
                            f"📦 Файл: `{backup_name}`\n"
                            f"📏 Размер: `{size_mb} MB`\n\n"
                            f"⚠️ Код возврата: {result.returncode}"
                        )
                        log_action(
                            "СОЗДАНИЕ БЭКАПА",
                            backup_name,
                            "ERROR",
                            f"Код: {result.returncode}",
                        )
            except Exception as e:
                logger.exception("management.backup.status_failed | error=%s", e)
                if result.returncode == 0:
                    text = "✅ *Бэкап создан успешно!*\n\n⚠️ Не удалось прочитать статус"
                else:
                    text = (
                        "❌ *Ошибка бэкапа*\n\n"
                        f"Код: {result.returncode}\n"
                        f"`\n{result.stderr[:500]}\n`"
                    )

            kb = types.InlineKeyboardMarkup(row_width=1)
            kb.add(
                types.InlineKeyboardButton(
                    "↩️ Назад",
                    callback_data=NAV_BACK_CALLBACK,
                )
            )
            safe_edit_message(
                bot,
                text,
                cid,
                message_id,
                parse_mode="Markdown",
                reply_markup=kb,
            )

        except subprocess.TimeoutExpired:
            kb = types.InlineKeyboardMarkup(row_width=1)
            kb.add(
                types.InlineKeyboardButton(
                    "↩️ Назад",
                    callback_data=NAV_BACK_CALLBACK,
                )
            )
            safe_edit_message(
                bot,
                "❌ *Таймаут бэкапа* (>5 минут)",
                cid,
                message_id,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        except Exception as e:
            kb = types.InlineKeyboardMarkup(row_width=1)
            kb.add(
                types.InlineKeyboardButton(
                    "↩️ Назад",
                    callback_data=NAV_BACK_CALLBACK,
                )
            )
            safe_edit_message(
                bot,
                f"❌ *Ошибка бэкапа:* `{str(e)[:200]}`",
                cid,
                message_id,
                parse_mode="Markdown",
                reply_markup=kb,
            )

    threading.Thread(target=_do_backup, daemon=True).start()


@handle_errors("Ошибка в handle_management_part4_callback")
def handle_management_part4_callback(bot, cid, call, data):
    """Обрабатывает управление часть 4: weekly_report, status, stats_"""
    if data == "weekly_report":
        threading.Thread(
            target=_run_weekly_report, args=(cid, call.message.message_id), daemon=True
        ).start()
        return CallbackResponse()

    if data == "bot_stats":
        threading.Thread(
            target=_run_bot_stats, args=(cid, call.message.message_id), daemon=True
        ).start()
        return CallbackResponse()

    if data == "create_backup":
        safe_edit_message(
            bot,
            (
                "⏳ *Создаю бэкап...*\n\n"
                "Это может занять 1-3 минуты.\n"
                "Пожалуйста, не закрывайте чат."
            ),
            cid,
            call.message.message_id,
            parse_mode="Markdown",
        )
        run_manual_backup(bot, cid, call.message.message_id)
        return CallbackResponse("Запускаю бэкап...")

    if data == "backup_history":
        from ui.screens import BACKUP_HISTORY

        if navigation.current(cid) != BACKUP_HISTORY:
            navigation.go(cid, BACKUP_HISTORY)

        return render_navigation_screen(
            bot,
            cid,
            call.message.message_id,
            BACKUP_HISTORY,
        )

    if data == "status":
        # Запускаем в потоке
        threading.Thread(
            target=_run_status, args=(cid, call.message.message_id), daemon=True
        ).start()
        return CallbackResponse()

    if data.startswith("stats_"):
        parts = data.split("_", 2)
        if len(parts) == 3:
            proto, username = parts[1], parts[2]
            # Запускаем в потоке
            threading.Thread(
                target=_run_client_stats,
                args=(cid, call.message.message_id, proto, username),
                daemon=True,
            ).start()
            return CallbackResponse()

    return False


@handle_errors("Ошибка в handle_ai_diagnosis_callback")
def handle_ai_diagnosis_callback(bot, cid, call, data):
    """Обрабатывает AI-диагностику логов."""
    message_id = call.message.message_id

    if data == "ai_server_health":
        safe_edit_message(
            bot,
            "⏳ Анализирую состояние сервера...\nЭто может занять до 30 секунд.",
            cid,
            message_id,
            reply_markup=None,
        )

        try:
            health_report = collect_server_health()

            result = analyze_logs_with_llm(
                health_report,
                "server",
            )

            safe_edit_message(
                bot,
                result,
                cid,
                message_id,
                reply_markup=ai_diagnosis_menu_kb(),
            )

        except Exception as e:
            safe_edit_message(
                bot,
                f"❌ Ошибка анализа сервера: {str(e)[:200]}",
                cid,
                message_id,
                reply_markup=ai_diagnosis_menu_kb(),
            )

        return CallbackResponse()

    if data.startswith("ai_log_"):
        service_name = data.removeprefix("ai_log_")

        safe_edit_message(
            bot,
            f"⏳ Анализирую логи **{service_name}**...\nЭто может занять до 30 секунд.",
            cid,
            message_id,
            reply_markup=None,
        )

        try:
            logs = get_service_logs(service_name)
            result = analyze_logs_with_llm(logs, service_name)

            safe_edit_message(
                bot,
                result,
                cid,
                message_id,
                reply_markup=ai_diagnosis_menu_kb(),
            )
        except Exception as e:
            safe_edit_message(
                bot,
                f"❌ Ошибка диагностики: {str(e)[:200]}",
                cid,
                message_id,
                reply_markup=ai_diagnosis_menu_kb(),
            )

        return CallbackResponse()
