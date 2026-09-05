"""
Unit-тесты бизнес-логики services.bindings.
"""

from unittest.mock import patch

from services import bindings


class TestPendingBindings:
    def test_get_pending_bindings(self):
        expected = {
            "123": {
                "name": "Test",
                "time": "2026-08-14",
            }
        }

        with patch(
            "data.storage.load_pending_bindings",
            return_value=expected,
        ) as mock_load:
            result = bindings.get_pending_bindings()

        assert result == expected
        mock_load.assert_called_once()

    def test_add_pending_binding(self):
        pending = {
            "123": {
                "name": "Old",
                "time": "old",
            }
        }

        with (
            patch(
                "data.storage.load_pending_bindings",
                return_value=pending,
            ),
            patch("data.storage.save_pending_bindings") as mock_save,
        ):
            bindings.add_pending_binding(
                456,
                "New",
                "2026-08-14 01:00",
            )

        assert pending == {
            "123": {
                "name": "Old",
                "time": "old",
            },
            "456": {
                "name": "New",
                "time": "2026-08-14 01:00",
            },
        }
        mock_save.assert_called_once_with(pending)

    def test_add_pending_binding_updates_existing(self):
        pending = {
            "123": {
                "name": "Old",
                "time": "old",
            }
        }

        with (
            patch(
                "data.storage.load_pending_bindings",
                return_value=pending,
            ),
            patch("data.storage.save_pending_bindings") as mock_save,
        ):
            bindings.add_pending_binding(
                "123",
                "New",
                "new-time",
            )

        assert pending == {
            "123": {
                "name": "New",
                "time": "new-time",
            }
        }
        mock_save.assert_called_once_with(pending)

    def test_remove_pending_binding_missing(self):
        pending = {"123": {"name": "Test"}}

        with (
            patch(
                "data.storage.load_pending_bindings",
                return_value=pending,
            ),
            patch("data.storage.save_pending_bindings") as mock_save,
        ):
            result = bindings.remove_pending_binding(999)

        assert result is False
        assert pending == {"123": {"name": "Test"}}
        mock_save.assert_not_called()

    def test_remove_pending_binding_existing(self):
        pending = {
            "123": {"name": "Test"},
            "456": {"name": "Other"},
        }

        with (
            patch(
                "data.storage.load_pending_bindings",
                return_value=pending,
            ),
            patch("data.storage.save_pending_bindings") as mock_save,
        ):
            result = bindings.remove_pending_binding(123)

        assert result is True
        assert pending == {
            "456": {"name": "Other"},
        }
        mock_save.assert_called_once_with(pending)


class TestNormalizeBindingsList:
    def test_list_is_returned_unchanged(self):
        value = ["client1", "client2"]

        result = bindings.normalize_bindings_list(value)

        assert result is value

    def test_single_value_becomes_list(self):
        assert bindings.normalize_bindings_list("client1") == ["client1"]

    def test_empty_value_becomes_empty_list(self):
        assert bindings.normalize_bindings_list("") == []

    def test_none_becomes_empty_list(self):
        assert bindings.normalize_bindings_list(None) == []


class TestClientBindings:
    def test_get_client_bindings_missing_chat(self):
        with patch(
            "services.bindings.load_client_bindings",
            return_value={},
        ) as mock_load:
            result = bindings.get_client_bindings(123)

        assert result == []
        mock_load.assert_called_once()

    def test_get_client_bindings_list(self):
        with patch(
            "services.bindings.load_client_bindings",
            return_value={
                "123": ["client1", "client2"],
            },
        ):
            result = bindings.get_client_bindings(123)

        assert result == ["client1", "client2"]

    def test_get_client_bindings_legacy_single_value(self):
        with patch(
            "services.bindings.load_client_bindings",
            return_value={
                "123": "client1",
            },
        ):
            result = bindings.get_client_bindings(123)

        assert result == ["client1"]

    def test_get_all_client_bindings(self):
        expected = {
            "123": ["client1"],
            "456": ["client2", "client3"],
        }

        with patch(
            "services.bindings.load_client_bindings",
            return_value=expected,
        ) as mock_load:
            result = bindings.get_all_client_bindings()

        assert result == expected
        mock_load.assert_called_once()


class TestAddClientBinding:
    def test_add_client_binding_added(self):
        bindings_data = {}

        with (
            patch(
                "services.bindings.load_client_bindings",
                return_value=bindings_data,
            ),
            patch("services.bindings.save_client_bindings") as mock_save,
        ):
            result = bindings.add_client_binding(123, "client1")

        assert result == "added"
        assert bindings_data == {
            "123": ["client1"],
        }
        mock_save.assert_called_once_with(bindings_data)

    def test_add_client_binding_added_to_existing_list(self):
        bindings_data = {
            "123": ["client1"],
        }

        with (
            patch(
                "services.bindings.load_client_bindings",
                return_value=bindings_data,
            ),
            patch("services.bindings.save_client_bindings") as mock_save,
        ):
            result = bindings.add_client_binding(123, "client2")

        assert result == "added"
        assert bindings_data == {
            "123": ["client1", "client2"],
        }
        mock_save.assert_called_once_with(bindings_data)

    def test_add_client_binding_legacy_single_value(self):
        bindings_data = {
            "123": "client1",
        }

        with (
            patch(
                "services.bindings.load_client_bindings",
                return_value=bindings_data,
            ),
            patch("services.bindings.save_client_bindings") as mock_save,
        ):
            result = bindings.add_client_binding(123, "client2")

        assert result == "added"
        assert bindings_data == {
            "123": ["client1", "client2"],
        }
        mock_save.assert_called_once_with(bindings_data)

    def test_add_client_binding_duplicate(self):
        bindings_data = {
            "123": ["client1", "client2"],
        }

        with (
            patch(
                "services.bindings.load_client_bindings",
                return_value=bindings_data,
            ),
            patch("services.bindings.save_client_bindings") as mock_save,
        ):
            result = bindings.add_client_binding(123, "client1")

        assert result == "duplicate"
        assert bindings_data == {
            "123": ["client1", "client2"],
        }
        mock_save.assert_not_called()

    def test_add_client_binding_limit(self):
        bindings_data = {
            "123": [
                "client1",
                "client2",
                "client3",
                "client4",
            ],
        }

        with (
            patch(
                "services.bindings.load_client_bindings",
                return_value=bindings_data,
            ),
            patch("services.bindings.save_client_bindings") as mock_save,
        ):
            result = bindings.add_client_binding(123, "client5")

        assert result == "limit"
        assert bindings_data == {
            "123": [
                "client1",
                "client2",
                "client3",
                "client4",
            ],
        }
        mock_save.assert_not_called()


class TestRemoveClientBinding:
    def test_remove_client_binding_missing_chat(self):
        bindings_data = {}

        with (
            patch(
                "services.bindings.load_client_bindings",
                return_value=bindings_data,
            ),
            patch("services.bindings.save_client_bindings") as mock_save,
        ):
            result = bindings.remove_client_binding(123, "client1")

        assert result is False
        mock_save.assert_not_called()

    def test_remove_client_binding_missing_username(self):
        bindings_data = {
            "123": ["client1", "client2"],
        }

        with (
            patch(
                "services.bindings.load_client_bindings",
                return_value=bindings_data,
            ),
            patch("services.bindings.save_client_bindings") as mock_save,
        ):
            result = bindings.remove_client_binding(123, "client3")

        assert result is False
        assert bindings_data == {
            "123": ["client1", "client2"],
        }
        mock_save.assert_not_called()

    def test_remove_client_binding_from_multiple(self):
        bindings_data = {
            "123": ["client1", "client2"],
        }

        with (
            patch(
                "services.bindings.load_client_bindings",
                return_value=bindings_data,
            ),
            patch("services.bindings.save_client_bindings") as mock_save,
        ):
            result = bindings.remove_client_binding(123, "client1")

        assert result is True
        assert bindings_data == {
            "123": ["client2"],
        }
        mock_save.assert_called_once_with(bindings_data)

    def test_remove_client_binding_last_client(self):
        bindings_data = {
            "123": ["client1"],
            "456": ["client2"],
        }

        with (
            patch(
                "services.bindings.load_client_bindings",
                return_value=bindings_data,
            ),
            patch("services.bindings.save_client_bindings") as mock_save,
        ):
            result = bindings.remove_client_binding(123, "client1")

        assert result is True
        assert bindings_data == {
            "456": ["client2"],
        }
        mock_save.assert_called_once_with(bindings_data)

    def test_remove_client_binding_legacy_single_value(self):
        bindings_data = {
            "123": "client1",
        }

        with (
            patch(
                "services.bindings.load_client_bindings",
                return_value=bindings_data,
            ),
            patch("services.bindings.save_client_bindings") as mock_save,
        ):
            result = bindings.remove_client_binding(123, "client1")

        assert result is True
        assert bindings_data == {}
        mock_save.assert_called_once_with(bindings_data)


class TestRemoveClientFromAllBindings:
    def test_remove_client_from_all_bindings(self):
        bindings_data = {
            "123": ["client1", "client2"],
            "456": ["client1"],
            "789": ["client3"],
        }

        with (
            patch(
                "services.bindings.load_client_bindings",
                return_value=bindings_data,
            ),
            patch("services.bindings.save_client_bindings") as mock_save,
        ):
            result = bindings.remove_client_from_all_bindings("client1")

        assert result == 2
        assert bindings_data == {
            "123": ["client2"],
            "789": ["client3"],
        }
        mock_save.assert_called_once_with(bindings_data)

    def test_remove_client_from_all_bindings_missing(self):
        bindings_data = {
            "123": ["client1"],
        }

        with (
            patch(
                "services.bindings.load_client_bindings",
                return_value=bindings_data,
            ),
            patch("services.bindings.save_client_bindings") as mock_save,
        ):
            result = bindings.remove_client_from_all_bindings("missing")

        assert result == 0
        assert bindings_data == {
            "123": ["client1"],
        }
        mock_save.assert_not_called()
