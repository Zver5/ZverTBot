#!/bin/bash

RED="\033[0;31m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
NC="\033[0m"

ok() {
    echo -e "${GREEN}[ OK ]${NC} $1"
}

fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    exit 1
}

info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}


echo
echo "================================="
echo " ZverTBot pre-install check"
echo "================================="
echo


if [ "$EUID" -ne 0 ]; then
    fail "Run installer as root"
fi

ok "Root"


if [ -f /etc/os-release ]; then
    . /etc/os-release
    ok "$PRETTY_NAME"
else
    fail "Cannot detect OS"
fi


if command -v curl >/dev/null; then
    ok "curl"
else
    fail "curl missing"
fi


if command -v python3 >/dev/null; then
    ok "python3"
else
    fail "python3 missing"
fi


if getent hosts api.telegram.org >/dev/null; then
    ok "DNS"
else
    fail "DNS resolution failed"
fi


if curl -fs https://api.telegram.org >/dev/null; then
    ok "Internet access"
else
    echo "[WARN] Telegram API unavailable"
fi


DISK=$(df / | awk 'NR==2 {print $4}')

if [ "$DISK" -gt 500000 ]; then
    ok "Disk space"
else
    echo "[WARN] Low disk space"
fi


echo
echo "Commands:"

for cmd in \
python3 \
curl \
git \
qrencode \
mtr \
jq
do
    if command -v $cmd >/dev/null; then
        ok "$cmd"
    else
        echo "[WARN] $cmd not installed yet"
    fi
done


echo
ok "Pre-install check complete"
