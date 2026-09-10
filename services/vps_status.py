from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VPSStatus:
    """Public, HA-facing status model for a VPS."""

    server_ip: str
    system: dict[str, Any] = field(default_factory=dict)
    services: dict[str, Any] = field(default_factory=dict)
    backup: dict[str, Any] = field(default_factory=dict)
    fail2ban: dict[str, Any] = field(default_factory=dict)
    connections: list[dict[str, Any]] = field(default_factory=list)
    awg_clients: list[dict[str, Any]] = field(default_factory=list)
    xray_clients: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the stable public contract consumed by HA."""
        return {
            "server": {
                "ip": self.server_ip,
            },
            "system": self.system,
            "services": self.services,
            "backup": self.backup,
            "fail2ban": self.fail2ban,
            "connections": self.connections,
            "awg": {
                "clients": self.awg_clients,
            },
            "xray": {
                "clients": self.xray_clients,
            },
            "updated_at": self.updated_at,
        }


def build_vps_status(raw: dict[str, Any]) -> VPSStatus:
    """Adapt the current stats.json structure to the public model."""

    disk = raw.get("disk") or {}

    services: dict[str, Any] = {}
    for name, data in (raw.get("services") or {}).items():
        if not isinstance(data, dict):
            continue

        services[name] = {
            "status": data.get("status"),
            "uptime": data.get("uptime"),
        }

    backup_raw = raw.get("rclone") or {}

    fail2ban_raw = raw.get("fail2ban") or {}

    awg_clients: list[dict[str, Any]] = []
    xray_clients: list[dict[str, Any]] = []

    for client in raw.get("peers") or []:
        if not isinstance(client, dict):
            continue

        awg_clients.append(
            {
                "name": client.get("name"),
                "ip": client.get("ip"),
                "online": client.get("online"),
                "endpoint": client.get("endpoint"),
                "last_ip": client.get("last_ip"),
                "last_seen": client.get("last_seen"),
                "rx": client.get("rx"),
                "tx": client.get("tx"),
                "total_bytes": client.get("total_bytes"),
                "geoip": _public_geoip(client.get("geoip")),
            }
        )

    for client in raw.get("xray_clients") or []:
        if not isinstance(client, dict):
            continue

        xray_clients.append(
            {
                "name": client.get("name"),
                "ip": client.get("ip"),
                "online": client.get("online"),
                "endpoint": client.get("endpoint"),
                "last_ip": client.get("last_ip"),
                "last_seen": client.get("last_seen"),
                "hs": client.get("hs"),
                "rx": client.get("rx"),
                "tx": client.get("tx"),
                "total_bytes": client.get("total_bytes"),
                "geoip": _public_geoip(client.get("geoip")),
            }
        )

    return VPSStatus(
        server_ip=str(raw.get("server_ip") or ""),
        system={
            "cpu": raw.get("cpu"),
            "memory_percent": raw.get("mem"),
            "disk": {
                "used_gb": disk.get("used_gb"),
                "free_gb": disk.get("free_gb"),
                "total_gb": disk.get("total_gb"),
                "percent": disk.get("percent"),
            },
            "vpn_total_gb": raw.get("vpn_total_gb"),
        },
        services=services,
        backup={
            "status": backup_raw.get("status"),
            "last_backup": backup_raw.get("last_backup"),
            "size_mb": backup_raw.get("size_mb"),
            "next_run": backup_raw.get("next_run"),
        },
        fail2ban={
            "currently_banned": fail2ban_raw.get("currently_banned"),
            "total_banned": fail2ban_raw.get("total_banned"),
        },
        connections=_public_connections(raw.get("connections")),
        awg_clients=awg_clients,
        xray_clients=xray_clients,
        updated_at=raw.get("vps_stats_last_check"),
    )


def _public_geoip(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    allowed = (
        "ip",
        "country",
        "city",
        "isp",
        "type",
        "emoji",
        "asn",
        "mobile",
        "accuracy",
        "location_source",
    )

    return {key: value[key] for key in allowed if key in value}


def _public_connections(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    result: list[dict[str, Any]] = []

    for connection in value:
        if not isinstance(connection, dict):
            continue

        allowed = (
            "type",
            "name",
            "ip",
            "port",
            "rx",
            "tx",
            "status",
            "hs",
        )

        result.append(
            {
                key: connection[key]
                for key in allowed
                if key in connection
            }
        )

    return result
