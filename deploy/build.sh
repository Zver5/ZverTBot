#!/bin/bash

set -e

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-$BASE_DIR/deploy/output}"

APP_NAME="$(
    "$BASE_DIR/.venv/bin/python" - "$BASE_DIR/config/config.py" <<'PY_PROJECT_NAME'
from pathlib import Path
import re
import sys

config = Path(sys.argv[1])
text = config.read_text(encoding="utf-8")

match = re.search(
    r'^\s*BOT_NAME\s*=\s*"([^"]+)"\s*$',
    text,
    re.MULTILINE,
)

if not match:
    raise SystemExit("BOT_NAME not found in config/config.py")

print(match.group(1))
PY_PROJECT_NAME
)"

if [ -z "$APP_NAME" ]; then
    echo "Unable to determine BOT_NAME from config/config.py" >&2
    exit 1
fi

BUILD_DIR="${BUILD_DIR:-/tmp/${APP_NAME}-build}"

VERSION="$(
    "$BASE_DIR/.venv/bin/python" - <<'PY_VERSION'
import re
from pathlib import Path

path = Path("config/config.py")
text = path.read_text(encoding="utf-8")

match = re.search(
    r'^\s*BOT_VERSION\s*=\s*"([^"]+)"\s*$',
    text,
    re.MULTILINE,
)

if not match:
    raise SystemExit("BOT_VERSION not found in config/config.py")

version = match.group(1)

if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    raise SystemExit(f"Invalid BOT_VERSION: {version}")

print(version)
PY_VERSION
)"

echo "================================="
echo " ZverTBot Builder ${VERSION}"
echo "================================="


rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/$APP_NAME"
mkdir -p "$OUTPUT_DIR"

rsync -a \
--exclude=".git" \
--exclude=".venv" \
--exclude=".env" \
--exclude=".env.example" \
--exclude="__pycache__" \
--exclude="*.pyc" \
--exclude=".pytest_cache" \
--exclude=".ruff_cache" \
--exclude=".coverage" \
--exclude="htmlcov" \
--exclude="deploy/output" \
--filter="+ data/" \
--filter="+ data/asn_types.json" \
--filter="+ data/ru_geo.conf" \
--filter="+ data/storage.py" \
--filter="+ data/traffic.py" \
--exclude="data/geoip/*" \
--filter="- data/*" \
--exclude="hass/stats/*.json" \
--exclude="hass/traffic/*.json" \
--exclude="hass/geo/*.json" \
--exclude="hass/backup/*.json" \
--exclude="logs/*" \
--exclude="*.log" \
--exclude="*.bak" \
--exclude="*.backup" \
--exclude="*.backup_*" \
--exclude="*.before*" \
--exclude="scripts/*fix_*.py" \
--exclude="scripts/*patch_*.py" \
--exclude="scripts/*cleanup_*.py" \
"$BASE_DIR/" \
"$BUILD_DIR/$APP_NAME/"

cp "$BASE_DIR/.env.example" \
"$BUILD_DIR/$APP_NAME/deploy/botinstaller/.env.example"

cd "$BUILD_DIR"

tar -czf \
"$OUTPUT_DIR/${APP_NAME}-deploy-${VERSION}.tar.gz" \
"$APP_NAME"

echo
echo "================================="
echo " ГОТОВО"
echo "================================="

ls -lh "$OUTPUT_DIR/${APP_NAME}-deploy-${VERSION}.tar.gz"

cp "$BASE_DIR/deploy/botinstaller/install.sh" \
"$OUTPUT_DIR/install.sh"

chmod +x "$OUTPUT_DIR/install.sh"

echo
echo "Installer:"
ls -lh "$OUTPUT_DIR/install.sh"
