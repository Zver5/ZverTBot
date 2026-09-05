"""
services/processes.py
Модуль для мониторинга процессов через Telegram-бот.
Функции: топ процессов по CPU/RAM, поиск, завершение.
"""

import os
import subprocess
import time

from utils.logger import logger
from utils.validators import validate_pid


def get_top_processes(sort_by="cpu", limit=10):
    """Получает топ процессов по CPU или RAM (исключая ps aux и grep)"""
    try:
        sort_key = "-%cpu" if sort_by == "cpu" else "-%mem"
        result = subprocess.run(
            ["ps", "aux", f"--sort={sort_key}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        lines = result.stdout.strip().split("\n")
        processes = []
        # Увеличиваем лимит для компенсации фильтрации
        max_lines = limit + 10
        for line in lines[1 : max_lines + 1]:
            # Исключаем ps aux и grep (артефакты измерения)
            if "ps aux" in line or "ps  aux" in line:
                continue
            if line.strip().startswith("grep"):
                continue

            parts = line.split(None, 10)
            if len(parts) >= 11:
                try:
                    proc = {
                        "user": parts[0],
                        "pid": parts[1],
                        "cpu": float(parts[2]),
                        "mem": float(parts[3]),
                        "vsz": int(parts[4]) // 1024,
                        "rss": int(parts[5]) // 1024,
                        "stat": parts[7],
                        "start": parts[8],
                        "time": parts[9],
                        "command": parts[10][:60],
                    }
                    processes.append(proc)
                    if len(processes) >= limit:
                        break
                except (ValueError, IndexError):
                    continue
        return processes
    except Exception as e:
        logger.error(
            "processes.list.failed | error=%s",
            e,
        )
        return []


def format_processes_text(sort_by="cpu"):
    """Форматирует текст с топ-процессами"""
    try:
        processes = get_top_processes(sort_by=sort_by, limit=10)
        if not processes:
            return "❌ Не удалось получить список процессов"
        sort_text = "🔥 CPU" if sort_by == "cpu" else "💾 RAM"
        text = f"📊 *Топ-10 процессов ({sort_text})*\n"
        for i, proc in enumerate(processes, 1):
            cmd = proc["command"]
            if len(cmd) > 50:
                cmd = cmd[:47] + "..."
            cmd = cmd.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")
            text += f"*{i}.* `{proc['pid']}` {cmd}\n"
            text += (
                f"   👤 {proc['user']} | 💻 {proc['cpu']}% | "
                f"🧠 {proc['mem']}% | 💿 {proc['rss']}MB\n"
            )

        # Подсчёт общего CPU с учётом количества ядер
        total_cpu = sum(p["cpu"] for p in processes)
        total_mem = sum(p["mem"] for p in processes)
        total_rss = sum(p["rss"] for p in processes)

        # Количество ядер CPU
        cpu_cores = os.cpu_count() or 1

        text += "━━━━━━━━━━━━━━━━━━━━━\n"
        text += "📈 *Итого в топ-10:*\n"
        text += f"💻 CPU: {total_cpu:.1f}% (ядер: {cpu_cores})\n"
        text += f"🧠 RAM: {total_mem:.1f}% ({total_rss} MB)\n"
        return text
    except Exception as e:
        logger.error(
            "processes.format.failed | error=%s",
            e,
        )
        return f"❌ Ошибка: {e}"


def kill_process_by_pid(pid):
    """Завершает процесс по PID"""
    try:
        if not validate_pid(pid):
            return False, "❌ Неверный формат PID"
        result = subprocess.run(["ps", "-p", str(pid)], capture_output=True, text=True)
        if result.returncode != 0:
            return False, f"❌ Процесс {pid} не найден"
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "user,comm"], capture_output=True, text=True
        )
        proc_info = result.stdout.strip().split("\n")[-1]
        result = subprocess.run(
            ["kill", "-15", str(pid)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False, f"❌ Ошибка завершения: {result.stderr}"
        time.sleep(2)
        result = subprocess.run(["ps", "-p", str(pid)], capture_output=True, text=True)
        if result.returncode == 0:
            subprocess.run(["kill", "-9", str(pid)], capture_output=True, text=True)
            return True, (
                f"⚠️ Процесс {pid} завершён принудительно (SIGKILL)\n📋 `{proc_info}`"
            )
        else:
            return True, (
                f"✅ Процесс {pid} завершён успешно (SIGTERM)\n📋 `{proc_info}`"
            )
    except Exception as e:
        return False, f"❌ Ошибка: {e}"


def search_process_by_name(name):
    """Ищет процессы по имени"""
    try:
        if not name or len(name) < 2:
            return "❌ Введите минимум 2 символа для поиска"
        result = subprocess.run(
            ["pgrep", "-a", "-i", name], capture_output=True, text=True
        )
        if result.returncode != 0 or not result.stdout.strip():
            return f"🔍 *Поиск:* `{name}`\n❌ Процессы не найдены"
        lines = result.stdout.strip().split("\n")[:10]
        text = f"🔍 *Поиск:* `{name}`\n"
        text += f"📊 Найдено: {len(lines)} процессов\n"
        for line in lines:
            parts = line.split(None, 1)
            if len(parts) == 2:
                pid, cmd = parts
                cmd = (
                    cmd[:60].replace("*", "\\*").replace("`", "\\`")
                )
                text += f"`{pid}` {cmd}\n"
        return text
    except Exception as e:
        logger.error(
            "processes.search.failed | error=%s",
            e,
        )
        return f"❌ Ошибка: {e}"
