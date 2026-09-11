from __future__ import annotations

import json
import os
from typing import Any

from config.paths import (
    AWG_USERS_JSON,
    GEOIP_JSON,
    STATS_JSON,
    USAGE_JSON,
)


def fmt_traffic(value: Any) -> str:
    """Format traffic for the legacy stats JSON contract."""
    try:
        value = float(value)
        if value >= 1073741824:
            return f"{value / 1073741824:.2f} GB"
        if value >= 1048576:
            return f"{value / 1048576:.0f} MB"
        return f"{value / 1024:.0f} KB"
    except Exception:
        return "0 KB"


def load_prepared_vps_payload() -> dict[str, Any]:
    """Load and enrich the VPS payload used by HTTP and SSH consumers."""
    result = _load_json(STATS_JSON, {})
    geoip_data = _load_json(GEOIP_JSON, {})

    usage = _load_json(USAGE_JSON, {})
    clients = usage.get("clients", {}) if isinstance(usage, dict) else {}

    if not isinstance(clients, dict):
        clients = {}

    awg_registry = _load_json(AWG_USERS_JSON, {})
    if not isinstance(awg_registry, dict):
        awg_registry = {}

    result["awg_clients"] = _build_awg_clients(
        result.get("peers", []),
        awg_registry,
        clients,
        geoip_data,
    )
    result["xray_clients"] = _build_xray_clients(clients, geoip_data)

    return result


def _build_awg_clients(
    peers: Any,
    awg_registry: dict[str, Any],
    clients: dict[str, Any],
    geoip_data: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(peers, list):
        return []

    result = []

    for peer in peers:
        if not isinstance(peer, dict):
            continue

        name = peer.get("name")
        if not name or name not in awg_registry:
            continue

        total_bytes = peer.get("total_bytes", 0)
        usage_stats = clients.get(name, {})
        if not isinstance(usage_stats, dict):
            usage_stats = {}

        down = usage_stats.get("downlink", 0)
        up = usage_stats.get("uplink", 0)

        # Preserve the existing legacy behavior for /stats.json.
        if down == 0 and up == 0 and total_bytes > 0:
            down = int(total_bytes * 0.7)
            up = int(total_bytes * 0.3)

        registry_entry = awg_registry.get(name, {})
        if not isinstance(registry_entry, dict):
            registry_entry = {}

        total = down + up

        client_data = {
            "name": name,
            "ip": registry_entry.get("ip", "N/A"),
            "proto": "awg",
            "online": peer.get("online", False),
            "endpoint": peer.get("endpoint", "offline"),
            "last_ip": peer.get("last_ip", ""),
            "last_seen": peer.get("last_seen", "never"),
            "hs": peer.get("hs", "never"),
            "rx": fmt_traffic(down),
            "tx": fmt_traffic(up),
            "downlink": down,
            "uplink": up,
            "total": fmt_traffic(total),
            "total_bytes": total_bytes,
        }

        if name in geoip_data:
            client_data["geoip"] = geoip_data[name]

        result.append(client_data)

    return result


def _build_xray_clients(
    clients: dict[str, Any],
    geoip_data: dict[str, Any],
) -> list[dict[str, Any]]:
    result = []

    for name, stats in clients.items():
        if not isinstance(stats, dict):
            continue

        if stats.get("proto") != "vless":
            continue

        down = stats.get("downlink", 0)
        up = stats.get("uplink", 0)
        total = down + up
        is_online = stats.get("_delta", 0) > 100

        last_ip = stats.get("last_ip", "")
        last_seen = stats.get("last_seen", "never")

        client_data = {
            "name": name,
            "ip": last_ip,
            "last_ip": last_ip,
            "endpoint": "active" if is_online else "offline",
            "proto": "vless",
            "rx": fmt_traffic(down),
            "tx": fmt_traffic(up),
            "downlink": down,
            "uplink": up,
            "total": fmt_traffic(total),
            "online": is_online,
            "hs": "active" if is_online else "offline",
            "last_seen": last_seen,
        }

        if name in geoip_data:
            client_data["geoip"] = geoip_data[name]

        result.append(client_data)

    return result


def _load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default

    try:
        with open(path) as file:
            return json.load(file)
    except Exception:
        return default
