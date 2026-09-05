from services.awg import config_generator as cg


def test_awg_get_config_success(monkeypatch, tmp_path):
    """
    Проверка генерации клиентского AWG конфига.
    """

    monkeypatch.setattr(
        cg,
        "load_awg_registry",
        lambda: {
            "test_user": {
                "privkey": "CLIENT_PRIVATE_KEY",
                "ip": "10.66.66.8",
                "pubkey": "CLIENT_PUBLIC_KEY",
            }
        },
    )

    monkeypatch.setattr(cg, "SERVER_IP", "1.2.3.4")

    awg_conf = tmp_path / "awg0.conf"
    awg_conf.write_text(
        "[Interface]\n"
        "PrivateKey = SERVER_PRIVATE_KEY\n"
        "ListenPort = 51820\n"
        "Jc = 8\n"
        "Jmin = 50\n"
        "Jmax = 1000\n"
        "S1 = 117\n"
        "S2 = 74\n"
        "S3 = 63\n"
        "S4 = 82\n"
        "H1 = 127034270-227034269\n"
        "H2 = 860555595-960555594\n"
        "H3 = 1181708860-1281708859\n"
        "H4 = 1849055827-1949055826\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cg,
        "AWG_CONF",
        awg_conf,
    )

    class FakeResult:
        stdout = "SERVER_PUBLIC_KEY\\n"

    monkeypatch.setattr(
        cg.subprocess,
        "run",
        lambda *args, **kwargs: FakeResult(),
    )

    result = cg.awg_get_config("test_user")

    assert result is not None

    assert "[Interface]" in result
    assert "PrivateKey = CLIENT_PRIVATE_KEY" in result
    assert "Address = 10.66.66.8/24" in result

    assert "[Peer]" in result
    assert "PublicKey = SERVER_PUBLIC_KEY" in result

    assert "Endpoint = 1.2.3.4:51820" in result
    assert "AllowedIPs = 0.0.0.0/0, ::/0" in result


def test_awg_get_config_client_not_found(monkeypatch):
    """
    Если клиента нет в реестре — конфиг не создается.
    """

    monkeypatch.setattr(cg, "load_awg_registry", dict)

    result = cg.awg_get_config("unknown")

    assert result is None


def test_awg_get_config_listen_port_not_found(monkeypatch, tmp_path):
    """
    Если ListenPort не найден в AWG_CONF — возвращается None.
    """
    monkeypatch.setattr(
        cg,
        "load_awg_registry",
        lambda: {
            "test_user": {
                "privkey": "CLIENT_PRIVATE_KEY",
                "ip": "10.66.66.8",
                "pubkey": "CLIENT_PUBLIC_KEY",
            }
        },
    )

    # Создаем конфиг без ListenPort
    awg_conf = tmp_path / "awg0.conf"
    awg_conf.write_text(
        "[Interface]\n"
        "PrivateKey = SERVER_PRIVATE_KEY\n"
        "Jc = 8\n"
        "Jmin = 50\n"
        "Jmax = 1000\n"
        "S1 = 117\n"
        "S2 = 74\n"
        "S3 = 63\n"
        "S4 = 82\n"
        "H1 = 127034270-227034269\n"
        "H2 = 860555595-960555594\n"
        "H3 = 1181708860-1281708859\n"
        "H4 = 1849055827-1949055826\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(cg, "AWG_CONF", awg_conf)

    result = cg.awg_get_config("test_user")

    assert result is None


def test_awg_get_config_unexpected_exception(monkeypatch):
    """
    При неожиданном исключении возвращается None.
    """
    # Вызываем исключение при загрузке реестра
    monkeypatch.setattr(
        cg,
        "load_awg_registry",
        lambda: (_ for _ in ()).throw(RuntimeError("unexpected error")),
    )

    result = cg.awg_get_config("test_user")

    assert result is None


def test_get_awg_server_params_missing_required_param(monkeypatch, tmp_path):
    awg_conf = tmp_path / "awg0.conf"
    awg_conf.write_text(
        "[Interface]\n"
        "PrivateKey = SERVER_PRIVATE_KEY\n"
        "Jc = 8\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cg, "AWG_CONF", awg_conf)

    import pytest

    with pytest.raises(ValueError, match="AWG parameters not found"):
        cg.get_awg_server_params()


def test_get_awg_server_params_missing_private_key(monkeypatch, tmp_path):
    awg_conf = tmp_path / "awg0.conf"
    awg_conf.write_text(
        "[Interface]\n"
        "Jc = 8\n"
        "Jmin = 50\n"
        "Jmax = 1000\n"
        "S1 = 117\n"
        "S2 = 74\n"
        "S3 = 63\n"
        "S4 = 82\n"
        "H1 = 127034270-227034269\n"
        "H2 = 860555595-960555594\n"
        "H3 = 1181708860-1281708859\n"
        "H4 = 1849055827-1949055826\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cg, "AWG_CONF", awg_conf)

    import pytest

    with pytest.raises(ValueError, match="PrivateKey not found"):
        cg.get_awg_server_params()


def test_get_awg_server_params_empty_public_key(monkeypatch, tmp_path):
    awg_conf = tmp_path / "awg0.conf"
    awg_conf.write_text(
        "[Interface]\n"
        "PrivateKey = SERVER_PRIVATE_KEY\n"
        "Jc = 8\n"
        "Jmin = 50\n"
        "Jmax = 1000\n"
        "S1 = 117\n"
        "S2 = 74\n"
        "S3 = 63\n"
        "S4 = 82\n"
        "H1 = 127034270-227034269\n"
        "H2 = 860555595-960555594\n"
        "H3 = 1181708860-1281708859\n"
        "H4 = 1849055827-1949055826\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cg, "AWG_CONF", awg_conf)

    class FakeResult:
        stdout = ""

    monkeypatch.setattr(cg.subprocess, "run", lambda *args, **kwargs: FakeResult())

    import pytest

    with pytest.raises(ValueError, match="Failed to derive AWG server public key"):
        cg.get_awg_server_params()


def test_get_awg_server_params_oserror(monkeypatch):
    import builtins

    import pytest

    monkeypatch.setattr(
        builtins,
        "open",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("read failed")),
    )

    with pytest.raises(ValueError, match="Cannot read AWG server config"):
        cg.get_awg_server_params()


def test_awg_get_config_missing_listen_port_raises_to_outer_handler(monkeypatch):
    monkeypatch.setattr(
        cg,
        "load_awg_registry",
        lambda: {
            "test_user": {
                "privkey": "CLIENT_PRIVATE_KEY",
                "ip": "10.66.66.8",
                "pubkey": "CLIENT_PUBLIC_KEY",
            }
        },
    )
    monkeypatch.setattr(
        cg,
        "get_awg_server_params",
        lambda: ("SERVER_PUBLIC_KEY", {"Jc": "8"}),
    )
    monkeypatch.setattr(cg, "get_awg_port", lambda: "N/A")

    result = cg.awg_get_config("test_user")

    assert result is None


def test_get_awg_port_returns_na_on_read_error(monkeypatch):
    import builtins

    monkeypatch.setattr(
        builtins,
        "open",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("read failed")),
    )

    assert cg.get_awg_port() == "N/A"
