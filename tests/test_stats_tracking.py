from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from core.stats_middleware import StatsMiddleware
from data import storage


def test_record_stat_action_increments_counters(tmp_path, monkeypatch):
    stats_file = tmp_path / "bot_stats.json"
    monkeypatch.setattr(storage, "BOT_STATS_FILE", str(stats_file))

    storage.record_stat_action("/start")
    storage.record_stat_action("/start")
    storage.record_stat_action("nav:home")

    stats = storage.load_stats()
    assert stats["commands"]["/start"] == 2
    assert stats["commands"]["nav:home"] == 1
    assert stats["total_commands"] == 3


def test_record_stat_action_is_thread_safe(tmp_path, monkeypatch):
    stats_file = tmp_path / "bot_stats.json"
    monkeypatch.setattr(storage, "BOT_STATS_FILE", str(stats_file))

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(
            storage.record_stat_action,
            [" /status "] * 100,
        ))

    stats = storage.load_stats()
    assert stats["commands"]["/status"] == 100
    assert stats["total_commands"] == 100


def test_stats_middleware_records_normalized_command(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        "core.stats_middleware.record_stat_action",
        recorded.append,
    )

    middleware = StatsMiddleware()
    middleware.pre_process_message(
        SimpleNamespace(text="/START@ExampleBot аргумент"),
        {},
    )

    assert recorded == ["/start"]


def test_stats_middleware_ignores_non_commands(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        "core.stats_middleware.record_stat_action",
        recorded.append,
    )

    middleware = StatsMiddleware()
    middleware.pre_process_message(
        SimpleNamespace(text="обычное сообщение"),
        {},
    )
    middleware.pre_process_message(
        SimpleNamespace(text=None),
        {},
    )

    assert recorded == []
