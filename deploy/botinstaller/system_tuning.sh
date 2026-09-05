#!/bin/bash

set -e

echo "================================="
echo " ZverTBot System Tuning"
echo "================================="

# ----------------------------------------------------------
# IPv4 priority over IPv6
# ----------------------------------------------------------

GAI_CONF="/etc/gai.conf"

if ! grep -q "^precedence ::ffff:0:0/96  100" "$GAI_CONF" 2>/dev/null; then
    echo "precedence ::ffff:0:0/96  100" >> "$GAI_CONF"
    echo "✅ IPv4 priority added"
else
    echo "ℹ️ IPv4 priority already configured"
fi


# ----------------------------------------------------------
# Network conntrack tuning
# ----------------------------------------------------------

SYSCTL_CONF="/etc/sysctl.d/99-zvertbot.conf"

cat > "$SYSCTL_CONF" <<EOF
# ZverTBot network tuning

net.netfilter.nf_conntrack_max=262144
net.netfilter.nf_conntrack_tcp_timeout_established=432000
net.netfilter.nf_conntrack_tcp_timeout_close_wait=60
net.netfilter.nf_conntrack_tcp_timeout_time_wait=120
EOF

if ! modprobe nf_conntrack; then
    echo "⚠️ nf_conntrack module could not be loaded"
fi

if [ -e /proc/sys/net/netfilter/nf_conntrack_max ]; then
    sysctl --system >/dev/null
    echo "✅ nf_conntrack configured"
else
    echo "⚠️ nf_conntrack unavailable in kernel"
fi


# ----------------------------------------------------------
# systemd journald limits
# ----------------------------------------------------------

JOURNALD="/etc/systemd/journald.conf"

set_journal_param() {
    PARAM="$1"
    VALUE="$2"

    if grep -q "^#\?${PARAM}=" "$JOURNALD"; then
        sed -i "s|^#\?${PARAM}=.*|${PARAM}=${VALUE}|" "$JOURNALD"
    else
        echo "${PARAM}=${VALUE}" >> "$JOURNALD"
    fi
}

set_journal_param "SystemMaxUse" "100M"
set_journal_param "RuntimeMaxUse" "50M"
set_journal_param "MaxRetentionSec" "7day"
set_journal_param "Compress" "yes"

systemctl restart systemd-journald

echo "✅ journald configured"


echo "================================="
echo " System tuning complete"
echo "================================="
