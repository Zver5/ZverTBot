from utils.validators import (
    validate_chat_id,
    validate_ip,
    validate_pid,
    validate_username,
)


def test_validate_username_ok():
    assert validate_username("test_user123") is True
    assert validate_username("abc-XYZ_9") is True


def test_validate_username_fail():
    assert validate_username("") is False
    assert validate_username("bad user") is False
    assert validate_username("user!") is False


def test_validate_ip_ok():
    assert validate_ip("8.8.8.8") is True
    assert validate_ip("192.168.0.1") is True


def test_validate_ip_fail():
    assert validate_ip("999.999.999.999") is False
    assert validate_ip("abc.def.ghi.jkl") is False
    assert validate_ip("") is False


def test_validate_pid():
    assert validate_pid(1234) is True
    assert validate_pid("1234") is True
    assert validate_pid("12ab") is False


def test_validate_chat_id():
    assert validate_chat_id(123456) is True
    assert validate_chat_id("999999") is True
    assert validate_chat_id("abc") is False


def test_is_username_unique_vless_returns_true_when_name_is_free(tmp_path):
    import json

    from utils.validators import is_username_unique_vless

    config = {
        "inbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {"email": "Alice"},
                        {"email": "Bob"},
                    ]
                },
            }
        ]
    }

    config_path = tmp_path / "xray.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    assert is_username_unique_vless("Charlie", str(config_path)) is True


def test_is_username_unique_vless_returns_false_for_case_insensitive_match(
    tmp_path,
):
    import json

    from utils.validators import is_username_unique_vless

    config = {
        "inbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {"email": "Alice"},
                    ]
                },
            }
        ]
    }

    config_path = tmp_path / "xray.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    assert is_username_unique_vless("ALICE", str(config_path)) is False


def test_is_username_unique_vless_ignores_non_vless_inbounds(tmp_path):
    import json

    from utils.validators import is_username_unique_vless

    config = {
        "inbounds": [
            {
                "protocol": "vmess",
                "settings": {
                    "clients": [
                        {"email": "Alice"},
                    ]
                },
            },
            {
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {"email": "Bob"},
                    ]
                },
            },
        ]
    }

    config_path = tmp_path / "xray.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    assert is_username_unique_vless("Alice", str(config_path)) is True


def test_is_username_unique_vless_returns_false_on_invalid_config(tmp_path):
    from utils.validators import is_username_unique_vless

    config_path = tmp_path / "xray.json"
    config_path.write_text("{invalid json", encoding="utf-8")

    assert is_username_unique_vless("Alice", str(config_path)) is False


def test_is_username_unique_vless_returns_false_when_config_missing(tmp_path):
    from utils.validators import is_username_unique_vless

    config_path = tmp_path / "missing.json"

    assert is_username_unique_vless("Alice", str(config_path)) is False


def test_is_username_unique_awg_returns_true_when_registry_missing(tmp_path):
    from utils.validators import is_username_unique_awg

    registry_path = tmp_path / "users.json"

    assert is_username_unique_awg("Alice", str(registry_path)) is True


def test_is_username_unique_awg_returns_true_when_name_is_free(tmp_path):
    import json

    from utils.validators import is_username_unique_awg

    registry_path = tmp_path / "users.json"
    registry_path.write_text(
        json.dumps({"Bob": "value", "Charlie": "value"}),
        encoding="utf-8",
    )

    assert is_username_unique_awg("Alice", str(registry_path)) is True


def test_is_username_unique_awg_returns_false_for_case_insensitive_match(tmp_path):
    import json

    from utils.validators import is_username_unique_awg

    registry_path = tmp_path / "users.json"
    registry_path.write_text(
        json.dumps({"Alice": "value"}),
        encoding="utf-8",
    )

    assert is_username_unique_awg("ALICE", str(registry_path)) is False


def test_is_username_unique_awg_returns_false_on_invalid_registry(tmp_path):
    from utils.validators import is_username_unique_awg

    registry_path = tmp_path / "users.json"
    registry_path.write_text("{invalid json", encoding="utf-8")

    assert is_username_unique_awg("Alice", str(registry_path)) is False
