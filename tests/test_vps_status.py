from services.vps_status import VPSStatus, build_vps_status


def test_empty_status_has_public_structure():
    status = VPSStatus(server_ip="1.2.3.4")

    assert status.to_dict() == {
        "server": {"ip": "1.2.3.4"},
        "system": {},
        "services": {},
        "backup": {},
        "fail2ban": {},
        "connections": [],
        "awg": {"clients": []},
        "xray": {"clients": []},
        "updated_at": None,
    }


def test_build_status_maps_current_stats():
    raw = {
        "server_ip": "1.2.3.4",
        "cpu": 12.5,
        "mem": 55.5,
        "disk": {
            "used_gb": 9.2,
            "free_gb": 5.4,
            "total_gb": 14.6,
            "percent": 63,
        },
        "vpn_total_gb": 100,
        "services": {
            "xray": {
                "status": 1,
                "uptime": "2 days",
            }
        },
        "rclone": {
            "status": "success",
            "last_backup": "2026-09-11T10:00:00",
            "size_mb": 66,
            "next_run": "2026-09-12T03:00:00",
        },
        "fail2ban": {
            "currently_banned": 2,
            "total_banned": 10,
        },
        "awg_clients": [
            {
                "name": "ZverPC",
                "ip": "10.66.66.3",
                "proto": "awg",
                "online": True,
                "endpoint": "1.2.3.4:5802",
                "last_ip": "5.6.7.8",
                "last_seen": "2026-09-11T10:00:00",
                "hs": "2026-09-11T09:59:55",
                "rx": "1 GB",
                "tx": "2 GB",
                "downlink": 1073741824,
                "uplink": 2147483648,
                "total": "3 GB",
                "total_bytes": 3221225472,
                "geoip": {
                    "ip": "5.6.7.8",
                    "country": "DE",
                    "city": "Frankfurt",
                    "isp": "Example ISP",
                    "emoji": "🏠",
                    "lat": "50.1",
                    "lon": "8.6",
                    "pubkey": "SECRET",
                },
            }
        ],
        "xray_clients": [
            {
                "name": "Work",
                "proto": "vless",
                "online": True,
                "endpoint": "active",
                "last_ip": "9.8.7.6",
                "last_seen": "2026-09-11T10:00:00",
                "downlink": 500,
                "uplink": 100,
                "total": "600 B",
            }
        ],
        "connections": [
            {
                "type": "HA-Tunnel",
                "ip": "127.0.0.1",
                "port": 8080,
                "status": "active",
                "secret": "must-not-leak",
            }
        ],
        "vps_stats_last_check": "2026-09-11T10:01:00",
    }

    result = build_vps_status(raw).to_dict()

    assert result["server"]["ip"] == "1.2.3.4"
    assert result["system"]["memory_percent"] == 55.5
    assert result["system"]["disk"]["free_gb"] == 5.4
    assert result["services"]["xray"]["status"] == 1
    assert result["backup"]["status"] == "success"
    assert result["fail2ban"]["currently_banned"] == 2
    assert result["awg"]["clients"][0]["name"] == "ZverPC"
    assert result["awg"]["clients"][0]["online"] is True
    assert result["awg"]["clients"][0]["endpoint"] == "1.2.3.4:5802"
    assert result["awg"]["clients"][0]["last_ip"] == "5.6.7.8"
    assert result["awg"]["clients"][0]["last_seen"] == "2026-09-11T10:00:00"
    assert result["awg"]["clients"][0]["hs"] == "2026-09-11T09:59:55"
    assert result["awg"]["clients"][0]["total_bytes"] == 3221225472
    assert result["awg"]["clients"][0]["downlink"] == 1073741824
    assert result["awg"]["clients"][0]["uplink"] == 2147483648
    assert result["awg"]["clients"][0]["geoip"]["city"] == "Frankfurt"
    assert result["xray"]["clients"][0]["name"] == "Work"
    assert result["xray"]["clients"][0]["downlink"] == 500
    assert result["xray"]["clients"][0]["uplink"] == 100
    assert "pubkey" not in result["awg"]["clients"][0]["geoip"]
    assert "lat" not in result["awg"]["clients"][0]["geoip"]
    assert result["connections"][0] == {
        "type": "HA-Tunnel",
        "ip": "127.0.0.1",
        "port": 8080,
        "status": "active",
    }
