#!/bin/bash

set -e

# ==========================================================
# ZverTBot Universal Installer
# Stage 1: Fresh server installation
# ==========================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

INSTALL_DIR="/opt/ZverTBot"

ENV_FILE="${INSTALL_DIR}/.env"
SYSTEMD_DIR="/etc/systemd/system"

# ---------- Colors ----------
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
CYAN="\033[0;36m"
NC="\033[0m"


info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

ok() {
    echo -e "${GREEN}[ OK ]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    exit 1
}


INSTALL_XRAY=false
INSTALL_AWG=false

for arg in "$@"; do
    case "$arg" in
        -xray)
            INSTALL_XRAY=true
            ;;
        -awg)
            INSTALL_AWG=true
            ;;
        *)
            fail "Unknown option: $arg"
            ;;
    esac
done


banner() {
clear
echo -e "${CYAN}"
echo "╔══════════════════════════════════════╗"
echo "║                                      ║"
echo "║        🐺 ZverTBot Installer         ║"
echo "║             Version ${VERSION}            ║"
echo "║                                      ║"
echo "╚══════════════════════════════════════╝"
echo -e "${NC}"
}


check_root() {
    if [ "$EUID" -ne 0 ]; then
        fail "Installer must run as root"
    fi
    ok "Root access"
}


check_os() {

    if [ ! -f /etc/os-release ]; then
        fail "Unknown Linux distribution"
    fi

    . /etc/os-release

    case "$ID" in
        ubuntu|debian)
            ok "$PRETTY_NAME detected"
            ;;
        *)
            fail "Supported only Debian/Ubuntu"
            ;;
    esac
}


check_network() {

    info "Checking internet..."

    if curl -s --max-time 5 https://api.telegram.org >/dev/null; then
        ok "Internet connection"
    else
        warn "Telegram API unavailable"
    fi

    if getent hosts google.com >/dev/null; then
        ok "DNS resolution"
    else
        fail "DNS problem"
    fi
}


install_packages() {

    info "Checking package manager lock"

    LOCK_TIMEOUT=180
    LOCK_STARTED=$(date +%s)
    LOCK_LAST_REPORT=-30

    while true; do
        LOCK_PIDS=""

        for lock_file in /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock; do
            if [ -e "$lock_file" ]; then
                PIDS=$(fuser "$lock_file" 2>/dev/null || true)
                if [ -n "$PIDS" ]; then
                    LOCK_PIDS="$LOCK_PIDS $PIDS"
                fi
            fi
        done

        LOCK_PIDS=$(printf '%s\n' "$LOCK_PIDS" | xargs -r -n1 | sort -nu | xargs || true)

        if [ -z "$LOCK_PIDS" ]; then
            break
        fi

        NOW=$(date +%s)
        ELAPSED=$((NOW - LOCK_STARTED))

        if [ "$((ELAPSED - LOCK_LAST_REPORT))" -ge 30 ]; then
            LOCK_LAST_REPORT=$ELAPSED

            LOCK_DETAILS=""
            for pid in $LOCK_PIDS; do
                if [ -r "/proc/$pid/comm" ]; then
                    NAME=$(cat "/proc/$pid/comm")
                    LOCK_DETAILS="${LOCK_DETAILS} ${NAME} (PID ${pid});"
                fi
            done

            info "Package manager is busy:${LOCK_DETAILS}"
            info "Waiting for package manager... elapsed: ${ELAPSED}s"
        fi

        if [ "$ELAPSED" -ge "$LOCK_TIMEOUT" ]; then
            echo
            fail "Package manager lock is still held after ${LOCK_TIMEOUT}s"

            echo
            echo "Processes holding the package manager lock:"
            for pid in $LOCK_PIDS; do
                ps -p "$pid" -o pid,ppid,etime,%cpu,%mem,stat,cmd --no-headers 2>/dev/null || true
            done

            echo
            echo "Check package manager state with:"
            echo "  ps aux | grep -E 'apt|dpkg|unattended' | grep -v grep"
            echo "  sudo fuser -v /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock"
            echo
            echo "Wait for automatic updates to finish, then run the installer again."
            return 1
        fi

        sleep 5
    done

    info "Package manager lock released"

    info "Checking package manager state"

    DPKG_AUDIT=$(dpkg --audit 2>&1 || true)
    if [ -n "$DPKG_AUDIT" ]; then
        echo "$DPKG_AUDIT"
        fail "dpkg has unfinished package operations"
    fi

    APT_CHECK_LOG=$(mktemp)
    if ! apt-get check >"$APT_CHECK_LOG" 2>&1; then
        cat "$APT_CHECK_LOG"
        rm -f "$APT_CHECK_LOG"
        fail "Package manager has broken dependencies"
    fi
    rm -f "$APT_CHECK_LOG"

    info "Updating package list"

    APT_UPDATE_LOG=$(mktemp)
    if ! apt-get update -y >"$APT_UPDATE_LOG" 2>&1; then
        cat "$APT_UPDATE_LOG"
        rm -f "$APT_UPDATE_LOG"
        fail "Failed to update package list"
    fi

    if grep -qE '(^|[[:space:]])(Err:|Failed to fetch)' "$APT_UPDATE_LOG"; then
        cat "$APT_UPDATE_LOG"
        rm -f "$APT_UPDATE_LOG"
        fail "Failed to update package list"
    fi

    rm -f "$APT_UPDATE_LOG"

    PACKAGE_FILE="${INSTALL_DIR}/deploy/botinstaller/packages.txt"


    if [ ! -f "$PACKAGE_FILE" ]; then
        fail "packages.txt not found"
    fi


    PACKAGES=$(grep -vE '^\s*#|^\s*$' "$PACKAGE_FILE")


    info "Installing system packages"

    APT_INSTALL_LOG=$(mktemp)

    if ! DEBIAN_FRONTEND=noninteractive apt-get install -y $PACKAGES >"$APT_INSTALL_LOG" 2>&1; then
        cat "$APT_INSTALL_LOG"
        rm -f "$APT_INSTALL_LOG"
        fail "Failed to install system packages"
    fi

    cat "$APT_INSTALL_LOG"
    rm -f "$APT_INSTALL_LOG"

    info "Validating package manager state"

    DPKG_AUDIT=$(dpkg --audit 2>&1 || true)
    if [ -n "$DPKG_AUDIT" ]; then
        echo "$DPKG_AUDIT"
        fail "dpkg has unfinished package operations after package installation"
    fi

    APT_CHECK_LOG=$(mktemp)
    if ! apt-get check >"$APT_CHECK_LOG" 2>&1; then
        cat "$APT_CHECK_LOG"
        rm -f "$APT_CHECK_LOG"
        fail "Package manager has broken dependencies after package installation"
    fi
    rm -f "$APT_CHECK_LOG"

    ok "System packages installed"

}






prepare_install_dir() {

    mkdir -p "$INSTALL_DIR"

    cd "$INSTALL_DIR"

}


extract_archive() {

    ARCHIVE=$(find "$SCRIPT_DIR" -maxdepth 1 -type f -name "ZverTBot-deploy-*.tar.gz" | head -1)

    if [ -z "$ARCHIVE" ] || [ ! -f "$ARCHIVE" ]; then
        fail "Deploy archive not found рядом с install.sh"
    fi

    info "Extracting ZverTBot archive"

    TMP_DIR="$(mktemp -d /tmp/zvertbot-install.XXXXXX)"
    trap 'rm -rf "$TMP_DIR"' EXIT

    tar -xzf "$ARCHIVE" \
        -C "$TMP_DIR"

    EXTRACTED_DIR="$TMP_DIR/ZverTBot"

    if [ ! -d "$EXTRACTED_DIR" ]; then
        fail "Extracted archive directory not found"
    fi

    rsync -a \
        "$EXTRACTED_DIR/" \
        "$INSTALL_DIR/"

    rm -rf "$TMP_DIR"
    trap - EXIT

    cd "$INSTALL_DIR"

    VERSION="$(
        sed -n 's/^\s*BOT_VERSION\s*=\s*"\([^"]*\)"\s*$/\1/p' \
            "$INSTALL_DIR/config/config.py" | head -1
    )"

    if ! printf '%s' "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
        fail "Invalid or missing BOT_VERSION in config/config.py"
    fi

    ok "Project version: $VERSION"
    ok "Archive installed"

}


install_xray() {

    if command -v xray >/dev/null 2>&1; then
        ok "Xray already installed"
    else
        info "Installing Xray"

        bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install

        if ! command -v xray >/dev/null 2>&1; then
            fail "Xray installation failed"
        fi

        ok "Xray installed"
    fi

    XRAY_DEFAULT_CONF="/usr/local/etc/xray/config.json"
    XRAY_EXAMPLE="${INSTALL_DIR}/deploy/botinstaller/examples/xray.config.example.json"

    if [ ! -f "$XRAY_DEFAULT_CONF" ] && [ -f "$XRAY_EXAMPLE" ]; then
        mkdir -p "$(dirname "$XRAY_DEFAULT_CONF")"
        install -m 644 "$XRAY_EXAMPLE" "$XRAY_DEFAULT_CONF"
        ok "Xray example config installed: $XRAY_DEFAULT_CONF"
    elif [ "$(tr -d '[:space:]' < "$XRAY_DEFAULT_CONF")" = "{}" ] && [ -f "$XRAY_EXAMPLE" ]; then
        install -m 644 "$XRAY_EXAMPLE" "$XRAY_DEFAULT_CONF"
        ok "Empty Xray config replaced with example: $XRAY_DEFAULT_CONF"
    fi
}


install_rclone() {

    if command -v rclone >/dev/null 2>&1; then
        if rclone version >/dev/null 2>&1; then
            RCLONE_VERSION=$(rclone version 2>/dev/null | awk 'NR==1 {print $2}')

            if [ -n "$RCLONE_VERSION" ]; then
                ok "rclone already installed: $RCLONE_VERSION"
            else
                ok "rclone already installed"
            fi
            return
        fi

        warn "rclone binary exists but is not working; reinstalling"
    else
        info "Installing rclone"
    fi

    if ! curl -fsSL https://rclone.org/install.sh | bash >/dev/null; then
        fail "rclone installation failed"
    fi

    if ! command -v rclone >/dev/null 2>&1 || ! rclone version >/dev/null 2>&1; then
        fail "rclone installation failed: binary is unavailable"
    fi

    RCLONE_VERSION=$(rclone version 2>/dev/null | awk 'NR==1 {print $2}')

    if [ -n "$RCLONE_VERSION" ]; then
        ok "rclone installed: $RCLONE_VERSION"
    else
        ok "rclone installed"
    fi
}


install_awg() {

    if command -v awg >/dev/null 2>&1; then
        ok "AmneziaWG already installed"
    else
        info "Installing AmneziaWG from PPA"

        DEBIAN_FRONTEND=noninteractive apt-get install -y software-properties-common >/dev/null

        add-apt-repository ppa:amnezia/ppa -y
        apt-get update -y >/dev/null
        DEBIAN_FRONTEND=noninteractive apt-get install -y amneziawg-dkms amneziawg-tools >/dev/null

        if ! command -v awg >/dev/null 2>&1; then
            fail "AmneziaWG installation failed"
        fi

        ok "AmneziaWG installed"
    fi

    AWG_DEFAULT_CONF="/etc/amnezia/amneziawg/awg0.conf"
    AWG_EXAMPLE="${INSTALL_DIR}/deploy/botinstaller/examples/awg0.conf.example"

    if [ ! -f "$AWG_DEFAULT_CONF" ] && [ -f "$AWG_EXAMPLE" ]; then
        mkdir -p "$(dirname "$AWG_DEFAULT_CONF")"
        install -m 600 "$AWG_EXAMPLE" "$AWG_DEFAULT_CONF"
        ok "AWG example config installed: $AWG_DEFAULT_CONF"
    fi
}


detect_service_config_paths() {

    # --------------------------------------------------------
    # Xray:
    # путь берём непосредственно из systemd ExecStart.
    # --------------------------------------------------------

    XRAY_CONF=""

    if command -v systemctl >/dev/null 2>&1; then
        XRAY_EXECSTART=$(systemctl cat xray.service 2>/dev/null \
            | grep -E '^[[:space:]]*ExecStart=.*xray.*run.*-config[[:space:]]+' \
            | tail -1 || true)

        if [[ "$XRAY_EXECSTART" =~ -config[[:space:]]+([^[:space:]]+) ]]; then
            XRAY_CANDIDATE="${BASH_REMATCH[1]}"

            if [ -f "$XRAY_CANDIDATE" ]; then
                XRAY_CONF="$XRAY_CANDIDATE"
                ok "Xray config detected: $XRAY_CONF"
            else
                warn "Xray config path detected but file not found: $XRAY_CANDIDATE"
            fi
        fi
    fi

    if [ -z "$XRAY_CONF" ]; then
        warn "Xray config path not detected."
        warn "Please set XRAY_CONF manually in .env"
    fi


    # --------------------------------------------------------
    # AWG:
    # ищем экземпляр awg-quick@<interface>.service.
    # Для найденного интерфейса используем только native
    # /etc/amnezia/amneziawg/<interface>.conf.
    # --------------------------------------------------------

    AWG_CONF=""

    if command -v systemctl >/dev/null 2>&1; then
        AWG_UNITS=$(systemctl list-units --all --no-legend \
            'awg-quick@*.service' 2>/dev/null \
            | awk '{print $1}' || true)

        for AWG_UNIT in $AWG_UNITS; do
            if [[ "$AWG_UNIT" =~ ^awg-quick@(.+)\.service$ ]]; then
                AWG_INTERFACE="${BASH_REMATCH[1]}"

                AWG_CANDIDATE="/etc/amnezia/amneziawg/${AWG_INTERFACE}.conf"

                if [ -f "$AWG_CANDIDATE" ]; then
                    AWG_CONF="$AWG_CANDIDATE"
                    ok "AWG config detected for ${AWG_UNIT}: $AWG_CONF"
                    break
                fi
            fi
        done
    fi

    if [ -z "$AWG_CONF" ]; then
        warn "AWG config path not detected."
        warn "Please set AWG_CONF manually in .env"
    fi

}

create_env() {

    ENV_FILE="${INSTALL_DIR}/.env"


    if [ -f "$ENV_FILE" ]; then
        warn ".env already exists"

        if [ ! -s "$ENV_FILE" ]; then
            fail ".env exists but is empty"
        fi

        chmod 600 "$ENV_FILE"
        return
    fi


    info "Detecting server IP"

    SERVER_IP=$(curl -4 -s ifconfig.me || echo "")

    if [ -z "$SERVER_IP" ]; then
        warn "Cannot detect public IP"
    else
        ok "Server IP: $SERVER_IP"
    fi


    echo
    echo -e "${CYAN}Telegram configuration${NC}"
    echo

    read -p "BOT_TOKEN: " BOT_TOKEN

    read -p "ADMIN_CHAT: " ADMIN_CHAT



    echo
    echo -e "${CYAN}VPN configuration${NC}"
    echo

    info "Xray Reality parameters are read from the Xray config"
    info "They are NOT stored in .env"

    detect_service_config_paths


    echo

    read -p "HA_TUNNEL_IP (optional, Enter to skip): " HA_TUNNEL_IP
    HA_TUNNEL_IP=${HA_TUNNEL_IP:-}


    HASS_FLAG="🌍"





    SERVER_FLAG="🌍"

    declare -A COUNTRY_FLAGS=(
        [RU]="🇷🇺"
        [NL]="🇳🇱"
        [DE]="🇩🇪"
        [TR]="🇹🇷"
        [FI]="🇫🇮"
        [SE]="🇸🇪"
        [US]="🇺🇸"
        [CH]="🇨🇭"
        [FR]="🇫🇷"
        [GB]="🇬🇧"
        [PL]="🇵🇱"
        [CZ]="🇨🇿"
        [AT]="🇦🇹"
        [NO]="🇳🇴"
        [DK]="🇩🇰"
        [EE]="🇪🇪"
        [LV]="🇱🇻"
        [LT]="🇱🇹"
        [IT]="🇮🇹"
        [ES]="🇪🇸"
    )

    if command -v curl >/dev/null; then

        COUNTRY=""

        # 1. ipapi.co
        COUNTRY=$(curl -4 -s --max-time 5 https://ipapi.co/country/ 2>/dev/null || true)

        # 2. ipinfo.io fallback
        if [[ ! "$COUNTRY" =~ ^[A-Z]{2}$ ]]; then
            COUNTRY=$(curl -4 -s --max-time 5 https://ipinfo.io/country 2>/dev/null || true)
        fi

        # 3. ip-api fallback
        if [[ ! "$COUNTRY" =~ ^[A-Z]{2}$ ]]; then
            COUNTRY=$(curl -4 -s --max-time 5 http://ip-api.com/line?fields=countryCode 2>/dev/null || true)
        fi

        COUNTRY=$(echo "$COUNTRY" | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')

        if [[ -n "${COUNTRY_FLAGS[$COUNTRY]}" ]]; then
            SERVER_FLAG="${COUNTRY_FLAGS[$COUNTRY]}"
        fi

    fi


    # Определяем страну HASS по HA_TUNNEL_IP
    if [[ -n "$HA_TUNNEL_IP" ]] && command -v curl >/dev/null; then

        HASS_COUNTRY=""

        HASS_COUNTRY=$(curl -s --max-time 5 "https://ipapi.co/${HA_TUNNEL_IP}/country/" 2>/dev/null || true)

        if [[ ! "$HASS_COUNTRY" =~ ^[A-Z]{2}$ ]]; then
            HASS_COUNTRY=$(curl -s --max-time 5 "https://ipinfo.io/${HA_TUNNEL_IP}/country" 2>/dev/null || true)
        fi

        if [[ ! "$HASS_COUNTRY" =~ ^[A-Z]{2}$ ]]; then
            HASS_COUNTRY=$(curl -s --max-time 5 "http://ip-api.com/line?query=${HA_TUNNEL_IP}&fields=countryCode" 2>/dev/null || true)
        fi

        HASS_COUNTRY=$(echo "$HASS_COUNTRY" | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')

        if [[ -n "${COUNTRY_FLAGS[$HASS_COUNTRY]}" ]]; then
            HASS_FLAG="${COUNTRY_FLAGS[$HASS_COUNTRY]}"
        fi

    fi



    mkdir -p "$INSTALL_DIR"

    ENV_TEMPLATE="${INSTALL_DIR}/deploy/botinstaller/.env.example"

    if [ ! -f "$ENV_TEMPLATE" ]; then
        warn ".env.example not found in deploy archive: $ENV_TEMPLATE"
        exit 1
    fi

    cp "$ENV_TEMPLATE" "$ENV_FILE"

    python3 - "$ENV_FILE" \
        "$BOT_TOKEN" \
        "$ADMIN_CHAT" \
        "$SERVER_IP" \
        "$SERVER_FLAG" \
        "$HA_TUNNEL_IP" \
        "$HASS_FLAG" \
        "$XRAY_CONF" \
        "$AWG_CONF" <<'PYENV'
import sys
from pathlib import Path

(
    env_file,
    bot_token,
    admin_chat,
    server_ip,
    server_flag,
    ha_tunnel_ip,
    hass_flag,
    xray_conf,
    awg_conf,
) = sys.argv[1:]

path = Path(env_file)
text = path.read_text()

values = {
    "BOT_TOKEN": bot_token,
    "ADMIN_CHAT": admin_chat,
    "SERVER_IP": server_ip,
    "SERVER_FLAG": server_flag,
    "HA_TUNNEL_IP": ha_tunnel_ip,
    "HASS_FLAG": hass_flag,
    "XRAY_CONF": xray_conf,
    "AWG_CONF": awg_conf,
}

lines = text.splitlines()
result = []

for line in lines:
    replaced = False

    for key, value in values.items():
        if line.startswith(key + "="):
            result.append(f"{key}={value}")
            replaced = True
            break

    if not replaced:
        result.append(line)

path.write_text("\n".join(result) + "\n")
PYENV


    chmod 600 "$ENV_FILE"


    ok ".env created"

}



enable_ip_forwarding() {

    info "Enabling IPv4 forwarding"

    if grep -q "^net.ipv4.ip_forward" /etc/sysctl.conf; then
        sed -i 's/^net\.ipv4\.ip_forward.*/net.ipv4.ip_forward=1/' /etc/sysctl.conf
    else
        echo "" >> /etc/sysctl.conf
        echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
    fi

    if ! sysctl -p >/dev/null 2>&1; then
        warn "Failed to apply sysctl configuration"
    fi

    if [ "$(cat /proc/sys/net/ipv4/ip_forward)" = "1" ]; then
        ok "IPv4 forwarding enabled"
    else
        warn "IPv4 forwarding could not be enabled"
    fi

}

create_runtime_files() {

    info "Creating runtime directories"

    mkdir -p "${INSTALL_DIR}/data"
    mkdir -p "${INSTALL_DIR}/hass/stats"
    mkdir -p "${INSTALL_DIR}/hass/traffic"
    mkdir -p "${INSTALL_DIR}/hass/geo"
    mkdir -p "${INSTALL_DIR}/hass/backup"
    mkdir -p "${INSTALL_DIR}/logs"

    # -------------------------------------------------------------------------
    # Clean installation state
    #
    # These files contain server-specific/user data. They are intentionally
    # NOT restored from the project package on a new server.
    #
    # If old data is required, it must be restored separately from backup.
    # Keeping these files empty prevents accidental dependency on the old
    # server state.
    # -------------------------------------------------------------------------

    # Persistent user data — empty on a new server.
    # If not restored from backup, the corresponding old data is lost:
    #   awg_users       -> AWG client registry
    #   client_bindings -> Telegram user/client bindings
    #   tickets         -> ticket history/state
    #   ip_tokens       -> generated IP access tokens
    [ -f "${INSTALL_DIR}/data/awg_users.json" ] || echo "{}" > "${INSTALL_DIR}/data/awg_users.json"
    [ -f "${INSTALL_DIR}/data/client_bindings.json" ] || echo "{}" > "${INSTALL_DIR}/data/client_bindings.json"
    [ -f "${INSTALL_DIR}/data/tickets.json" ] || echo "{}" > "${INSTALL_DIR}/data/tickets.json"
    [ -f "${INSTALL_DIR}/data/ip_tokens.json" ] || echo "{}" > "${INSTALL_DIR}/data/ip_tokens.json"

    # Runtime/application state — starts empty and is rebuilt automatically.
    [ -f "${INSTALL_DIR}/data/pending_bindings.json" ] || echo "{}" > "${INSTALL_DIR}/data/pending_bindings.json"
    [ -f "${INSTALL_DIR}/data/bot_history.json" ] || echo "[]" > "${INSTALL_DIR}/data/bot_history.json"
    [ -f "${INSTALL_DIR}/data/bot_stats.json" ] || echo "{}" > "${INSTALL_DIR}/data/bot_stats.json"

    # Runtime snapshots/state — generated or updated automatically.
    [ -f "${INSTALL_DIR}/hass/stats/stats.json" ] || echo "{}" > "${INSTALL_DIR}/hass/stats/stats.json"
    [ -f "${INSTALL_DIR}/hass/traffic/usage.json" ] || echo "{}" > "${INSTALL_DIR}/hass/traffic/usage.json"
    [ -f "${INSTALL_DIR}/hass/traffic/archive.json" ] || echo "{}" > "${INSTALL_DIR}/hass/traffic/archive.json"
    [ -f "${INSTALL_DIR}/hass/geo/geoip.json" ] || echo "{}" > "${INSTALL_DIR}/hass/geo/geoip.json"
    [ -f "${INSTALL_DIR}/hass/backup/rclone_backup_status.json" ] || echo "{}" > "${INSTALL_DIR}/hass/backup/rclone_backup_status.json"

    # data/asn_types.json and data/ru_geo.conf are NOT generated here.
    # They are static project files and must be supplied by the package.

    ok "Runtime files created"

}


create_venv() {

    cd "${INSTALL_DIR}"

    if [ ! -d ".venv" ]; then

        info "Creating Python virtual environment"

        python3 -m venv .venv

    fi


    .venv/bin/pip install --upgrade pip >/dev/null

    .venv/bin/pip install -r requirements.txt >/dev/null

    ok "Python dependencies installed"

    download_geoip_databases
}


download_geoip_databases() {

    info "Installing DB-IP Lite GeoIP databases"

    GEOIP_DIR="${INSTALL_DIR}/data/geoip"
    mkdir -p "$GEOIP_DIR"

    CITY_DB="${GEOIP_DIR}/dbip-city-lite.mmdb"
    ASN_DB="${GEOIP_DIR}/dbip-asn-lite.mmdb"

    # DB-IP Lite выпускается ежемесячно.
    # Пробуем текущий месяц, затем предыдущий.
    CURRENT_MONTH="$(date +%Y-%m)"
    PREVIOUS_MONTH="$(date -d '1 month ago' +%Y-%m)"

    download_and_extract_geoip() {

        local url="$1"
        local target="$2"
        local label="$3"

        local tmp_gz="${target}.download.gz"
        local tmp_mmdb="${target}.download"

        rm -f "$tmp_gz" "$tmp_mmdb"

        info "Downloading ${label}: ${url}"

        if ! curl -fL \
            --retry 3 \
            --retry-delay 2 \
            --connect-timeout 15 \
            --max-time 900 \
            "$url" \
            -o "$tmp_gz"
        then
            rm -f "$tmp_gz" "$tmp_mmdb"
            return 1
        fi

        if ! gzip -t "$tmp_gz" >/dev/null 2>&1; then
            rm -f "$tmp_gz" "$tmp_mmdb"
            warn "${label}: downloaded archive is invalid"
            return 1
        fi

        if ! gzip -dc "$tmp_gz" > "$tmp_mmdb"; then
            rm -f "$tmp_gz" "$tmp_mmdb"
            warn "${label}: failed to extract archive"
            return 1
        fi

        if [ ! -s "$tmp_mmdb" ]; then
            rm -f "$tmp_gz" "$tmp_mmdb"
            warn "${label}: MMDB is empty"
            return 1
        fi

        # City Lite ~125 MB, ASN Lite ~9 MB.
        # Anything below 1 MB is definitely not a valid database.
        if [ "$(stat -c%s "$tmp_mmdb")" -lt 1048576 ]; then
            rm -f "$tmp_gz" "$tmp_mmdb"
            warn "${label}: MMDB is suspiciously small"
            return 1
        fi

        # Проверяем MMDB до замены существующей базы.
    if ! "${INSTALL_DIR}/.venv/bin/python" \
        - "$tmp_mmdb" <<'PYCHECK'
import sys
import maxminddb

path = sys.argv[1]

with maxminddb.open_database(path) as db:
    db.get("1.1.1.1")

print("MMDB validation: OK")
PYCHECK
    then
            rm -f "$tmp_gz" "$tmp_mmdb"
            warn "${label}: MMDB validation failed"
            return 1
        fi

        mv -f "$tmp_mmdb" "$target"
        rm -f "$tmp_gz"

        ok "${label} installed: $(du -h "$target" | awk '{print $1}')"

        return 0
    }

    install_geoip_database() {

        local database="$1"
        local target="$2"
        local label="$3"

        # Если база уже есть — не скачиваем её заново.
        if [ -s "$target" ]; then
            ok "${label} already exists"
            return 0
        fi

        local url

        for month in "$CURRENT_MONTH" "$PREVIOUS_MONTH"
        do
            DBIP_SCHEME="https"
            DBIP_HOST="download.db-ip.com"
            DBIP_PATH="/free"
            url="${DBIP_SCHEME}://${DBIP_HOST}${DBIP_PATH}/${database}-${month}.mmdb.gz"
            info "Trying ${label} release ${month}"

            if download_and_extract_geoip "$url" "$target" "$label"; then
                return 0
            fi

            warn "${label} release ${month} is unavailable or invalid"
        done

        fail "Unable to install ${label}: no usable monthly release found"
    }

    install_geoip_database \
        "dbip-city-lite" \
        "$CITY_DB" \
        "DB-IP City Lite"

    install_geoip_database \
        "dbip-asn-lite" \
        "$ASN_DB" \
        "DB-IP ASN Lite"

    # Финальная проверка обеих баз.
    if ! "${INSTALL_DIR}/.venv/bin/python" \
        - "$CITY_DB" "$ASN_DB" <<'PYCHECK'
import sys
import maxminddb

for path in sys.argv[1:]:
    with maxminddb.open_database(path) as db:
        db.get("1.1.1.1")

print("GeoIP MMDB validation: OK")
PYCHECK
    then
        fail "GeoIP MMDB final validation failed"
    fi

    ok "DB-IP GeoIP databases ready"
}

create_service() {

    info "Installing systemd services"

    SYSTEMD_TEMPLATE_DIR="${INSTALL_DIR}/deploy/botinstaller/systemd/core"

    if [ ! -d "$SYSTEMD_TEMPLATE_DIR" ]; then
        fail "systemd template directory not found"
    fi


    for file in "$SYSTEMD_TEMPLATE_DIR"/*.service "$SYSTEMD_TEMPLATE_DIR"/*.timer
    do
        [ -e "$file" ] || continue

        name=$(basename "$file")

        sed \
            "s#{{INSTALL_DIR}}#${INSTALL_DIR}#g" \
            "$file" \
            > "${SYSTEMD_DIR}/${name}"

        ok "Installed ${name}"
    done


    systemctl daemon-reload


    CORE_SERVICES="
zvertbot.service
stats-http.service
vps-stats.service
vps-stats.timer
geoip-collect.timer
zvertbot-vps-monitor.service
"


    for service in $CORE_SERVICES
    do
        if [[ "$service" == *.timer ]]; then
            if ! systemctl enable --now "$service" >/dev/null 2>&1; then
                fail "Failed to enable/start $service"
            fi

            if ! systemctl is-active --quiet "$service"; then
                fail "$service is not active after start"
            fi
        else
            if ! systemctl enable "$service" >/dev/null 2>&1; then
                fail "Failed to enable $service"
            fi

            if ! systemctl restart "$service" >/dev/null 2>&1; then
                fail "Failed to start $service"
            fi
        fi

        ok "Started $service"
    done


    OPTIONAL_DIR="${INSTALL_DIR}/deploy/botinstaller/systemd/optional"

    if [ -d "$OPTIONAL_DIR" ]; then

        info "Installing optional systemd templates"

        for file in "$OPTIONAL_DIR"/*.service "$OPTIONAL_DIR"/*.timer
        do
            [ -e "$file" ] || continue

            name=$(basename "$file")

            sed \
                "s#{{INSTALL_DIR}}#${INSTALL_DIR}#g" \
                "$file" \
                > "${SYSTEMD_DIR}/${name}"

            ok "Optional template installed: ${name}"
        done

        systemctl daemon-reload

        OPTIONAL_SERVICES="
xray-traffic.timer
zvertbot-backup.timer
"

        for service in $OPTIONAL_SERVICES
        do
            if [[ "$service" == *.timer ]]; then
                if ! systemctl enable --now "$service" >/dev/null 2>&1; then
                    fail "Failed to enable/start optional $service"
                fi

                if ! systemctl is-active --quiet "$service"; then
                    fail "Optional $service is not active after start"
                fi
            else
                if ! systemctl enable "$service" >/dev/null 2>&1; then
                    fail "Failed to enable optional $service"
                fi

                if ! systemctl restart "$service" >/dev/null 2>&1; then
                    fail "Failed to start optional $service"
                fi
            fi

            ok "Started optional $service"
        done

    fi


    ok "Systemd services installed"

}



verify_install() {

echo
echo -e "${CYAN}Checking services...${NC}"
echo

CHECKS="
zvertbot.service
zvertbot-vps-monitor.service
stats-http.service
vps-stats.timer
geoip-collect.timer
xray-traffic.timer
"

for s in $CHECKS
do
    if systemctl is-active --quiet "$s"; then
        ok "$s active"
    else
        warn "$s not active"
    fi
done


echo
echo -e "${CYAN}Checking timers...${NC}"

TIMERS="
vps-stats.timer
geoip-collect.timer
xray-traffic.timer
"

for t in $TIMERS
do
    if systemctl is-enabled --quiet "$t"; then
        ok "$t enabled"
    else
        warn "$t disabled"
    fi
done

}

summary() {

echo

echo -e "${GREEN}"
echo "======================================"
echo " ZverTBot installation completed"
echo "======================================"
echo -e "${NC}"

echo
echo "Location:"
echo "${INSTALL_DIR}"
echo

echo "Service:"
echo "zvertbot.service"
echo

echo "Commands:"
echo
echo "systemctl status zvertbot"
echo "journalctl -u zvertbot -f"
echo

}


main() {



check_root

check_os

check_network

extract_archive
banner

CHECK_SCRIPT="${INSTALL_DIR}/deploy/botinstaller/checks.sh"

if [ -f "$CHECK_SCRIPT" ]; then
    bash "$CHECK_SCRIPT"
else
    warn "checks.sh not found"
fi


install_packages
install_rclone


# System tuning
TUNING_SCRIPT="${INSTALL_DIR}/deploy/botinstaller/system_tuning.sh"

if [ -f "$TUNING_SCRIPT" ]; then
    bash "$TUNING_SCRIPT"
else
    warn "system_tuning.sh not found"
fi


if [ "$INSTALL_XRAY" = true ]; then
    install_xray
fi

if [ "$INSTALL_AWG" = true ]; then
    install_awg
fi


create_env
enable_ip_forwarding
create_runtime_files
create_venv

create_service

verify_install

summary

}


main
