from data import storage


def test_load_stats_default(tmp_path, monkeypatch):
    test_file = tmp_path / "stats.json"

    monkeypatch.setattr(storage, "BOT_STATS_FILE", str(test_file))

    stats = storage.load_stats()

    assert stats["commands"] == {}
    assert stats["total_commands"] == 0
    assert "start_date" in stats


def test_save_and_load_stats(tmp_path, monkeypatch):
    test_file = tmp_path / "stats.json"

    monkeypatch.setattr(storage, "BOT_STATS_FILE", str(test_file))

    expected = {
        "commands": {"/start": 5, "/status": 2},
        "start_date": "2026-07-04 16:00:00",
        "total_commands": 7,
    }

    storage.save_stats(expected)

    loaded = storage.load_stats()

    assert loaded == expected


def test_load_stats_repairs_empty_object(tmp_path, monkeypatch):
    test_file = tmp_path / "stats.json"
    test_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(storage, "BOT_STATS_FILE", str(test_file))

    stats = storage.load_stats()

    assert stats["commands"] == {}
    assert stats["total_commands"] == 0
    assert "start_date" in stats
