import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Корень проекта
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# -----------------------
# HASS
# -----------------------

HASS_DIR = PROJECT_ROOT / "hass"

STATS_DIR = HASS_DIR / "stats"
TRAFFIC_DIR = HASS_DIR / "traffic"
GEO_DIR = HASS_DIR / "geo"
BACKUP_DIR = HASS_DIR / "backup"

# -----------------------
# JSON
# -----------------------

STATS_JSON = STATS_DIR / "stats.json"

USAGE_JSON = TRAFFIC_DIR / "usage.json"
ARCHIVE_JSON = TRAFFIC_DIR / "archive.json"

GEOIP_JSON = GEO_DIR / "geoip.json"

RCLONE_STATUS_JSON = BACKUP_DIR / "rclone_backup_status.json"

# -----------------------
# Scripts
# -----------------------

VPS_STATS_SCRIPT = STATS_DIR / "vps_stats.py"
STATS_HTTP_SCRIPT = STATS_DIR / "stats-http.py"

XRAY_TRAFFIC_SCRIPT = TRAFFIC_DIR / "xray-traffic-collect.py"

GEOIP_COLLECT_SCRIPT = GEO_DIR / "geoip-collect.py"

# -----------------------
# BOT DATA
# -----------------------

DATA_DIR = PROJECT_ROOT / "data"


AWG_USERS_JSON = DATA_DIR / "awg_users.json"
CLIENT_BINDINGS = DATA_DIR / "client_bindings.json"
TICKETS_JSON = DATA_DIR / "tickets.json"
PENDING_BINDINGS = DATA_DIR / "pending_bindings.json"
BOT_HISTORY = DATA_DIR / "bot_history.json"

RU_GEO_CONF = DATA_DIR / "ru_geo.conf"

BOT_STATS_FILE = DATA_DIR / "bot_stats.json"
IP_TOKENS_FILE = DATA_DIR / "ip_tokens.json"
ASN_DB_PATH = DATA_DIR / "asn_types.json"

# Local GeoIP MMDB databases
GEOIP_CITY_DB = Path(
    os.getenv("GEOIP_CITY_DB", str(DATA_DIR / "geoip/dbip-city-lite.mmdb"))
)
GEOIP_ASN_DB = Path(
    os.getenv("GEOIP_ASN_DB", str(DATA_DIR / "geoip/dbip-asn-lite.mmdb"))
)

# -----------------------
# SYSTEM CONFIG PATHS
# -----------------------

# Xray
XRAY_CONF = Path(os.getenv("XRAY_CONF", "/usr/local/etc/xray/config.json"))
XRAY_ACCESS_LOG = Path(os.getenv("XRAY_ACCESS_LOG", "/var/log/xray/access.log"))

XRAY_TRAFFIC_LOG = Path(os.getenv("XRAY_TRAFFIC_LOG", "/var/log/xray-traffic.log"))

# AmneziaWG
AWG_DEFAULT_CONF = Path("/etc/amnezia/amneziawg/awg0.conf")


def resolve_awg_conf():
    """Resolve the AWG server config path.

    An explicit AWG_CONF environment value always has priority.
    Otherwise, use the native AmneziaWG config path.
    """
    env_value = os.getenv("AWG_CONF", "").strip()
    if env_value:
        return Path(env_value)

    return AWG_DEFAULT_CONF


AWG_CONF = resolve_awg_conf()


# -----------------------
# BACKUP
# -----------------------

BACKUP_SCRIPT = PROJECT_ROOT / "scripts" / "backup-to-yandex.sh"

BACKUP_REMOTE = os.getenv("BACKUP_REMOTE", "").strip()
BACKUP_ROOT_DIR = os.getenv("BACKUP_ROOT_DIR", "").strip()

CONFIG_BACKUPS_DIR = Path(
    os.getenv("CONFIG_BACKUPS_DIR", str(Path.home() / "config-backups"))
)


# -----------------------
# SSH / SECURITY
# -----------------------

SSH_HOME = Path(os.getenv("SSH_HOME", str(Path.home())))

SSH_AUTHORIZED_KEYS = SSH_HOME / ".ssh" / "authorized_keys"


# -----------------------
# TEMP FILES
# -----------------------

TMP_DIR = Path("/tmp")

KUMA_STATE_FILE = TMP_DIR / "zvert_health_state.json"

# -----------------------
# LOGS
# -----------------------

LOG_DIR = Path("/var/log")

LOG_FILE = LOG_DIR / "zvertbot.log"
AUTH_LOG = LOG_DIR / "auth.log"
FAIL2BAN_LOG = LOG_DIR / "fail2ban.log"
