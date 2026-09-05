from unittest.mock import patch

import services.xray.config_manager as cm


def sample_config():
    return {
        "inbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {
                            "id": "uuid-1",
                            "email": "user1",
                            "flow": "xtls-rprx-vision",
                            "level": 0,
                        }
                    ]
                },
            },
            {
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {
                            "id": "uuid-1",
                            "email": "user1",
                            "flow": "xtls-rprx-vision",
                            "level": 0,
                        }
                    ]
                },
            },
            {"protocol": "vmess", "settings": {}},
        ]
    }


def test_get_vless_inbounds():
    config = sample_config()

    result = cm.get_vless_inbounds(config)

    assert len(result) == 2
    assert all(x["protocol"] == "vless" for x in result)


def test_get_all_vless_clients():
    config = sample_config()

    result = cm.get_all_vless_clients(config)

    assert result == ["user1"]


def test_add_client_to_all_inbounds():
    config = sample_config()

    count = cm.add_client_to_all_inbounds(config, "user2", "uuid-2")

    assert count == 2

    for inbound in cm.get_vless_inbounds(config):
        emails = [x["email"] for x in inbound["settings"]["clients"]]
        assert "user2" in emails


def test_remove_client_from_all_inbounds():
    config = sample_config()

    removed = cm.remove_client_from_all_inbounds(config, "user1")

    assert removed == 2

    for inbound in cm.get_vless_inbounds(config):
        assert inbound["settings"]["clients"] == []


def test_rename_client_in_config():
    config = sample_config()

    result = cm.rename_client_in_config(config, "user1", "new_user")

    assert result is True

    assert all(
        client["email"] != "user1"
        for inbound in cm.get_vless_inbounds(config)
        for client in inbound.get("settings", {}).get("clients", [])
    )
    assert any(
        client["email"] == "new_user"
        for inbound in cm.get_vless_inbounds(config)
        for client in inbound.get("settings", {}).get("clients", [])
    )


def test_rename_missing_client():
    config = sample_config()

    result = cm.rename_client_in_config(config, "none", "new")

    assert result is False


def test_save_and_load_xray_config(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"

    monkeypatch.setattr(cm, "XRAY_CONF", config_file)

    data = sample_config()

    monkeypatch.setattr(
        cm,
        "validate_xray_config",
        lambda config: True,
    )

    cm.save_xray_config(data)

    loaded = cm.load_xray_config()

    assert loaded == data


def test_validate_xray_config_invalid_empty():
    assert cm.validate_xray_config_structure({}) is False


def test_validate_xray_config_invalid_inbounds_type():
    config = {"inbounds": {}}

    assert cm.validate_xray_config_structure(config) is False


def test_validate_xray_config_valid_minimal():
    config = {"inbounds": [{"protocol": "vless", "settings": {"clients": []}}]}

    assert cm.validate_xray_config_structure(config) is True


def test_validate_xray_config_rejects_empty_client():
    config = {"inbounds": [{"protocol": "vless", "settings": {"clients": [{}]}}]}

    assert cm.validate_xray_config_structure(config) is False


def test_validate_xray_config_rejects_client_without_email():
    config = {
        "inbounds": [{"protocol": "vless", "settings": {"clients": [{"id": "uuid-1"}]}}]
    }

    assert cm.validate_xray_config_structure(config) is False


def test_validate_xray_config_rejects_client_without_id():
    config = {
        "inbounds": [
            {"protocol": "vless", "settings": {"clients": [{"email": "user1"}]}}
        ]
    }

    assert cm.validate_xray_config_structure(config) is False


def test_load_xray_config_file_not_found(tmp_path, monkeypatch):
    config_file = tmp_path / "missing.json"
    monkeypatch.setattr(cm, "XRAY_CONF", config_file)

    try:
        cm.load_xray_config()
        assert False, "Expected FileNotFoundError"
    except FileNotFoundError as exc:
        assert "Xray config не найден" in str(exc)


def test_load_xray_config_invalid_json(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text("{invalid json")
    monkeypatch.setattr(cm, "XRAY_CONF", config_file)

    try:
        cm.load_xray_config()
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Поврежден Xray config" in str(exc)


def test_load_xray_config_requires_json_object(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text("[]")
    monkeypatch.setattr(cm, "XRAY_CONF", config_file)

    try:
        cm.load_xray_config()
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Xray config должен быть JSON объектом" in str(exc)


def test_validate_xray_config_rejects_non_dict():
    assert cm.validate_xray_config_structure([]) is False


def test_validate_xray_config_rejects_non_dict_settings():
    config = {
        "inbounds": [
            {
                "protocol": "vless",
                "settings": [],
            }
        ]
    }

    assert cm.validate_xray_config_structure(config) is False


def test_validate_xray_config_rejects_non_list_clients():
    config = {
        "inbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "clients": {},
                },
            }
        ]
    }

    assert cm.validate_xray_config_structure(config) is False


def test_validate_xray_config_rejects_non_dict_client():
    config = {
        "inbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "clients": ["invalid"],
                },
            }
        ]
    }

    assert cm.validate_xray_config_structure(config) is False


def test_save_xray_config_rejects_invalid_structure():
    try:
        cm.save_xray_config({})
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Некорректная структура Xray config" in str(exc)


def test_add_client_skips_inbound_without_clients():
    config = {
        "inbounds": [
            {
                "protocol": "vless",
                "settings": {},
            },
            {
                "protocol": "vless",
                "settings": {
                    "clients": [],
                },
            },
        ]
    }

    count = cm.add_client_to_all_inbounds(config, "user1", "uuid-1")

    assert count == 1
    assert config["inbounds"][1]["settings"]["clients"][0]["email"] == "user1"


def test_remove_client_skips_inbound_without_clients():
    config = {
        "inbounds": [
            {
                "protocol": "vless",
                "settings": {},
            },
            {
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {
                            "id": "uuid-1",
                            "email": "user1",
                        }
                    ]
                },
            },
        ]
    }

    removed = cm.remove_client_from_all_inbounds(config, "user1")

    assert removed == 1
    assert config["inbounds"][1]["settings"]["clients"] == []


def test_rename_client_skips_inbound_without_clients():
    config = {
        "inbounds": [
            {
                "protocol": "vless",
                "settings": {},
            },
            {
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {
                            "id": "uuid-1",
                            "email": "user1",
                        }
                    ]
                },
            },
        ]
    }

    result = cm.rename_client_in_config(
        config,
        "user1",
        "renamed",
    )

    assert result is True
    assert config["inbounds"][1]["settings"]["clients"][0]["email"] == "renamed"


def test_validate_xray_config_rejects_invalid_structure(monkeypatch):
    config = {}
    monkeypatch.setattr(
        cm,
        "validate_xray_config_structure",
        lambda value: False,
    )

    assert cm.validate_xray_config(config) is False


def test_save_xray_config_rejects_xray_validation_failure(monkeypatch):
    config = sample_config()
    monkeypatch.setattr(
        cm,
        "validate_xray_config",
        lambda value: False,
    )

    try:
        cm.save_xray_config(config)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert str(exc) == "Конфиг Xray не прошёл проверку"


def test_validate_xray_config_success(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(cm, "XRAY_CONF", config_file)

    result = type("Result", (), {"returncode": 0, "stderr": ""})()

    with patch(
        "services.xray.config_manager.subprocess.run",
        return_value=result,
    ) as mock_run:
        assert cm.validate_xray_config(sample_config()) is True

    args = mock_run.call_args.args[0]
    assert args[:4] == ["xray", "run", "-test", "-config"]
    assert not __import__("os").path.exists(args[4])


def test_validate_xray_config_xray_rejects(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(cm, "XRAY_CONF", config_file)

    result = type(
        "Result",
        (),
        {"returncode": 1, "stderr": "invalid config"},
    )()

    with patch("services.xray.config_manager.subprocess.run", return_value=result):
        assert cm.validate_xray_config(sample_config()) is False


def test_validate_xray_config_subprocess_exception(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(cm, "XRAY_CONF", config_file)

    with patch(
        "services.xray.config_manager.subprocess.run",
        side_effect=RuntimeError("xray failed"),
    ):
        assert cm.validate_xray_config(sample_config()) is False


def test_validate_xray_config_cleanup_error(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(cm, "XRAY_CONF", config_file)

    result = type("Result", (), {"returncode": 0, "stderr": ""})()

    with (
        patch("services.xray.config_manager.subprocess.run", return_value=result),
        patch(
            "services.xray.config_manager.Path.unlink",
            side_effect=OSError("cleanup failed"),
        ),
        patch("services.xray.config_manager.logger.error") as mock_error,
    ):
        assert cm.validate_xray_config(sample_config()) is True

    assert any(
        call.args[0] == "xray.config.cleanup_failed | error=%s"
        and str(call.args[1]) == "cleanup failed"
        for call in mock_error.call_args_list
    )
