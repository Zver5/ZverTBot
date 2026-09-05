"""
Расширенные тесты services/stats.py
"""

import json
from unittest.mock import Mock

import services.stats as st

# ==========================================================
# _build_status_text
# ==========================================================


def test_build_status_text_ok(monkeypatch, tmp_path):
    stats = tmp_path / "stats.json"

    stats.write_text(
        json.dumps(
            {
                "cpu": 10.5,
                "mem": 20.2,
                "disk": {"percent": 30.3},
                "vpn_total_gb": 12.34,
                "services": {"xray": 1, "awg": 0, "fail2ban": 2},
            }
        )
    )

    monkeypatch.setattr(st, "STATS_JSON", str(stats))
    text = st._build_status_text()

    assert "CPU" in text
    assert "10.5%" in text
    assert "xray" in text
    assert "работает" in text
    assert "остановлен" in text
    assert "не установлен" in text


def test_build_status_text_missing_file(monkeypatch):
    monkeypatch.setattr(st, "STATS_JSON", "/no/such/file.json")

    text = st._build_status_text()

    assert "Ошибка" in text


# ==========================================================
# get_bot_stats_text
# ==========================================================


def test_get_bot_stats_text_empty(monkeypatch):
    monkeypatch.setattr(st, "load_stats", lambda: {"commands": {}})

    text = st.get_bot_stats_text()

    assert "Статистика пуста" in text


def test_get_bot_stats_text_ok(monkeypatch):
    monkeypatch.setattr(
        st,
        "load_stats",
        lambda: {
            "commands": {"status": 5, "restart_xray": 3},
            "total_commands": 8,
            "start_date": "2026-01-01",
        },
    )

    text = st.get_bot_stats_text()

    assert "Статистика использования" in text
    assert "Статус VPS" in text
    assert "Перезапуск Xray" in text


def test_get_bot_stats_text_exception(monkeypatch):
    monkeypatch.setattr(st, "load_stats", Mock(side_effect=Exception("fail")))

    text = st.get_bot_stats_text()

    assert "Ошибка чтения статистики" in text


# ==========================================================
# get_client_stats_text
# ==========================================================


def test_client_stats_unknown_proto():
    assert st.get_client_stats_text("user", "test") == "❌ Неизвестный протокол"


def test_client_stats_vless_empty(monkeypatch):
    monkeypatch.setattr(st, "load_usage", dict)

    text = st.get_client_stats_text("user", "vless")

    assert "Ожидание" in text


def test_client_stats_vless_found(monkeypatch):
    monkeypatch.setattr(
        st,
        "load_usage",
        lambda: {"clients": {"user": {"uplink": 100, "downlink": 200, "total": 300}}},
    )

    monkeypatch.setattr(st, "fmt_traffic", lambda x: str(x))

    text = st.get_client_stats_text("user", "vless")

    assert "user" in text
    assert "300" in text


def test_client_stats_awg_not_found(monkeypatch):
    monkeypatch.setattr(st, "load_awg_registry", dict)

    text = st.get_client_stats_text("user", "awg")

    assert "Клиент не найден" in text


def test_client_stats_awg_online(monkeypatch):
    monkeypatch.setattr(st, "load_awg_registry", lambda: {"user": {"ip": "10.0.0.2"}})

    monkeypatch.setattr(
        st, "get_client_traffic", lambda x: {"uplink": 1, "downlink": 2, "total": 3}
    )

    monkeypatch.setattr(
        st.subprocess,
        "run",
        lambda *a, **kw: Mock(
            stdout=("peer\nallowed ips: 10.0.0.2\nlatest handshake: today")
        ),
    )

    monkeypatch.setattr(st, "fmt_traffic", lambda x: str(x))

    text = st.get_client_stats_text("user", "awg")

    assert "Активен" in text
    assert "10.0.0.2" in text


def test_build_status_service_dict_with_uptime(monkeypatch, tmp_path):
    stats = tmp_path / "stats.json"
    stats.write_text(
        json.dumps(
            {
                "cpu": 10,
                "mem": 20,
                "disk": {"percent": 30},
                "services": {
                    "xray": {"status": 1, "uptime": "2h 15m"},
                    "awg": {"status": 0, "uptime": None},
                },
            }
        )
    )

    monkeypatch.setattr(st, "STATS_JSON", str(stats))

    result = st._build_status_text()

    assert "xray" in result
    assert "2h 15m" in result
    assert "awg" in result
