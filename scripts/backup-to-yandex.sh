#!/bin/bash
# Backup script for ZverTBot VPS
# Version: 2.0
#
# Изменения v2.0:
# - добавлен бэкап /etc/amnezia/amneziawg/ (реальные файлы, не симлинки)
# - добавлены исключения *.log и *.tmp в tar (уменьшение размера архива)
# - синхронизирована версия в заголовке с BACKUP_VERSION
# - убраны устаревшие пути (/usr/local/etc/vpn-traffic, /root/check_passport_*.py)
#
# Восстановление:
# tar -xzf backup.tar.gz -C /

set -e
set -o pipefail

# ============================================================
# CONFIG
# ============================================================

BACKUP_VERSION="2.0"

# ZverTBot installation directory
INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Load project environment.
if [ -f "${INSTALL_DIR}/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${INSTALL_DIR}/.env"
    set +a
fi


PASSPORT_DIR="${PASSPORT_DIR:-/root/passport}"

BACKUP_DIR="${CONFIG_BACKUPS_DIR:-/root/config-backups}"

DATE=$(TZ='Europe/Moscow' date +%Y-%m-%d_%H-%M-%S)

BACKUP_NAME="vps-backup-${DATE}.tar.gz"

# Backup configuration is loaded from the project .env.
BACKUP_REMOTE="${BACKUP_REMOTE:-}"
BACKUP_ROOT_DIR="${BACKUP_ROOT_DIR:-}"

STATUS_FILE="${INSTALL_DIR}/hass/backup/rclone_backup_status.json"

STATUS_WRITTEN=0

log_info() {
    printf "[INFO] %s\n" "$*"
}

log_warn() {
    printf "[WARN] %s\n" "$*" >&2
}

log_error() {
    printf "[ERROR] %s\n" "$*" >&2
}

write_failed_status() {
    local rc="${1:-1}"
    local error="${2:-Backup script failed}"

    if ! mkdir -p "$(dirname "${STATUS_FILE}")" 2>/dev/null; then
        log_error "backup.status.directory_create_failed"
        return 1
    fi

    if ! cat > "${STATUS_FILE}" << EOF
{
  "last_backup": "$(TZ='Europe/Moscow' date -Iseconds)",
  "status": "failed",
  "size_mb": "$(du -m "${BACKUP_DIR}/${BACKUP_NAME}" 2>/dev/null | cut -f1)",
  "file_name": "${BACKUP_NAME}",
  "remote": "${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}",
  "error": "${error}",
  "code": ${rc}
}
EOF
    then
        log_error "backup.status.write_failed"
        return 1
    fi

    STATUS_WRITTEN=1
}

handle_unexpected_error() {
    local rc=$?

    if [ "${STATUS_WRITTEN}" -eq 0 ]; then
        write_failed_status "${rc}" "Unexpected backup script failure"
    fi

    exit "${rc}"
}

set -E
trap 'handle_unexpected_error' ERR

mkdir -p "${BACKUP_DIR}"

TEMP_DIR=$(mktemp -d)

trap "rm -rf ${TEMP_DIR}" EXIT


log_info "backup.started | version=${BACKUP_VERSION} | file=${BACKUP_NAME}"


cd /


# ============================================================
# 🔴 CRITICAL SYSTEM FILES
# ============================================================

log_info "backup.section.started | section=critical"


# Xray

if [ -e /usr/local/etc/xray/config.json ]; then

    cp --parents \
    /usr/local/etc/xray/config.json \
    "${TEMP_DIR}/"

fi



# Telegram bot PROJECT

if [ -d ${INSTALL_DIR} ]; then

    cp -r --parents \
    ${INSTALL_DIR} \
    "${TEMP_DIR}/"

else

    log_error "backup.project.missing | path=${INSTALL_DIR}"
    exit 1

fi



# SSH

if [ -d /root/.ssh ]; then

    cp -r --parents \
    /root/.ssh \
    "${TEMP_DIR}/"

fi



# rclone token

if [ -d /root/.config/rclone ]; then

    cp -r --parents \
    /root/.config/rclone \
    "${TEMP_DIR}/"

fi



# firewall

if [ -d /etc/iptables ]; then

    cp -r --parents \
    /etc/iptables \
    "${TEMP_DIR}/"

fi



# sysctl

if [ -e /etc/sysctl.conf ]; then

    cp --parents \
    /etc/sysctl.conf \
    "${TEMP_DIR}/"

fi


# НОВОЕ v2.0: бэкап /etc/amnezia/amneziawg/ (реальные файлы, не симлинки)
if [ -d /etc/amnezia/amneziawg ]; then

    # Копируем только реальные файлы, игнорируя симлинки.
    # Ошибка копирования не должна быть проигнорирована.
    if ! find /etc/amnezia/amneziawg -type f -exec cp --parents {} "${TEMP_DIR}/" \; 2>/dev/null; then
        log_error "backup.awg.copy_failed | path=/etc/amnezia/amneziawg"
        write_failed_status 1 "Failed to copy AmneziaWG configuration"
        exit 1
    fi

fi


log_info "backup.section.completed | section=critical"



# ============================================================
# 🟡 SERVICES
# ============================================================

log_info "backup.section.started | section=services"





# systemd services

for SERVICE in \
zvertbot.service \
healthcheck.service \
kuma-webhook.service \
stats-http.service \
vps-stats.service \
xray-traffic.service \
geoip-collect.service \
zvertbot-backup.service

do

if [ -e "/etc/systemd/system/${SERVICE}" ]; then

cp --parents \
"/etc/systemd/system/${SERVICE}" \
"${TEMP_DIR}/"

fi

done



# systemd overrides

for DIR in \
/etc/systemd/system/xray.service.d \
/etc/systemd/system/awg-quick@awg0.service.d

do

if [ -d "${DIR}" ]; then

cp -r --parents \
"${DIR}" \
"${TEMP_DIR}/"

fi

done


log_info "backup.section.completed | section=services"

# systemd timers
for TIMER in \
vps-stats.timer \
xray-traffic.timer \
geoip-collect.timer \
zvertbot-backup.timer
do
    if [ -e "/etc/systemd/system/${TIMER}" ]; then
        cp --parents \
        "/etc/systemd/system/${TIMER}" \
        "${TEMP_DIR}/"
    fi
done

log_info "backup.section.completed | section=timers"
# ============================================================
# 🟢 ADDITIONAL FILES
# ============================================================

log_info "backup.section.started | section=additional"



# passport

if [ -d "${PASSPORT_DIR}" ]; then

cp -r --parents \
"${PASSPORT_DIR}" \
"${TEMP_DIR}/"

fi





# system configs

for FILE in \
/etc/fstab \
/etc/logrotate.d/rsyslog \
/etc/apt/apt.conf.d/50unattended-upgrades \
/etc/systemd/journald.conf

do

if [ -e "${FILE}" ]; then

cp --parents \
"${FILE}" \
"${TEMP_DIR}/"

fi

done



log_info "backup.section.completed | section=additional"



# ============================================================
# 🐻 KUMA DATABASE
# ============================================================

if [ -d /opt/uptime-kuma/data ]; then

log_info "backup.kuma.started"

mkdir -p \
"${TEMP_DIR}/opt/uptime-kuma/data"


if ! tar -czf \
"${TEMP_DIR}/opt/uptime-kuma/data/kuma-data.tar.gz" \
-C /opt/uptime-kuma/data .; then
    log_error "backup.kuma.archive_failed"

    if ! write_failed_status 1 "Failed to create Kuma archive"; then
        log_error "backup.status.write_failed"
    fi

    exit 1
fi


fi



# ============================================================
# CREATE ARCHIVE
# ============================================================

log_info "backup.archive.create_started | file=${BACKUP_NAME}"


if ! tar \
--exclude="__pycache__" \
--exclude="*.pyc" \
--exclude="*.backup" \
--exclude="usage_before_test.json" \
--exclude="usage_new_before_restore.json" \
--exclude=".venv" \
--exclude=".git" \
--exclude=".pytest_cache" \
--exclude=".backup_before_cleanup" \
--exclude="*.bak" \
--exclude="*.log" \
--exclude="*.tmp" \
-czf \
"${BACKUP_DIR}/${BACKUP_NAME}" \
-C "${TEMP_DIR}" .; then
    log_error "backup.archive.create_failed | file=${BACKUP_NAME}"

    if ! write_failed_status 1 "Failed to create backup archive"; then
        log_error "backup.status.write_failed"
    fi

    exit 1
fi


log_info "backup.archive.created | file=${BACKUP_NAME}"

log_info "backup.archive.verify_started | file=${BACKUP_NAME}"
if tar -tzf "${BACKUP_DIR}/${BACKUP_NAME}" >/dev/null 2>&1; then
    log_info "backup.archive.verified | file=${BACKUP_NAME}"
else
    log_error "backup.archive.verify_failed | file=${BACKUP_NAME}"

    if ! write_failed_status 1 "Backup archive is corrupted"; then
        log_error "backup.status.write_failed"
    fi

    exit 1
fi

ls -lh \
"${BACKUP_DIR}/${BACKUP_NAME}"



# ============================================================
# CHECK RCLONE CONFIGURATION
# ============================================================

if [ -z "${BACKUP_REMOTE}" ] || [ -z "${BACKUP_ROOT_DIR}" ]; then
    log_warn "backup.remote.not_configured"
    log_info "backup.local_only | file=${BACKUP_NAME}"


    cat > "${STATUS_FILE}" <<EOF
{
  "status": "local_only",
  "last_backup": "$(TZ='Europe/Moscow' date -Iseconds)",
  "file_name": "${BACKUP_NAME}",
  "size_mb": "$(du -m "${BACKUP_DIR}/${BACKUP_NAME}" | cut -f1)",
  "remote": "",
  "error": "Backup remote is not configured"
}
EOF

    exit 2
fi

RCLONE_REMOTES_FILE="${TEMP_DIR}/rclone-remotes.txt"

if ! rclone listremotes > "${RCLONE_REMOTES_FILE}" 2>/dev/null; then
    log_error "backup.remote.list_failed | remote=${BACKUP_REMOTE}"

    if ! write_failed_status 1 "Failed to list rclone remotes"; then
        log_error "backup.status.write_failed"
    fi

    exit 1
fi

if ! grep -Fxq "${BACKUP_REMOTE}:" "${RCLONE_REMOTES_FILE}"; then
    log_warn "backup.remote.not_found | remote=${BACKUP_REMOTE}"
    log_info "backup.local_only | file=${BACKUP_NAME}"

    cat > "${STATUS_FILE}" <<EOF
{
  "status": "local_only",
  "last_backup": "$(TZ='Europe/Moscow' date -Iseconds)",
  "file_name": "${BACKUP_NAME}",
  "size_mb": "$(du -m "${BACKUP_DIR}/${BACKUP_NAME}" | cut -f1)",
  "remote": "${BACKUP_REMOTE}",
  "error": "Configured rclone remote is missing"
}
EOF

    exit 2
fi

# ============================================================
# UPLOAD BACKUP
# ============================================================

log_info "backup.remote.upload_started | remote=${BACKUP_REMOTE} | file=${BACKUP_NAME}"

if ! rclone copy \
"${BACKUP_DIR}/${BACKUP_NAME}" \
"${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}/configs/" \
--progress; then
    log_error "backup.remote.upload_failed | remote=${BACKUP_REMOTE} | file=${BACKUP_NAME}"

    if ! write_failed_status 1 "Failed to upload backup to remote"; then
        log_error "backup.status.write_failed"
    fi

    exit 1
fi

log_info "backup.remote.uploaded | remote=${BACKUP_REMOTE} | file=${BACKUP_NAME}"

log_info "backup.remote.verify_started | remote=${BACKUP_REMOTE} | file=${BACKUP_NAME}"
REMOTE_UPLOAD_LIST="${TEMP_DIR}/uploaded-backups.txt"

if ! rclone lsf "${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}/configs/" --files-only > "${REMOTE_UPLOAD_LIST}"; then
    log_error "backup.remote.verify_failed | file=${BACKUP_NAME}"

    if ! write_failed_status 1 "Failed to verify uploaded archive"; then
        log_error "backup.status.write_failed"
    fi

    exit 1
fi

if grep -Fxq "${BACKUP_NAME}" "${REMOTE_UPLOAD_LIST}"; then
    log_info "backup.remote.verified | file=${BACKUP_NAME}"
else
    log_error "backup.remote.archive_not_found | remote=${BACKUP_REMOTE} | file=${BACKUP_NAME}"

    if ! write_failed_status 1 "Uploaded archive was not found on remote"; then
        log_error "backup.status.write_failed"
    fi

    exit 1
fi



# ============================================================
# PASSPORTS
# ============================================================

if [ -d "${PASSPORT_DIR}" ]; then

if ! rclone copy \
"${PASSPORT_DIR}/" \
"${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}/passport/" \
--progress; then
    log_error "backup.passport.upload_failed | remote=${BACKUP_REMOTE}"

    if ! write_failed_status 1 "Failed to upload passports to remote"; then
        log_error "backup.status.write_failed"
    fi

    exit 1
fi

fi



# ============================================================
# CLEAN LOCAL
# ============================================================

log_info "backup.local_retention.started"


cd "${BACKUP_DIR}"


BACKUP_FILES=()
while IFS= read -r FILE; do
    BACKUP_FILES+=("${FILE}")
done < <(
    find "${BACKUP_DIR}" \
        -maxdepth 1 \
        -type f \
        -name 'vps-backup-*.tar.gz' \
        -printf '%T@ %p\n' \
        2>/dev/null | sort -nr
)

if [ "${#BACKUP_FILES[@]}" -gt 5 ]; then
    for ((i=5; i<${#BACKUP_FILES[@]}; i++)); do
        rm -f -- "${BACKUP_FILES[$i]#* }"
    done
fi



# ============================================================
# CLEAN YANDEX
# ============================================================

log_info "backup.remote_retention.started"


REMOTE_BACKUPS_FILE="${TEMP_DIR}/remote-backups.txt"

if ! rclone lsf \
"${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}/configs/" \
--files-only > "${REMOTE_BACKUPS_FILE}" 2>/dev/null; then
    log_error "backup.remote_retention.list_failed | remote=${BACKUP_REMOTE}"

    if ! write_failed_status 1 "Failed to list remote backups"; then
        log_error "backup.status.write_failed"
    fi

    exit 1
fi

REMOTE_BACKUPS_TO_DELETE=()
while IFS= read -r FILE; do
    REMOTE_BACKUPS_TO_DELETE+=("${FILE}")
done < <(
    awk '/vps-backup-.*\.tar.gz/ {print}' "${REMOTE_BACKUPS_FILE}" | sort -r
)

if [ "${#REMOTE_BACKUPS_TO_DELETE[@]}" -gt 10 ]; then
    REMOTE_BACKUPS_TO_DELETE=(
        "${REMOTE_BACKUPS_TO_DELETE[@]:10}"
    )
fi

for FILE in "${REMOTE_BACKUPS_TO_DELETE[@]}"; do
    if ! rclone delete \
    "${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}/configs/${FILE}" \
    2>/dev/null; then
        log_warn "backup.remote_retention.delete_failed | file=${FILE}"
    fi
done


# ============================================================
# STATUS JSON
# ============================================================


SIZE_BYTES=$(stat -c%s "${BACKUP_DIR}/${BACKUP_NAME}" 2>/dev/null || echo 0)

SIZE_MB=$((SIZE_BYTES / 1048576))


NEXT_RUN=$(TZ='Europe/Moscow' date -d "+8 hours" -Iseconds)



mkdir -p "$(dirname "${STATUS_FILE}")"


cat > "${STATUS_FILE}" << EOF
{
  "last_backup": "$(TZ='Europe/Moscow' date -Iseconds)",
  "status": "success",
  "size_mb": ${SIZE_MB},
  "next_run": "${NEXT_RUN}",
  "file_name": "${BACKUP_NAME}"
}
EOF



log_info "backup.completed | file=${BACKUP_NAME} | size_mb=${SIZE_MB} | remote=${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}/configs/"
log_info "backup.restore | command=tar -xzf ${BACKUP_NAME} -C /"
