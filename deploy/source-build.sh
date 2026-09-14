#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-$BASE_DIR/deploy/output}"
APP_NAME="ZverTBot"
COMMIT_SHA="$(git -C "$BASE_DIR" rev-parse --short HEAD)"
COMMIT_TITLE="$(git -C "$BASE_DIR" log -1 --pretty=%s | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]\+/-/g; s/^-//; s/-$//')"
COMMIT_TITLE="${COMMIT_TITLE:-source}"
STAGING_DIR="$(mktemp -d)"
ARCHIVE="$OUTPUT_DIR/${APP_NAME}-source-${COMMIT_SHA}-${COMMIT_TITLE}.tar.gz"

cleanup() {
    rm -rf "$STAGING_DIR"
}
trap cleanup EXIT

mkdir -p "$OUTPUT_DIR"

rsync -a "$BASE_DIR/" "$STAGING_DIR/$APP_NAME/" \
    --exclude='.git/' \
    --exclude='.venv/' \
    --exclude='.env' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache/' \
    --exclude='.ruff_cache/' \
    --exclude='.coverage' \
    --exclude='htmlcov/' \
    --exclude='deploy/output/' \
    --include='data/asn_types.json' \
    --include='data/ru_geo.conf' \
    --include='data/storage.py' \
    --include='data/traffic.py' \
    --exclude='data/*.json' \
    --exclude='data/geoip/*' \
    --exclude='hass/stats/*.json' \
    --exclude='hass/traffic/*.json' \
    --exclude='hass/geo/*.json' \
    --exclude='hass/backup/*.json' \
    --exclude='logs/' \
    --exclude='*.log' \
    --exclude='*.bak' \
    --exclude='*.backup*' \
    --exclude='*.before*'

# Keep only files that can be safely redistributed as source.
find "$STAGING_DIR/$APP_NAME" -type f -name '.env' -delete
find "$STAGING_DIR/$APP_NAME" -type f -name '*.pem' -delete
find "$STAGING_DIR/$APP_NAME" -type f -name '*.key' -delete
find "$STAGING_DIR/$APP_NAME" -type f -name '*private*key*' -delete

rm -f "$ARCHIVE"
tar -czf "$ARCHIVE" -C "$STAGING_DIR" "$APP_NAME"

echo "Created: $ARCHIVE"
