import json

import pytest

from services import ip_tokens


def test_load_returns_empty_dict_when_file_does_not_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(ip_tokens, "TOKENS_FILE", tmp_path / "tokens.json")

    assert ip_tokens._load() == {}


def test_load_returns_data_from_valid_json(tmp_path, monkeypatch):
    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text('{"token123": "12345"}')
    monkeypatch.setattr(ip_tokens, "TOKENS_FILE", tokens_file)

    assert ip_tokens._load() == {"token123": "12345"}


def test_load_raises_on_invalid_json(tmp_path, monkeypatch):
    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text("{invalid json")
    monkeypatch.setattr(ip_tokens, "TOKENS_FILE", tokens_file)

    with pytest.raises(json.JSONDecodeError):
        ip_tokens._load()


def test_load_invalid_json_logs_standardized_error(tmp_path, monkeypatch):
    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text("{invalid json")
    monkeypatch.setattr(ip_tokens, "TOKENS_FILE", tokens_file)

    logger_calls = []

    original_error = ip_tokens.logger.error
    monkeypatch.setattr(
        ip_tokens.logger,
        "error",
        lambda *args: logger_calls.append(args),
    )

    try:
        with pytest.raises(json.JSONDecodeError):
            ip_tokens._load()
    finally:
        monkeypatch.setattr(ip_tokens.logger, "error", original_error)

    assert len(logger_calls) == 1
    assert logger_calls[0][0] == "ip_tokens.load.failed | error=%s"
    assert isinstance(logger_calls[0][1], json.JSONDecodeError)



def test_save_creates_parent_and_writes_json(tmp_path, monkeypatch):
    tokens_file = tmp_path / "nested" / "tokens.json"
    monkeypatch.setattr(ip_tokens, "TOKENS_FILE", tokens_file)

    ip_tokens._save({"token123": "12345"})

    assert json.loads(tokens_file.read_text()) == {"token123": "12345"}


def test_create_ip_token_saves_token_for_chat_id(tmp_path, monkeypatch):
    tokens_file = tmp_path / "tokens.json"
    monkeypatch.setattr(ip_tokens, "TOKENS_FILE", tokens_file)
    monkeypatch.setattr(
        ip_tokens.uuid, "uuid4", lambda: type("UUID", (), {"hex": "abcdef1234567890"})()
    )

    token = ip_tokens.create_ip_token(12345)

    assert token == "abcdef12"
    assert json.loads(tokens_file.read_text()) == {"abcdef12": "12345"}


def test_get_chat_id_by_token_returns_matching_chat_id(tmp_path, monkeypatch):
    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text('{"token123": "12345"}')
    monkeypatch.setattr(ip_tokens, "TOKENS_FILE", tokens_file)

    assert ip_tokens.get_chat_id_by_token("token123") == "12345"


def test_get_chat_id_by_token_returns_none_for_unknown_token(tmp_path, monkeypatch):
    tokens_file = tmp_path / "tokens.json"
    tokens_file.write_text('{"token123": "12345"}')
    monkeypatch.setattr(ip_tokens, "TOKENS_FILE", tokens_file)

    assert ip_tokens.get_chat_id_by_token("unknown") is None
