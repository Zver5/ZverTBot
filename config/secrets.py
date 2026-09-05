"""
Секретные и серверные настройки.

Берутся из .env.

В Git хранится только этот модуль.
Все индивидуальные параметры сервера находятся в .env.
"""

import os

from dotenv import load_dotenv

load_dotenv()


# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT = os.getenv("ADMIN_CHAT")

# Поддержка нескольких админских чатов
# Формат в .env:
# ADMIN_CHAT=123456789,987654321


# Сервер
SERVER_IP = os.getenv("SERVER_IP")
SERVER_FLAG = os.getenv("SERVER_FLAG", "🌐")

# Home Assistant SSH tunnel IP
# Optional: empty if tunnel is not used
HA_TUNNEL_IP = os.getenv("HA_TUNNEL_IP", "")
HASS_FLAG = os.getenv("HASS_FLAG", "🌍")

# Xray Reality


# AmneziaWG


# Kuma webhook / healthcheck
KUMA_HEALTHCHECK_URL = os.getenv("KUMA_HEALTHCHECK_URL", "http://127.0.0.1:8081/status")


# LLM API for log diagnostics
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()

LLM_PROVIDER_DEFAULTS = {
    "groq": {
        "api_url": "https://api.groq.com/openai/v1/chat/completions",
        "models": (
            "openai/gpt-oss-120b",
            "qwen/qwen3.6-27b",
            "openai/gpt-oss-20b",
        ),
    },
    "openrouter": {
        "api_url": "https://openrouter.ai/api/v1/chat/completions",
        "models": (
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.6-27b",
        ),
    },
    "openai": {
        "api_url": "https://api.openai.com/v1/chat/completions",
        "models": (
            "gpt-5",
            "gpt-4.1",
        ),
    },
}

_provider_defaults = LLM_PROVIDER_DEFAULTS.get(LLM_PROVIDER, {})

LLM_API_URL = os.getenv("LLM_API_URL", "").strip() or _provider_defaults.get(
    "api_url", ""
)

LLM_MODEL = (
    os.getenv("LLM_MODEL", "").strip() or _provider_defaults.get("models", ("",))[0]
)

LLM_MODELS = tuple(
    model.strip()
    for model in (
        os.getenv("LLM_MODELS", "").strip()
        or ",".join(_provider_defaults.get("models", ()))
    ).split(",")
    if model.strip()
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN отсутствует в .env")

if not ADMIN_CHAT:
    raise RuntimeError("ADMIN_CHAT отсутствует в .env")

ADMIN_CHATS = [x.strip() for x in ADMIN_CHAT.split(",") if x.strip()]

# AbuseIPDB для проверки репутации IP
ABUSEIPDB_API_KEY = os.getenv("ABUSEIPDB_API_KEY", "")
