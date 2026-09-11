from services.vps_status_source import _build_awg_clients


def test_awg_client_keeps_total_bytes_without_fake_direction_split():
    peers = [
        {
            "name": "alice",
            "total_bytes": 1000,
            "online": False,
        }
    ]
    awg_registry = {"alice": {"ip": "10.66.66.2"}}
    clients = {"alice": {"downlink": 0, "uplink": 0}}
    geoip_data = {}

    result = _build_awg_clients(peers, awg_registry, clients, geoip_data)

    assert len(result) == 1
    assert result[0]["downlink"] == 0
    assert result[0]["uplink"] == 0
    assert result[0]["total_bytes"] == 1000
    assert result[0]["total"] == "1 KB"


def test_awg_client_uses_real_direction_totals():
    peers = [
        {
            "name": "alice",
            "total_bytes": 9999,
            "online": False,
        }
    ]
    awg_registry = {"alice": {"ip": "10.66.66.2"}}
    clients = {"alice": {"downlink": 700, "uplink": 300}}
    geoip_data = {}

    result = _build_awg_clients(peers, awg_registry, clients, geoip_data)

    assert result[0]["downlink"] == 700
    assert result[0]["uplink"] == 300
    assert result[0]["total_bytes"] == 1000
    assert result[0]["total"] == "1 KB"
