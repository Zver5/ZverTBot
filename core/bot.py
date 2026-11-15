"""
Инициализация Telegram-бота.
Единая точка создания объекта bot.

Создано: 2026-07-07
Папка: INSTALL_DIR/core/
"""

import telebot

# Добавляем путь к config.py
from config.secrets import BOT_TOKEN
from core.stats_middleware import StatsMiddleware

# Создаём единый объект бота
bot = telebot.TeleBot(
    BOT_TOKEN,
    num_threads=5,
    use_class_middlewares=True,
)
bot.setup_middleware(StatsMiddleware())
