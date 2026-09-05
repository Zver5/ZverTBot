"""Тесты TTLDict."""

import pytest

from utils.ttl_dict import TTLDict


class TestTTLDict:
    def test_value_is_available_before_ttl(self):
        now = [100.0]
        data = TTLDict(ttl=30, clock=lambda: now[0])

        data["key"] = "value"
        now[0] = 129.9

        assert data["key"] == "value"
        assert data.get("key") == "value"
        assert "key" in data

    def test_value_expires_after_ttl(self):
        now = [100.0]
        data = TTLDict(ttl=30, clock=lambda: now[0])

        data["key"] = "value"
        now[0] = 130.0

        assert data.get("key") is None
        assert "key" not in data
        assert len(data) == 0

    def test_expired_value_is_removed_from_mapping(self):
        now = [100.0]
        data = TTLDict(ttl=30, clock=lambda: now[0])

        data["key"] = "value"
        now[0] = 131.0

        assert list(data.keys()) == []

    def test_pop_removes_value_and_timestamp(self):
        now = [100.0]
        data = TTLDict(ttl=30, clock=lambda: now[0])

        data["key"] = "value"

        assert data.pop("key") == "value"
        assert "key" not in data
        assert data.get("key") is None

    def test_clear_removes_values_and_timestamps(self):
        now = [100.0]
        data = TTLDict(ttl=30, clock=lambda: now[0])

        data["one"] = 1
        data["two"] = 2
        data.clear()

        assert len(data) == 0
        assert data.get("one") is None
        assert data.get("two") is None

    def test_setting_existing_key_refreshes_ttl(self):
        now = [100.0]
        data = TTLDict(ttl=30, clock=lambda: now[0])

        data["key"] = "old"
        now[0] = 120.0
        data["key"] = "new"
        now[0] = 149.9

        assert data["key"] == "new"


def test_values_returns_only_unexpired_values():
    now = [100.0]
    data = TTLDict(ttl=30, clock=lambda: now[0])

    data["one"] = 1
    data["two"] = 2

    now[0] = 130.0

    assert list(data.values()) == []


def test_values_returns_unexpired_values():
    now = [100.0]
    data = TTLDict(ttl=30, clock=lambda: now[0])

    data["one"] = 1
    data["two"] = 2

    now[0] = 120.0

    assert list(data.values()) == [1, 2]


def test_delitem_removes_value_and_timestamp():
    now = [100.0]
    data = TTLDict(ttl=30, clock=lambda: now[0])

    data["key"] = "value"
    del data["key"]

    assert "key" not in data
    assert data.get("key") is None
    assert "key" not in data._timestamps


def test_delitem_raises_key_error_for_missing_key():
    now = [100.0]
    data = TTLDict(ttl=30, clock=lambda: now[0])

    with pytest.raises(KeyError):
        del data["missing"]


def test_items_returns_unexpired_items():
    now = [100.0]
    data = TTLDict(ttl=30, clock=lambda: now[0])

    data["one"] = 1
    data["two"] = 2
    now[0] = 120.0

    assert list(data.items()) == [("one", 1), ("two", 2)]
