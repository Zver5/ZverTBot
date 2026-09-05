def test_awg_add_and_delete_isolated(monkeypatch, tmp_path):
    """
    Проверка полного цикла AWG:
    создание клиента -> запись -> удаление.
    Реальные конфиги не используются.
    """

    fake_conf = tmp_path / "awg0.conf"
    fake_registry = tmp_path / "awg_users.json"

    fake_conf.write_text("[Interface]\nPrivateKey = SERVER_KEY\n\n", encoding="utf-8")

    fake_registry.write_text("{}", encoding="utf-8")

    import services.awg.client_manager as cm
    import services.awg.config_manager as cfg

    # Подмена реального awg0.conf
    monkeypatch.setattr(cfg, "AWG_CONF", fake_conf)

    # Подмена хранилища
    registry = {}

    monkeypatch.setattr(cm, "load_awg_registry", lambda: registry.copy())

    monkeypatch.setattr(cm, "save_awg_registry", lambda data: registry.update(data))

    # Подмена проверки имени
    monkeypatch.setattr(cm, "is_username_unique_awg", lambda username: True)

    # Подмена генерации ключей awg
    class FakeResult:
        def __init__(self, out):
            self.stdout = out

    def fake_run(cmd, *args, **kwargs):
        if cmd == ["awg", "genkey"]:
            return FakeResult("PRIVATE_KEY")
        if cmd == ["awg", "pubkey"]:
            return FakeResult("PUBLIC_KEY")
        return FakeResult("")

    monkeypatch.setattr(cm.subprocess, "run", fake_run)

    # Свободный IP
    monkeypatch.setattr(cm, "find_free_awg_ip", lambda: "10.66.66.8")

    monkeypatch.setattr(cfg.logger, "info", lambda *a, **kw: None)

    # Добавление клиента
    ok, result = cm.awg_add_user("test_user")

    assert ok is True
    assert result == "10.66.66.8"

    assert "test_user" in registry

    conf = fake_conf.read_text(encoding="utf-8")

    assert "# Name: test_user" in conf
    assert "PublicKey = PUBLIC_KEY" in conf
    assert "AllowedIPs = 10.66.66.8/32" in conf


def test_awg_remove_peer_isolated(monkeypatch, tmp_path):
    """
    Проверка удаления Peer только из тестового конфига.
    """

    fake_conf = tmp_path / "awg0.conf"

    fake_conf.write_text(
        """
[Interface]
PrivateKey = SERVER_KEY

# Name: user1
[Peer]
PublicKey = PUBLIC_KEY
AllowedIPs = 10.66.66.8/32
""",
        encoding="utf-8",
    )

    import services.awg.config_manager as cfg

    monkeypatch.setattr(cfg, "AWG_CONF", fake_conf)

    assert cfg.remove_peer_from_config("PUBLIC_KEY") is True

    result = fake_conf.read_text(encoding="utf-8")

    assert "PUBLIC_KEY" not in result
    assert "user1" not in result
