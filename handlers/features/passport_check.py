"""
Обработчик проверки паспорта сервера.
"""

import os
import re
import subprocess
import time

from telebot import types

from config.paths import PROJECT_ROOT
from core.callback_response import CallbackResponse
from core.navigation import NAV_BACK_CALLBACK
from utils.error_handler import handle_errors
from utils.logger import logger

PASSPORT_TIMEOUT = 30

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Удаляет ANSI escape-коды из текста."""
    return ANSI_RE.sub("", text)


REPORT_DIR = "/tmp/zvertbot_reports"
os.makedirs(REPORT_DIR, exist_ok=True)


@handle_errors("Ошибка в handle_passport_check")
def handle_passport_check(bot, cid, call, data):
    """Обрабатывает проверку паспорта сервера и выдачу отчёта"""

    if data == "passport_check":
        try:
            result = subprocess.run(
                [
                    str(PROJECT_ROOT / ".venv" / "bin" / "python"),
                    str(PROJECT_ROOT / "scripts" / "check_passport.py"),
                ],
                capture_output=True,
                text=True,
                timeout=PASSPORT_TIMEOUT,
                cwd=str(PROJECT_ROOT / "scripts"),
            )
            output = strip_ansi(result.stdout + result.stderr)

            lines = output.strip().split("\n")

            key_lines = [
                line.strip()
                for line in lines
                if any(
                    line.strip().startswith(prefix)
                    for prefix in (
                        "Всего проверок:",
                        "Успешно:",
                        "Предупреждений:",
                        "Ошибок:",
                        "❌ СЕРВЕР НЕ ГОТОВ",
                        "⚠️ СЕРВЕР ГОТОВ С ПРЕДУПРЕЖДЕНИЯМИ",
                        "✅ СЕРВЕР ГОТОВ К ИСПОЛЬЗОВАНИЮ",
                    )
                )
            ]

            if key_lines:
                summary_text = "\n".join(key_lines)
            else:
                summary_text = "Не удалось сформировать краткий итог."

            # Сохраняем полный отчёт во временный файл
            timestamp = int(time.time())
            filename = f"passport_{cid}_{timestamp}.txt"
            filepath = os.path.join(REPORT_DIR, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(output)

            kb = types.InlineKeyboardMarkup(row_width=1)
            kb.add(
                types.InlineKeyboardButton(
                    "📄 Скачать полный отчёт",
                    callback_data=f"get_passport_file:{filename}",
                )
            )
            kb.add(
                types.InlineKeyboardButton(
                    "↩️ Назад",
                    callback_data=NAV_BACK_CALLBACK,
                )
            )

            bot.edit_message_text(
                f"🛡 ПАСПОРТ СЕРВЕРА\n\n{summary_text}",
                cid,
                call.message.message_id,
                reply_markup=kb,
            )
        except subprocess.TimeoutExpired:
            bot.edit_message_text(
                f"⏱ Превышено время ожидания проверки ({PASSPORT_TIMEOUT}с).",
                cid,
                call.message.message_id,
            )
        except Exception as e:
            logger.error("passport_check.failed | error=%s", e)
            bot.edit_message_text(
                f"❌ Ошибка при проверке: {e}", cid, call.message.message_id
            )
        return CallbackResponse("Проверяю паспорт сервера...")

    if data.startswith("get_passport_file:"):
        filename = data.split(":", 1)[1]
        filepath = os.path.join(REPORT_DIR, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, "rb") as f:
                    bot.send_document(
                        cid, f, caption="📄 Полный отчёт проверки паспорта сервера"
                    )
                return CallbackResponse("Отчёт отправлен в чат!")
            except Exception as e:
                logger.error("passport_check.file_send.failed | error=%s", e)
                return CallbackResponse(
                    "Ошибка отправки файла",
                    show_alert=True,
                )
        else:
            return CallbackResponse(
                "Файл не найден или устарел",
                show_alert=True,
            )

    return False
