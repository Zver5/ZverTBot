from __future__ import annotations

import json

from services import vps_status_cli


def test_main_outputs_public_vps_status(monkeypatch, capsys):
    monkeypatch.setattr(
        vps_status_cli,
        "load_prepared_vps_payload",
        lambda: {
            "server_ip": "1.2.3.4",
            "cpu": 1.5,
            "mem": 42,
            "disk": {
                "used_gb": 10,
                "free_gb": 20,
                "total_gb": 30,
                "percent": 33.3,
            },
            "services": {},
            "rclone": {},
            "fail2ban": {},
            "connections": [],
            "awg_clients": [],
            "xray_clients": [],
            "vps_stats_last_check": "2026-09-11T01:00:00",
        },
    )

    assert vps_status_cli.main() == 0

    result = json.loads(capsys.readouterr().out)

    assert result["server"]["ip"] == "1.2.3.4"
    assert result["system"]["cpu"] == 1.5
    assert result["system"]["memory_percent"] == 42
    assert result["awg"]["clients"] == []
    assert result["xray"]["clients"] == []
