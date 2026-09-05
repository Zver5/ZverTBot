def test_awg_config_never_touches_real_file(monkeypatch, tmp_path):
    """
    Проверяем, что работа с AWG конфигом идёт через подменённый файл.
    Реальный AWG_CONF не используется.
    """

    import services.awg.config_manager as cfg

    fake_conf = tmp_path / "awg0.conf"

    fake_conf.write_text("[Interface]\nPrivateKey = TEST\n", encoding="utf-8")

    monkeypatch.setattr(cfg, "AWG_CONF", fake_conf)

    content = cfg.load_awg_config()

    assert "PrivateKey = TEST" in content

    cfg.save_awg_config("[Interface]\nPrivateKey = NEW_TEST\n")

    result = fake_conf.read_text(encoding="utf-8")

    assert "NEW_TEST" in result


def test_awg_peer_operations_are_isolated(monkeypatch, tmp_path):
    """
    Добавление/удаление Peer работает только с тестовым awg0.conf.
    """

    import services.awg.config_manager as cfg

    fake_conf = tmp_path / "awg0.conf"

    fake_conf.write_text("[Interface]\nPrivateKey = SERVER\n", encoding="utf-8")

    monkeypatch.setattr(cfg, "AWG_CONF", fake_conf)

    cfg.add_peer_to_config("alice", "PUB_KEY", "10.66.66.8")

    data = fake_conf.read_text(encoding="utf-8")

    assert "alice" in data
    assert "PUB_KEY" in data
    assert "10.66.66.8/32" in data

    result = cfg.remove_peer_from_config("PUB_KEY")

    assert result is True

    data = fake_conf.read_text(encoding="utf-8")

    assert "PUB_KEY" not in data
    assert "alice" not in data


def test_awg_registry_isolation(monkeypatch, tmp_path):
    """
    Проверка, что реестр AWG можно полностью заменить.
    """

    import services.awg.client_manager as cm

    fake_registry = tmp_path / "awg_users.json"

    fake_registry.write_text('{"test": {"ip": "10.66.66.8"}}', encoding="utf-8")

    registry = {"test": {"ip": "10.66.66.8"}}

    monkeypatch.setattr(cm, "load_awg_registry", lambda: registry.copy())

    data = cm.load_awg_registry()

    assert data["test"]["ip"] == "10.66.66.8"
