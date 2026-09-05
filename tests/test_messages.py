"""
Unit-тесты для модуля ui/messages.py
Тестирует функцию build_client_card() — форматирование карточек клиентов.
"""

from ui.messages import build_client_card


class TestBuildClientCard:
    """Тесты функции build_client_card"""

    def test_returns_string(self):
        """Тест: функция возвращает строку"""
        result = build_client_card("TestUser", "vless")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_vless_contains_protocol(self):
        """Тест: VLESS карточка содержит название протокола"""
        result = build_client_card("TestUser", "vless")
        assert "VLESS" in result
        assert "Reality" in result

    def test_vless_contains_sni(self):
        """Тест: VLESS карточка содержит оба SNI (MTS и Beeline)"""
        result = build_client_card("TestUser", "vless")
        assert "itunes.apple.com" in result
        assert "speed.cloudflare.com" in result
        assert "443" in result
        assert "2096" in result

    def test_vless_contains_username(self):
        """Тест: VLESS карточка содержит имя клиента"""
        result = build_client_card("MyClient_01", "vless")
        assert "MyClient_01" in result

    def test_awg_contains_protocol(self):
        """Тест: AWG карточка содержит название протокола"""
        result = build_client_card("TestUser", "awg")
        assert "AmneziaWG" in result

    def test_awg_contains_username(self):
        """Тест: AWG карточка содержит имя клиента"""
        result = build_client_card("MyAWGClient", "awg")
        assert "MyAWGClient" in result

    def test_awg_missing_client_shows_na(self):
        """Тест: для несуществующего AWG клиента IP = N/A"""
        result = build_client_card("NonExistentClient_XYZ", "awg")
        assert "N/A" in result


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])


def test_awg_card_uses_na_when_config_unreadable(monkeypatch):
    import ui.messages as messages

    def fail_open(*args, **kwargs):
        raise OSError("config unavailable")

    monkeypatch.setattr("builtins.open", fail_open)
    monkeypatch.setattr(
        messages,
        "load_awg_registry",
        lambda: {"TestUser": {"ip": "10.0.0.2"}},
    )

    result = messages.build_client_card("TestUser", "awg")

    assert "AmneziaWG" in result
    assert ":N/A" in result
    assert "10.0.0.2" in result


def test_vless_card_returns_fallback_on_exception(monkeypatch):
    import ui.messages as messages

    def fail_load():
        raise RuntimeError("broken xray config")

    monkeypatch.setattr(messages, "xray_get_sni_by_port", fail_load)

    result = messages.build_client_card("TestUser", "vless")

    assert result == (
        "✅ *Клиент успешно создан*\n"
        "⚡ *Протокол:* VLESS (Reality)\n"
        "👤 *Имя:* `TestUser`\n"
    )
