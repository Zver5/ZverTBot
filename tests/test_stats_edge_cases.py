from unittest.mock import Mock

import services.stats as st


def reset_cache():
    st._STATUS_CACHE = None
    st._STATUS_CACHE_TIME = 0


def test_status_cache_public(monkeypatch, tmp_path):
    reset_cache()

    f = tmp_path / "stats.json"
    f.write_text('{"cpu":1,"mem":2,"disk":{"percent":3},"services":{}}')

    monkeypatch.setattr(st, "STATS_JSON", str(f))

    text = st.get_status_text()

    assert "VPS ОТЧЕТ" in text


def test_status_swap_error(monkeypatch, tmp_path):
    reset_cache()

    f = tmp_path / "stats.json"
    f.write_text("{}")

    monkeypatch.setattr(st, "STATS_JSON", str(f))

    real_open = open

    def fake_open(path, *args, **kwargs):
        if path == "/proc/meminfo":
            raise Exception("mem fail")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)

    text = st._build_status_text()

    assert "Swap" in text


def test_awg_without_ip(monkeypatch):
    monkeypatch.setattr(st, "load_awg_registry", lambda: {"user": {}})

    text = st.get_client_stats_text("user", "awg")

    assert "Нет IP" in text


def test_awg_show_exception(monkeypatch):
    monkeypatch.setattr(st, "load_awg_registry", lambda: {"user": {"ip": "10.0.0.5"}})

    monkeypatch.setattr(
        st, "get_client_traffic", lambda x: {"uplink": 0, "downlink": 0, "total": 0}
    )

    monkeypatch.setattr(st.subprocess, "run", Mock(side_effect=Exception("awg fail")))

    text = st.get_client_stats_text("user", "awg")

    assert "Оффлайн" in text
