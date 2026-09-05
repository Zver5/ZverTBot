#!/usr/bin/env python3

from core.bot import bot
from core.callback_checker import check_callbacks
from core.callback_router import register_callback_router
from core.handler_loader import load_handler_modules
from handlers.navigation_registry import register_navigation_screens
from utils.logger import logger

# ==========================================================
# HANDLER MODULES
# ==========================================================

load_handler_modules()

# ==========================================================
# NAVIGATION SCREENS
# ==========================================================

register_navigation_screens()


# ==========================================================
# CALLBACK ROUTER
# ==========================================================

register_callback_router(bot)

# ==========================================================
# ЗАПУСК
# ==========================================================

logger.info("bot.started | mode=SAFE_STRICT")


# ==========================================================
# ПРОВЕРКА CALLBACK КНОПОК
# ==========================================================

check_callbacks()

bot.infinity_polling()
