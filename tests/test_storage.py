import json
import os
from pathlib import Path

import pytest

from data import storage

# ==========================================================
# pending_bindings
# ==========================================================


def test_load_pending_bindings_creates_file(tmp_path, monkeypatch):
    test_file = tmp_path / "pending.json"

    monkeypatch.setattr(storage, "PENDING_BINDINGS", str(test_file))

    result = storage.load_pending_bindings()

    assert result == {}
    assert test_file.exists()

    with open(test_file) as f:
        assert json.load(f) == {}


def test_save_pending_bindings(tmp_path, monkeypatch):
    test_file = tmp_path / "pending.json"

    monkeypatch.setattr(storage, "PENDING_BINDINGS", str(test_file))

    data = {"123456": {"username": "ivan", "time": "2026-07-03 19:00"}}

    storage.save_pending_bindings(data)

    with open(test_file) as f:
        assert json.load(f) == data


def test_load_pending_bindings_existing_file(tmp_path, monkeypatch):
    test_file = tmp_path / "pending.json"

    expected = {"999": {"username": "alex"}}

    with open(test_file, "w") as f:
        json.dump(expected, f)

    monkeypatch.setattr(storage, "PENDING_BINDINGS", str(test_file))

    result = storage.load_pending_bindings()

    assert result == expected


# ==========================================================
# client_bindings
# ==========================================================


def test_load_client_bindings_creates_file(tmp_path, monkeypatch):
    test_file = tmp_path / "client_bindings.json"

    monkeypatch.setattr(storage, "CLIENT_BINDINGS", str(test_file))

    result = storage.load_client_bindings()

    assert result == {}
    assert test_file.exists()

    with open(test_file) as f:
        assert json.load(f) == {}


def test_save_client_bindings(tmp_path, monkeypatch):
    test_file = tmp_path / "client_bindings.json"

    monkeypatch.setattr(storage, "CLIENT_BINDINGS", str(test_file))

    data = {"123456": ["ivan", "alex"]}

    storage.save_client_bindings(data)

    with open(test_file) as f:
        assert json.load(f) == data


def test_load_client_bindings_existing_file(tmp_path, monkeypatch):
    test_file = tmp_path / "client_bindings.json"

    expected = {"999999": ["client1", "client2"]}

    with open(test_file, "w") as f:
        json.dump(expected, f)

    monkeypatch.setattr(storage, "CLIENT_BINDINGS", str(test_file))

    result = storage.load_client_bindings()

    assert result == expected


def test_load_json_returns_default_on_invalid_json(tmp_path):
    test_file = tmp_path / "broken.json"
    test_file.write_text("{invalid")

    default = {"fallback": True}

    result = storage._load_json(str(test_file), default)

    assert result == default
    assert result is not default


def test_save_json_logs_cleanup_error(tmp_path, monkeypatch):
    test_file = tmp_path / "data.json"
    temp_file = tmp_path / ".data.json.tmp.test"

    def fail_mkstemp(*args, **kwargs):
        return os.open(temp_file, os.O_CREAT | os.O_WRONLY), str(temp_file)

    def fail_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(storage.tempfile, "mkstemp", fail_mkstemp)
    monkeypatch.setattr(storage.os, "replace", fail_replace)
    monkeypatch.setattr(storage.os, "remove", lambda path: (_ for _ in ()).throw(
        OSError("cleanup failed")
    ))

    with pytest.raises(OSError, match="replace failed"):
        storage._save_json(str(test_file), {"value": 1})

    assert temp_file.exists()


def test_save_json_logs_error_when_replace_fails(tmp_path, monkeypatch):
    test_file = tmp_path / "data.json"

    def fail_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(storage.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        storage._save_json(str(test_file), {"value": 1})

    assert not list(tmp_path.glob("data.json.tmp.*"))


def test_save_json_uses_unique_temp_file_without_pid_suffix(tmp_path, monkeypatch):
    test_file = tmp_path / "data.json"
    seen = []

    real_mkstemp = storage.tempfile.mkstemp

    def tracking_mkstemp(*args, **kwargs):
        fd, path = real_mkstemp(*args, **kwargs)
        seen.append(path)
        return fd, path

    monkeypatch.setattr(storage.tempfile, "mkstemp", tracking_mkstemp)

    storage._save_json(str(test_file), {"value": 1})

    assert test_file.read_text()
    assert len(seen) == 1
    assert Path(seen[0]).parent == tmp_path
    assert Path(seen[0]).name.startswith(".data.json.")
    assert not Path(seen[0]).exists()


def test_save_tickets_delegates_to_save_json(monkeypatch):
    calls = []

    def mock_save(path, data):
        calls.append((path, data))

    monkeypatch.setattr(storage, "_save_json", mock_save)

    data = {"ticket": "value"}
    storage.save_tickets(data)

    assert calls == [(storage.TICKETS_JSON, data)]


def test_save_awg_registry_delegates_to_save_json(monkeypatch):
    calls = []

    def mock_save(path, data):
        calls.append((path, data))

    monkeypatch.setattr(storage, "_save_json", mock_save)

    data = {"client": "value"}
    storage.save_awg_registry(data)

    assert calls == [(storage.AWG_USERS_JSON, data)]


def test_load_stats_replaces_non_dict_with_default(monkeypatch):
    monkeypatch.setattr(storage, "_load_json", lambda path, default: [])

    result = storage.load_stats()

    assert result["commands"] == {}
    assert isinstance(result["start_date"], str)
    storage.load_stats.__globals__["datetime"].strptime(
        result["start_date"],
        "%Y-%m-%d %H:%M:%S",
    )
    assert result["total_commands"] == 0


def test_save_history_limits_to_last_100_entries(monkeypatch):
    calls = []

    monkeypatch.setattr(
        storage,
        "_save_json",
        lambda path, data: calls.append((path, data)),
    )

    history = list(range(150))

    storage.save_history(history)

    assert calls == [(storage.BOT_HISTORY, list(range(50, 150)))]


def test_load_history_passes_custom_path_to_load_json(monkeypatch):
    calls = []

    monkeypatch.setattr(
        storage,
        "_load_json",
        lambda path, default: calls.append((path, default)) or ["event"],
    )

    result = storage.load_history("/tmp/custom-history.json")

    assert result == ["event"]
    assert calls == [("/tmp/custom-history.json", [])]
