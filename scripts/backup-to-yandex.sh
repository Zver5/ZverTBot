#!/bin/bash
# Backup script for ZverTBot VPS
# Version: 2.1
#
# Назначение:
# - создаёт полный конфигурационный backup VPS;
# - сохраняет конфигурацию ZverTBot, Xray, SSH, rclone и firewall;
# - сохраняет реальные конфигурационные файлы AmneziaWG;
# - сохраняет systemd-сервисы и timers ZverTBot;
# - загружает архив и passport-файлы в облачный remote;
# - поддерживает локальную и облачную retention-политику;
# - записывает результат в hass/backup/rclone_backup_status.json.
#
# Мониторинг VPS в backup не реализуется.
# Состояние VPS отслеживает отдельный zvertbot-vps-monitor.service.
#
# Восстановление:
# tar -xzf backup.tar.gz -C /

set -e
set -o pipefail

# ============================================================
# CONFIG
# ============================================================

BACKUP_VERSION="2.1"

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
BACKUP_START_TIME=$(date +%s)

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
    local size_mb=""
    local tmp_file="${STATUS_FILE}.tmp.$$"

    size_mb="$(du -m "${BACKUP_DIR}/${BACKUP_NAME}" 2>/dev/null | cut -f1 || true)"

    if ! command -v jq >/dev/null 2>&1; then
        log_error "backup.status.jq_missing"
        return 1
    fi
    if ! mkdir -p "$(dirname "${STATUS_FILE}")" 2>/dev/null; then
        log_error "backup.status.directory_create_failed"
        return 1
    fi

    if ! jq -n \
        --arg last_backup "$(TZ='Europe/Moscow' date -Iseconds)" \
        --arg status "failed" \
        --arg size_mb "${size_mb}" \
        --arg file_name "${BACKUP_NAME}" \
        --arg remote "${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}" \
        --arg error "${error}" \
        --argjson code "${rc}" \
        '{last_backup:$last_backup,status:$status,size_mb:$size_mb,file_name:$file_name,remote:$remote,error:$error,code:$code}' \
        > "${tmp_file}"; then
        rm -f -- "${tmp_file}"
        log_error "backup.status.write_failed"
        return 1
    fi

    if ! jq -e . "${tmp_file}" >/dev/null 2>&1 ||
       ! mv -f -- "${tmp_file}" "${STATUS_FILE}"; then
        rm -f -- "${tmp_file}"
        log_error "backup.status.write_failed"
        return 1
    fi

    STATUS_WRITTEN=1
}

write_local_only_status() {
    local remote="${1:-}"
    local error="${2:-Backup remote is not configured}"
    local size_mb=""
    local tmp_file="${STATUS_FILE}.tmp.$$"

    size_mb="$(du -m "${BACKUP_DIR}/${BACKUP_NAME}" 2>/dev/null | cut -f1 || true)"

    if ! command -v jq >/dev/null 2>&1; then
        log_error "backup.status.jq_missing"
        return 1
    fi
    if ! mkdir -p "$(dirname "${STATUS_FILE}")" 2>/dev/null; then
        log_error "backup.status.directory_create_failed"
        return 1
    fi

    if ! jq -n \
        --arg status "local_only" \
        --arg last_backup "$(TZ='Europe/Moscow' date -Iseconds)" \
        --arg file_name "${BACKUP_NAME}" \
        --arg size_mb "${size_mb}" \
        --arg remote "${remote}" \
        --arg error "${error}" \
        '{status:$status,last_backup:$last_backup,file_name:$file_name,size_mb:$size_mb,remote:$remote,error:$error}' \
        > "${tmp_file}"; then
        rm -f -- "${tmp_file}"
        log_error "backup.status.write_failed"
        return 1
    fi

    if ! jq -e . "${tmp_file}" >/dev/null 2>&1 ||
       ! mv -f -- "${tmp_file}" "${STATUS_FILE}"; then
        rm -f -- "${tmp_file}"
        log_error "backup.status.write_failed"
        return 1
    fi

    STATUS_WRITTEN=1
}

write_success_status() {
    local tmp_file="${STATUS_FILE}.tmp.$$"

    if ! command -v jq >/dev/null 2>&1; then
        log_error "backup.status.jq_missing"
        return 1
    fi
    if ! mkdir -p "$(dirname "${STATUS_FILE}")" 2>/dev/null; then
        log_error "backup.status.directory_create_failed"
        return 1
    fi

    if ! jq -n \
        --arg last_backup "$(TZ='Europe/Moscow' date -Iseconds)" \
        --arg status "success" \
        --argjson size_mb "${SIZE_MB}" \
        --argjson duration_sec "${BACKUP_DURATION_SEC}" \
        --arg next_run "${NEXT_RUN}" \
        --arg file_name "${BACKUP_NAME}" \
        --arg remote "${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}/configs/" \
        '{last_backup:$last_backup,status:$status,size_mb:$size_mb,duration_sec:$duration_sec,next_run:$next_run,file_name:$file_name,remote:$remote}' \
        > "${tmp_file}"; then
        rm -f -- "${tmp_file}"
        log_error "backup.status.write_failed"
        return 1
    fi

    if ! jq -e . "${tmp_file}" >/dev/null 2>&1 ||
       ! mv -f -- "${tmp_file}" "${STATUS_FILE}"; then
        rm -f -- "${tmp_file}"
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

if [ -d "${INSTALL_DIR}" ]; then

    cp -r --parents \
    "${INSTALL_DIR}" \
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

    # Сначала сохраняем список файлов, затем проверяем каждое копирование.
    AWG_FILES_LIST="${TEMP_DIR}/awg-files.list"
    if ! find /etc/amnezia/amneziawg -type f -print0 > "${AWG_FILES_LIST}" 2>/dev/null; then
        log_error "backup.awg.find_failed"
        write_failed_status 1 "Failed to list AmneziaWG configuration files" || true
        exit 1
    fi

    while IFS= read -r -d '' FILE; do
        if ! cp --parents "$FILE" "${TEMP_DIR}/"; then
            log_error "backup.awg.copy_failed | path=${FILE}"
            write_failed_status 1 "Failed to copy AmneziaWG configuration" || true
            exit 1
        fi
    done < "${AWG_FILES_LIST}"

fi


log_info "backup.section.completed | section=critical"



# ============================================================
# 🟡 SERVICES
# ============================================================

log_info "backup.section.started | section=services"





# systemd services

for SERVICE in \
zvertbot.service \
zvertbot-vps-monitor.service \
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
/etc/systemd/system/xray.service.d

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
/etc/systemd/journald.conf \
/etc/sysctl.d/99-zvertbot-network.conf \
/etc/sysctl.d/99-zvertbot-swap.conf

do

if [ -e "${FILE}" ]; then

cp --parents \
"${FILE}" \
"${TEMP_DIR}/"

fi

done



log_info "backup.section.completed | section=additional"



# ============================================================
# CREATE ARCHIVE
# ============================================================

log_info "backup.archive.create_started | file=${BACKUP_NAME}"


if ! tar \
--exclude="__pycache__" \
--exclude="*.pyc" \
--exclude="*.backup" \
--exclude=".venv" \
--exclude=".git" \
--exclude=".pytest_cache" \
--exclude=".ruff_cache" \
--exclude="data/geoip/*.mmdb" \
--exclude="deploy/output/*.tar.gz" \
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


    if ! write_local_only_status "" "Backup remote is not configured"; then
        log_error "backup.status.write_failed"
    fi

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

    if ! write_local_only_status "${BACKUP_REMOTE}" "Configured rclone remote is missing"; then
        log_error "backup.status.write_failed"
    fi

    exit 2
fi

# ============================================================
# UPLOAD BACKUP
# ============================================================

log_info "backup.remote.upload_started | remote=${BACKUP_REMOTE} | file=${BACKUP_NAME}"

RCLONE_UPLOAD_LOG="${TEMP_DIR}/rclone-upload.log"

if rclone copy \
"${BACKUP_DIR}/${BACKUP_NAME}" \
"${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}/configs/" \
--stats=1s \
--use-json-log \
--stats-log-level=INFO \
-vv 2> >(tee "${RCLONE_UPLOAD_LOG}" >&2); then
    :
else
    upload_rc=$?
    log_error "backup.remote.upload_failed | remote=${BACKUP_REMOTE} | file=${BACKUP_NAME} | code=${upload_rc}"

    error_detail="$(jq -r 'select((.level // "") == "error" or (.level // "") == "fatal") | .msg // empty' \
        "${RCLONE_UPLOAD_LOG}" 2>/dev/null | tail -n 3 | paste -sd '; ' -)"

    if [ -z "${error_detail}" ]; then
        error_detail="$(tail -n 8 "${RCLONE_UPLOAD_LOG}" 2>/dev/null | paste -sd ' ' - | cut -c1-700)"
    fi

    if [ -z "${error_detail}" ]; then
        error_detail="rclone завершился с ошибкой, код ${upload_rc}"
    fi

    if ! write_failed_status "${upload_rc}" "Не удалось загрузить бэкап в облако (${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}/configs/). Причина: ${error_detail}"; then
        log_error "backup.status.write_failed"
    fi

    exit "${upload_rc}"
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

# Проверяем содержимое архива на удалённой стороне, а не только имя.
log_info "backup.remote.check_started | file=${BACKUP_NAME}"
if ! rclone check \
    "${BACKUP_DIR}" \
    "${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}/configs/" \
    --one-way \
    --include "${BACKUP_NAME}"; then
    log_error "backup.remote.check_failed | file=${BACKUP_NAME}"
    write_failed_status 1 "Uploaded backup integrity check failed" || true
    exit 1
fi
log_info "backup.remote.check_passed | file=${BACKUP_NAME}"

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
# CLEAN CLOUD
# ============================================================

log_info "backup.cloud_retention.started"


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
    [ -n "${FILE}" ] || continue
    [ "${FILE}" = "${BACKUP_NAME}" ] && continue

    REMOTE_BACKUPS_TO_DELETE+=("${FILE}")
done < <(
    awk '/^vps-backup-.*\.tar.gz$/ {print}' "${REMOTE_BACKUPS_FILE}" | sort -r
)

if [ "${#REMOTE_BACKUPS_TO_DELETE[@]}" -gt 9 ]; then
    REMOTE_BACKUPS_TO_DELETE=(
        "${REMOTE_BACKUPS_TO_DELETE[@]:9}"
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
        FILE="${BACKUP_FILES[$i]#* }"

        if [ "${FILE}" = "${BACKUP_DIR}/${BACKUP_NAME}" ]; then
            continue
        fi

        rm -f -- "${FILE}"
    done
fi





# ============================================================
# STATUS JSON
# ============================================================


SIZE_BYTES=$(stat -c%s "${BACKUP_DIR}/${BACKUP_NAME}" 2>/dev/null || echo 0)

SIZE_MB=$((SIZE_BYTES / 1048576))

BACKUP_DURATION_SEC=$(( $(date +%s) - BACKUP_START_TIME ))

NEXT_RUN=$(TZ='Europe/Moscow' date -d "+8 hours" -Iseconds)



if ! write_success_status; then
    log_error "backup.status.write_failed"
    exit 1
fi



log_info "backup.completed | file=${BACKUP_NAME} | size_mb=${SIZE_MB} | remote=${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}/configs/"
log_info "backup.restore | command=tar -xzf ${BACKUP_NAME} -C /"
