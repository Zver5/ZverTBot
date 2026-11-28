import json

import utils.formatters as formatters
from config import BOT_VERSION
from utils.formatters import get_help_text


def _set_state(tmp_path, monkeypatch, state):
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(formatters, "CHEBURCHECK_STATE_FILE", state_file)
    monkeypatch.setattr(formatters, "SERVER_IP", "1.2.3.4")


def test_get_help_text():
    text = get_help_text()
    assert isinstance(text, str)
    assert "Управление сервером VPS" in text
    assert "ZverTBot" in text
    assert f"v{BOT_VERSION}" in text
    assert "github.com" not in text
    assert "VPS:" in text
    assert "HASS:" in text
    assert "cheburcheck.ru" not in text
    assert "Выберите действие" in text


def test_cheburcheck_hidden_when_available_and_not_blocked(tmp_path, monkeypatch):
    _set_state(
        tmp_path,
        monkeypatch,
        {
            "target": "1.2.3.4",
            "api_status": "available",
            "blocked": False,
        },
    )
    text = get_help_text()
    assert "Возможно, IP заблокирован" not in text
    assert "cheburcheck.ru" not in text


def test_cheburcheck_warning_when_api_unavailable(tmp_path, monkeypatch):
    _set_state(
        tmp_path,
        monkeypatch,
        {
            "target": "1.2.3.4",
            "api_status": "unavailable",
            "blocked": False,
        },
    )
    text = get_help_text()
    assert "⚠️ Возможно, IP заблокирован" in text
    assert "https://cheburcheck.ru/" in text


def test_cheburcheck_warning_when_ip_blocked(tmp_path, monkeypatch):
    _set_state(
        tmp_path,
        monkeypatch,
        {
            "target": "1.2.3.4",
            "api_status": "available",
            "blocked": True,
        },
    )
    text = get_help_text()
    assert "⚠️ Возможно, IP заблокирован" in text
    assert "https://cheburcheck.ru/" in text


def test_cheburcheck_ignores_other_ip(tmp_path, monkeypatch):
    _set_state(
        tmp_path,
        monkeypatch,
        {
            "target": "5.6.7.8",
            "api_status": "unavailable",
            "blocked": True,
        },
    )
    text = get_help_text()
    assert "Возможно, IP заблокирован" not in text


def test_cheburcheck_without_state(tmp_path, monkeypatch):
    monkeypatch.setattr(formatters, "CHEBURCHECK_STATE_FILE", tmp_path / "missing.json")
    text = get_help_text()
    assert "Возможно, IP заблокирован" not in text
