import importlib

import pytest

import config.secrets


def test_secrets_requires_bot_token(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "")
    monkeypatch.setenv("ADMIN_CHAT", "123456789")

    with pytest.raises(RuntimeError, match="BOT_TOKEN отсутствует"):
        importlib.reload(config.secrets)


def test_secrets_requires_admin_chat(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("ADMIN_CHAT", "")

    with pytest.raises(RuntimeError, match="ADMIN_CHAT отсутствует"):
        importlib.reload(config.secrets)

    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("ADMIN_CHAT", "123456789")
    importlib.reload(config.secrets)
