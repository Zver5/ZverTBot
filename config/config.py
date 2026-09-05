"""
Центральный модуль настроек ZverTBot.

Назначение:
- собирает общие настройки приложения;
- экспортирует пути из config.paths;
- экспортирует серверные параметры из config.secrets (.env).

Структура:
- config.paths  → пути к файлам и каталогам;
- config.secrets → секреты и индивидуальные параметры сервера (.env);
- config.config → единая точка импорта для приложения.

Создано: 2026-06-30
Проект: ZverTBot
"""

from datetime import timedelta, timezone

BOT_TZ = timezone(timedelta(hours=3))

# ruff: noqa: F401

from config.paths import (
    ARCHIVE_JSON,
    ASN_DB_PATH,
    AUTH_LOG,
    AWG_CONF,
    AWG_USERS_JSON,
    BACKUP_DIR,
    BACKUP_SCRIPT,
    BOT_HISTORY,
    BOT_STATS_FILE,
    CLIENT_BINDINGS,
    CONFIG_BACKUPS_DIR,
    DATA_DIR,
    FAIL2BAN_LOG,
    GEO_DIR,
    GEOIP_COLLECT_SCRIPT,
    GEOIP_JSON,
    HASS_DIR,
    IP_TOKENS_FILE,
    KUMA_STATE_FILE,
    LOG_DIR,
    LOG_FILE,
    PENDING_BINDINGS,
    PROJECT_ROOT,
    RCLONE_STATUS_JSON,
    RU_GEO_CONF,
    SSH_AUTHORIZED_KEYS,
    STATS_DIR,
    STATS_HTTP_SCRIPT,
    STATS_JSON,
    TMP_DIR,
    TRAFFIC_DIR,
    USAGE_JSON,
    VPS_STATS_SCRIPT,
    XRAY_ACCESS_LOG,
    XRAY_CONF,
    XRAY_TRAFFIC_SCRIPT,
)
from config.secrets import (
    ADMIN_CHAT,
    ADMIN_CHATS,
    BOT_TOKEN,
    HA_TUNNEL_IP,
    HASS_FLAG,
    KUMA_HEALTHCHECK_URL,
    LLM_API_KEY,
    LLM_API_URL,
    LLM_MODEL,
    LLM_MODELS,
    LLM_PROVIDER,
    SERVER_FLAG,
    SERVER_IP,
)

# ═══════════════════════════════════════════════════════
#  ИНФОРМАЦИЯ О ВЕРСИИ ZverTBot
# ═══════════════════════════════════════════════════════

BOT_NAME = "ZverTBot"
BOT_VERSION = "1.0.0"


# ═══════════════════════════════════════════════════════
#  СЕРВЕРНЫЕ ПАРАМЕТРЫ
# ═══════════════════════════════════════════════════════
#
# Индивидуальные параметры текущего сервера.
# Хранятся только в .env.
# Получаются через config.secrets.
#
# При переносе ZverTBot на новый VPS
# меняется только .env.
#
