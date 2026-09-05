import json
from unittest.mock import Mock, patch

from data import traffic


def test_load_usage_missing_file(tmp_path):
    test_file = tmp_path / "usage.json"

    result = traffic.load_usage(str(test_file))

    assert result == {}


def test_save_and_load_usage(tmp_path):
    test_file = tmp_path / "usage.json"

    expected = {"clients": {"ivan": {"uplink": 100, "downlink": 200, "total": 300}}}

    traffic.save_usage(expected, str(test_file))

    loaded = traffic.load_usage(str(test_file))

    assert loaded == expected


def test_get_client_traffic_exists(tmp_path):
    test_file = tmp_path / "usage.json"

    data = {"clients": {"ivan": {"uplink": 10, "downlink": 20, "total": 30}}}

    with open(test_file, "w") as f:
        json.dump(data, f)

    result = traffic.get_client_traffic("ivan", str(test_file))

    assert result == {"uplink": 10, "downlink": 20, "total": 30}


def test_get_client_traffic_missing_client(tmp_path):
    test_file = tmp_path / "usage.json"

    with open(test_file, "w") as f:
        json.dump({"clients": {}}, f)

    result = traffic.get_client_traffic("nobody", str(test_file))

    assert result == {"uplink": 0, "downlink": 0, "total": 0}


def test_rename_client_success(tmp_path):
    test_file = tmp_path / "usage.json"

    data = {"clients": {"old": {"uplink": 1, "downlink": 2, "total": 3}}}

    with open(test_file, "w") as f:
        json.dump(data, f)

    assert traffic.rename_client_in_usage("old", "new", str(test_file)) is True

    loaded = traffic.load_usage(str(test_file))

    assert "old" not in loaded["clients"]
    assert "new" in loaded["clients"]
    assert loaded["clients"]["new"]["total"] == 3


def test_rename_client_missing(tmp_path):
    test_file = tmp_path / "usage.json"

    with open(test_file, "w") as f:
        json.dump({"clients": {}}, f)

    assert traffic.rename_client_in_usage("old", "new", str(test_file)) is False


def test_remove_client_from_usage(tmp_path):
    test_file = tmp_path / "usage.json"

    data = {
        "clients": {
            "client1": {
                "uplink": 100,
                "downlink": 200,
                "total": 300,
            },
            "client2": {
                "uplink": 400,
                "downlink": 500,
                "total": 900,
            },
        }
    }

    with open(test_file, "w") as f:
        json.dump(data, f)

    assert traffic.remove_client_from_usage("client1", str(test_file)) is True

    loaded = traffic.load_usage(str(test_file))

    assert "client1" not in loaded["clients"]
    assert "client2" in loaded["clients"]
    assert loaded["clients"]["client2"]["total"] == 900


def test_remove_client_from_usage_missing(tmp_path):
    test_file = tmp_path / "usage.json"

    with open(test_file, "w") as f:
        json.dump({"clients": {"client1": {}}}, f)

    assert traffic.remove_client_from_usage("missing", str(test_file)) is False

    loaded = traffic.load_usage(str(test_file))

    assert "client1" in loaded["clients"]


def test_load_usage_invalid_json(tmp_path):
    test_file = tmp_path / "usage.json"
    test_file.write_text("{invalid json")

    result = traffic.load_usage(str(test_file))

    assert result == {}


def test_save_usage_error(tmp_path):
    bad_path = tmp_path / "dir_as_file"
    bad_path.mkdir()

    traffic.save_usage({"test": "data"}, str(bad_path))


def test_get_client_traffic_invalid_json(tmp_path):
    test_file = tmp_path / "usage.json"
    test_file.write_text("not a json")

    result = traffic.get_client_traffic("ivan", str(test_file))

    assert result == {"uplink": 0, "downlink": 0, "total": 0}


def test_get_client_traffic_not_dict(tmp_path):
    test_file = tmp_path / "usage.json"
    test_file.write_text("[]")

    result = traffic.get_client_traffic("ivan", str(test_file))

    assert result == {"uplink": 0, "downlink": 0, "total": 0}


def test_remove_client_from_usage_invalid_json(tmp_path):
    test_file = tmp_path / "usage.json"
    test_file.write_text("{broken")

    result = traffic.remove_client_from_usage("client1", str(test_file))

    assert result is False


def test_remove_client_from_usage_not_dict(tmp_path):
    test_file = tmp_path / "usage.json"
    test_file.write_text("[]")

    result = traffic.remove_client_from_usage("client1", str(test_file))

    assert result is False


def test_rename_client_in_usage_invalid_json(tmp_path):
    test_file = tmp_path / "usage.json"
    test_file.write_text("{broken")

    result = traffic.rename_client_in_usage("old", "new", str(test_file))

    assert result is False


def test_rename_client_in_usage_not_dict(tmp_path):
    test_file = tmp_path / "usage.json"
    test_file.write_text("[]")

    result = traffic.rename_client_in_usage("old", "new", str(test_file))

    assert result is False

def test_load_usage_logs_standardized_error(tmp_path):
    test_file = tmp_path / "usage.json"
    test_file.write_text("{invalid json")

    with patch("data.traffic.logger.error") as mock_error:
        assert traffic.load_usage(str(test_file)) == {}

    mock_error.assert_called_once()
    args = mock_error.call_args.args
    assert args[0] == "traffic.load.failed | error=%s"
    assert isinstance(args[1], json.JSONDecodeError)


def test_save_usage_logs_standardized_error(tmp_path):
    bad_path = tmp_path / "dir_as_file"
    bad_path.mkdir()

    with patch("data.traffic.logger.error") as mock_error:
        traffic.save_usage({"test": "data"}, str(bad_path))

    mock_error.assert_called_once()
    args = mock_error.call_args.args
    assert args[0] == "traffic.save.failed | error=%s"
    assert isinstance(args[1], Exception)


def test_get_client_traffic_logs_missing_client():
    with patch("data.traffic.load_usage", return_value={"clients": {}}):
        with patch("data.traffic.logger.warning") as mock_warning:
            result = traffic.get_client_traffic("nobody")

    assert result == {"uplink": 0, "downlink": 0, "total": 0}
    mock_warning.assert_called_once_with(
        "traffic.client.not_found | username=%s",
        "nobody",
    )


def test_get_client_traffic_logs_standardized_error(monkeypatch):
    error = RuntimeError("traffic read failed")
    monkeypatch.setattr(
        traffic,
        "load_usage",
        Mock(side_effect=error),
    )

    with patch("data.traffic.logger.error") as mock_error:
        result = traffic.get_client_traffic("ivan")

    assert result == {"uplink": 0, "downlink": 0, "total": 0}
    mock_error.assert_called_once_with(
        "traffic.client.get_failed | username=%s | error=%s",
        "ivan",
        error,
    )


def test_remove_client_from_usage_logs_standardized_error(monkeypatch, tmp_path):
    error = RuntimeError("remove failed")
    monkeypatch.setattr(
        traffic,
        "load_usage",
        Mock(side_effect=error),
    )

    with patch("data.traffic.logger.error") as mock_error:
        result = traffic.remove_client_from_usage(
            "client1",
            str(tmp_path / "usage.json"),
        )

    assert result is False
    mock_error.assert_called_once_with(
        "traffic.client.remove_failed | username=%s | error=%s",
        "client1",
        error,
    )


def test_rename_client_in_usage_logs_standardized_error(monkeypatch, tmp_path):
    error = RuntimeError("rename failed")
    monkeypatch.setattr(
        traffic,
        "load_usage",
        Mock(side_effect=error),
    )

    with patch("data.traffic.logger.error") as mock_error:
        result = traffic.rename_client_in_usage(
            "old",
            "new",
            str(tmp_path / "usage.json"),
        )

    assert result is False
    mock_error.assert_called_once_with(
        "traffic.client.rename_failed | old_name=%s | new_name=%s | error=%s",
        "old",
        "new",
        error,
    )
