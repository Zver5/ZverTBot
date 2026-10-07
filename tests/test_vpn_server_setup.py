
from services import vpn_server_setup
from services.xray import config_manager as xray_config_manager


def test_setup_result_is_immutable():
    result = vpn_server_setup.SetupResult(
        protocol="xray",
        created=True,
        message="created",
    )

    assert result.protocol == "xray"
    assert result.created is True
    assert result.message == "created"


def test_build_xray_config_generates_reality_config(monkeypatch):
    def fake_run_xray(*args):
        if args == ("uuid",):
            return "11111111-2222-3333-4444-555555555555"

        if args == ("x25519",):
            return (
                "PrivateKey: test-private-key\n"
                "Password (PublicKey): test-public-key\n"
                "Hash32: test-hash\n"
            )

        raise AssertionError(args)

    monkeypatch.setattr(vpn_server_setup, "_run_xray", fake_run_xray)

    config = vpn_server_setup._build_xray_config()

    inbound = config["inbounds"][0]
    reality = inbound["streamSettings"]["realitySettings"]
    client = inbound["settings"]["clients"][0]

    assert inbound["protocol"] == "vless"
    assert inbound["port"] == 2096
    assert client["id"] == "11111111-2222-3333-4444-555555555555"
    assert client["flow"] == "xtls-rprx-vision"
    assert reality["dest"] == "speed.cloudflare.com:443"
    assert reality["serverNames"] == ["speed.cloudflare.com"]
    assert reality["privateKey"] == "test-private-key"
    assert len(reality["shortIds"]) == 1
    assert len(reality["shortIds"][0]) == 16
    int(reality["shortIds"][0], 16)
    assert "serverName" not in reality


def test_generate_reality_private_key_parses_current_xray_output(monkeypatch):
    monkeypatch.setattr(
        vpn_server_setup,
        "_run_xray",
        lambda *args: (
            "PrivateKey: generated-private-key\n"
            "Password (PublicKey): generated-public-key\n"
            "Hash32: generated-hash\n"
        ),
    )

    assert (
        vpn_server_setup._generate_reality_private_key()
        == "generated-private-key"
    )


def test_setup_xray_server_replaces_broken_config_with_backup(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"inbounds": [{"protocol": "vless"}]}',
        encoding="utf-8",
    )

    monkeypatch.setattr(vpn_server_setup, "XRAY_CONF", config_path)
    monkeypatch.setattr(xray_config_manager, "XRAY_CONF", config_path)
    monkeypatch.setattr(
        vpn_server_setup,
        "load_xray_config",
        lambda: {"inbounds": [{"protocol": "vless"}]},
    )
    monkeypatch.setattr(
        vpn_server_setup,
        "get_xray_readiness",
        lambda config: (False, ["тестовый нерабочий конфиг"]),
    )

    result = vpn_server_setup.setup_xray_server()

    assert result.created is True
    assert "Backup" in result.message
    assert list(tmp_path.glob("config.json.bak-*"))


def test_setup_xray_server_keeps_existing_config_when_generation_fails(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "config.json"
    original = '{"broken": true}'
    config_path.write_text(original, encoding="utf-8")

    monkeypatch.setattr(vpn_server_setup, "XRAY_CONF", config_path)
    monkeypatch.setattr(xray_config_manager, "XRAY_CONF", config_path)
    monkeypatch.setattr(
        vpn_server_setup,
        "load_xray_config",
        lambda: {"broken": True},
    )
    monkeypatch.setattr(
        vpn_server_setup,
        "get_xray_readiness",
        lambda config: (False, ["broken"]),
    )

    def fail_build(**kwargs):
        raise RuntimeError("generation failed")

    monkeypatch.setattr(
        vpn_server_setup,
        "_build_xray_config",
        fail_build,
    )

    result = vpn_server_setup.setup_xray_server()

    assert result.created is False
    assert config_path.read_text(encoding="utf-8") == original
    assert len(list(tmp_path.glob("config.json.bak-*"))) == 1


def test_setup_xray_server_saves_generated_config(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"

    monkeypatch.setattr(vpn_server_setup, "XRAY_CONF", config_path)
    monkeypatch.setattr(xray_config_manager, "XRAY_CONF", config_path)

    expected = {
        "inbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {
                            "id": "uuid",
                            "email": "default",
                        }
                    ]
                },
            }
        ]
    }

    monkeypatch.setattr(
        vpn_server_setup,
        "_build_xray_config",
        lambda **kwargs: expected,
    )

    saved = {}

    def fake_save(config):
        saved["config"] = config

    monkeypatch.setattr(vpn_server_setup, "save_xray_config", fake_save)

    result = vpn_server_setup.setup_xray_server()

    assert result.created is True
    assert saved["config"] == expected


def test_build_awg_config(monkeypatch):
    monkeypatch.setattr(
        vpn_server_setup,
        "_generate_awg_private_key",
        lambda: "test-awg-private-key",
    )

    config = vpn_server_setup._build_awg_config()

    assert "PrivateKey = test-awg-private-key" in config
    assert "Address = 10.66.66.1/24" in config
    assert "ListenPort = 58352" in config
    assert "Jc = 4" in config
    assert "Jmin = 40" in config
    assert "Jmax = 70" in config
    assert "S1 = 117" in config
    assert "S2 = 74" in config
    assert "S3 = 63" in config
    assert "S4 = 82" in config
    assert "H1 = 1" in config
    assert "H2 = 2" in config
    assert "H3 = 3" in config
    assert "H4 = 4" in config
    assert "[Peer]" not in config


def test_setup_awg_server_does_not_overwrite_working_config(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "awg0.conf"

    config = (
        "[Interface]\n"
        "PrivateKey = valid-private-key\n"
        "Address = 10.66.66.1/24\n"
        "ListenPort = 58352\n"
    )
    config_path.write_text(config, encoding="utf-8")

    monkeypatch.setattr(vpn_server_setup, "AWG_CONF", config_path)

    result = vpn_server_setup.setup_awg_server()

    assert result.created is False
    assert config_path.read_text(encoding="utf-8") == config


def test_setup_awg_server_keeps_existing_config_when_generation_fails(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "awg0.conf"
    original = "[Interface]\\nPrivateKey = REPLACE_WITH_KEY\\n"
    config_path.write_text(original, encoding="utf-8")

    monkeypatch.setattr(vpn_server_setup, "AWG_CONF", config_path)

    def fail_key_generation():
        raise RuntimeError("generation failed")

    monkeypatch.setattr(
        vpn_server_setup,
        "_generate_awg_private_key",
        fail_key_generation,
    )

    result = vpn_server_setup.setup_awg_server()

    assert result.created is False
    assert config_path.read_text(encoding="utf-8") == original
    assert len(list(tmp_path.glob("awg0.conf.bak-*"))) == 1


def test_setup_awg_server_backs_up_broken_config(monkeypatch, tmp_path):
    config_path = tmp_path / "awg0.conf"
    config_path.write_text(
        "[Interface]\\nPrivateKey = REPLACE_WITH_KEY\\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(vpn_server_setup, "AWG_CONF", config_path)
    monkeypatch.setattr(
        vpn_server_setup,
        "_generate_awg_private_key",
        lambda: "generated-private-key",
    )

    saved = {}

    def fake_save(content):
        saved["content"] = content

    monkeypatch.setattr(vpn_server_setup, "_save_awg_candidate", fake_save)

    result = vpn_server_setup.setup_awg_server()

    assert result.created is True
    assert "Backup" in result.message
    assert list(tmp_path.glob("awg0.conf.bak-*"))
    assert "generated-private-key" in saved["content"]
