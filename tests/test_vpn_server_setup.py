
from services import vpn_server_setup
from services.awg import config_manager as awg_config_manager
from services.awg import network as awg_network
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

    api_inbound = next(
        inbound
        for inbound in config["inbounds"]
        if inbound.get("tag") == "api"
    )
    assert api_inbound == {
        "listen": "127.0.0.1",
        "port": 10085,
        "protocol": "dokodemo-door",
        "settings": {
            "address": "127.0.0.1",
        },
        "tag": "api",
    }

    assert config["api"] == {
        "tag": "api",
        "services": ["HandlerService", "LoggerService", "StatsService"],
    }
    assert config["log"]["access"] == str(vpn_server_setup.XRAY_ACCESS_LOG)
    assert config["stats"] == {}
    assert config["policy"]["levels"]["0"] == {
        "statsUserUplink": True,
        "statsUserDownlink": True,
    }
    assert not any(
        outbound.get("tag") == "api"
        for outbound in config["outbounds"]
    )

    assert config["routing"]["rules"] == [
        {
            "type": "field",
            "inboundTag": ["api"],
            "outboundTag": "api",
        }
    ]


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


def test_setup_xray_server_refuses_broken_config_without_backup(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "config.json"
    original = '{"inbounds": [{"protocol": "vless"}]}'
    config_path.write_text(original, encoding="utf-8")

    monkeypatch.setattr(vpn_server_setup, "XRAY_CONF", config_path)
    monkeypatch.setattr(
        vpn_server_setup, "load_xray_config",
        lambda: {"inbounds": [{"protocol": "vless"}]},
    )
    monkeypatch.setattr(
        vpn_server_setup, "get_xray_readiness",
        lambda config: (False, ["broken config"]),
    )
    monkeypatch.setattr(
        vpn_server_setup, "_build_xray_config",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("Нельзя генерировать новые ключи")
        ),
    )

    result = vpn_server_setup.setup_xray_server()

    assert result.created is False
    assert config_path.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob("config.json.bak-*"))



def test_setup_xray_server_does_not_backup_or_replace_invalid_config(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "config.json"
    original = '{"broken": true}'
    config_path.write_text(original, encoding="utf-8")

    monkeypatch.setattr(vpn_server_setup, "XRAY_CONF", config_path)
    monkeypatch.setattr(
        vpn_server_setup, "load_xray_config", lambda: {"broken": True}
    )
    monkeypatch.setattr(
        vpn_server_setup, "get_xray_readiness",
        lambda config: (False, ["invalid"]),
    )

    result = vpn_server_setup.setup_xray_server()

    assert result.created is False
    assert config_path.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob("config.json.bak-*"))



def test_setup_xray_server_creates_config_and_starts_new_service(
    monkeypatch, tmp_path
):
    import json

    config_path = tmp_path / "config.json"
    candidate = {"inbounds": [{"protocol": "vless", "port": 8443}]}

    monkeypatch.setattr(vpn_server_setup, "XRAY_CONF", config_path)
    monkeypatch.setattr(
        xray_config_manager, "XRAY_CONF", config_path
    )
    monkeypatch.setattr(
        vpn_server_setup, "_build_xray_config",
        lambda **kwargs: candidate,
    )
    monkeypatch.setattr(
        vpn_server_setup, "validate_xray_config", lambda config: True
    )
    monkeypatch.setattr(
        vpn_server_setup, "get_service_state",
        lambda service: "inactive" if not config_path.exists() else "active",
    )
    monkeypatch.setattr(
        vpn_server_setup, "run_systemctl",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        vpn_server_setup, "save_xray_config",
        lambda config: (
            config_path.write_text(json.dumps(config), encoding="utf-8"),
            config_path.chmod(0o644),
        ),
    )

    result = vpn_server_setup.setup_xray_server(port=8443)

    assert result.created is True
    assert json.loads(config_path.read_text(encoding="utf-8")) == candidate
    assert config_path.stat().st_mode & 0o777 == 0o644



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


def test_setup_awg_server_reconfigures_without_changing_identity(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "awg0.conf"
    original = (
        "[Interface]\n"
        "PrivateKey = server-private-key\n"
        "Address = 10.66.66.1/24\n"
        "ListenPort = 58352\n"
        "Jc = 4\nJmin = 40\nJmax = 70\n"
        "S1 = 117\nS2 = 74\nS3 = 63\nS4 = 82\n"
        "H1 = 1\nH2 = 2\nH3 = 3\nH4 = 4\n"
        "\n# Name: Alice\n[Peer]\n"
        "PublicKey = alice-public-key\n"
        "PresharedKey = alice-psk\n"
        "AllowedIPs = 10.66.66.8/32\n"
        "PostUp = iptables -A TEST\n"
    )
    config_path.write_text(original, encoding="utf-8")

    monkeypatch.setattr(vpn_server_setup, "AWG_CONF", config_path)
    monkeypatch.setattr(awg_config_manager, "AWG_CONF", config_path)
    monkeypatch.setattr(
        vpn_server_setup, "get_awg_readiness",
        lambda content: (True, []),
    )
    monkeypatch.setattr(
        vpn_server_setup, "_run_command", lambda *args, **kwargs: ""
    )
    monkeypatch.setattr(
        vpn_server_setup, "get_service_state", lambda service: "inactive"
    )
    monkeypatch.setattr(
        vpn_server_setup, "save_awg_config",
        lambda content: config_path.write_text(content, encoding="utf-8"),
    )

    result = vpn_server_setup.setup_awg_server(port=58353, jc=5)

    updated = config_path.read_text(encoding="utf-8")
    assert result.created is True
    assert "PrivateKey = server-private-key" in updated
    assert "Address = 10.66.66.1/24" in updated
    assert "ListenPort = 58353" in updated
    assert "Jc = 5" in updated
    assert "PublicKey = alice-public-key" in updated
    assert "PresharedKey = alice-psk" in updated
    assert "AllowedIPs = 10.66.66.8/32" in updated
    assert "PostUp = iptables -A TEST" in updated
    assert list(tmp_path.glob("awg0.conf.bak-*"))



def test_setup_awg_server_refuses_invalid_config_without_backup(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "awg0.conf"
    original = "[Interface]\nPrivateKey = REPLACE_WITH_KEY\n"
    config_path.write_text(original, encoding="utf-8")

    monkeypatch.setattr(vpn_server_setup, "AWG_CONF", config_path)
    monkeypatch.setattr(
        vpn_server_setup, "get_awg_readiness",
        lambda content: (False, ["placeholder key"]),
    )
    monkeypatch.setattr(
        vpn_server_setup, "_generate_awg_private_key",
        lambda: (_ for _ in ()).throw(
            AssertionError("Нельзя генерировать ключ для существующего конфига")
        ),
    )

    result = vpn_server_setup.setup_awg_server()

    assert result.created is False
    assert config_path.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob("awg0.conf.bak-*"))



def test_setup_awg_server_does_not_replace_broken_config(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "awg0.conf"
    original = "[Interface]\nPrivateKey = broken\n"
    config_path.write_text(original, encoding="utf-8")

    monkeypatch.setattr(vpn_server_setup, "AWG_CONF", config_path)
    monkeypatch.setattr(
        vpn_server_setup, "get_awg_readiness",
        lambda content: (False, ["broken config"]),
    )

    result = vpn_server_setup.setup_awg_server()

    assert result.created is False
    assert config_path.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob("awg0.conf.bak-*"))



def test_build_awg_network_hooks_uses_default_route(monkeypatch):
    monkeypatch.setattr(
        awg_network,
        "get_default_route_interface",
        lambda: "ens3",
    )

    hooks = awg_network.build_awg_network_hooks(
        address="10.66.66.1/24",
    )

    assert hooks.wan_interface == "ens3"
    assert any(
        "10.66.66.0/24" in command
        for command in hooks.post_up
    )
    assert any(
        "-s 10.66.66.0/24 -o ens3 "
        "-m comment --comment ZverTBot-AWG -j MASQUERADE" in command
        for command in hooks.post_up
    )
    assert all(
        "ZverTBot-AWG" in command
        for command in hooks.post_up
    )
    assert all(
        "ZverTBot-AWG" in command
        for command in hooks.post_down
    )


def test_extract_awg_peer_blocks_preserves_full_blocks():
    content = (
        "[Interface]\n"
        "PrivateKey = broken\n"
        "\n# Name: Alice\n"
        "[Peer]\n"
        "PublicKey = alice-key\n"
        "AllowedIPs = 10.66.66.8/32\n"
        "PresharedKey = alice-psk\n"
        "PersistentKeepalive = 25\n"
        "\n# Name: Bob\n"
        "[Peer]\n"
        "PublicKey = bob-key\n"
        "AllowedIPs = 10.66.66.9/32\n"
    )

    blocks = vpn_server_setup._extract_awg_peer_blocks(content)

    assert len(blocks) == 2
    assert "# Name: Alice" in blocks[0]
    assert "PresharedKey = alice-psk" in blocks[0]
    assert "PersistentKeepalive = 25" in blocks[0]
    assert "# Name: Bob" in blocks[1]
    assert "AllowedIPs = 10.66.66.9/32" in blocks[1]


def test_extract_awg_peer_blocks_ignores_example_placeholder():
    content = (
        "[Interface]\n"
        "PrivateKey = broken\n"
        "\n# Name: example\n"
        "[Peer]\n"
        "PublicKey = REPLACE_WITH_CLIENT_PUBLIC_KEY\n"
        "AllowedIPs = 10.66.66.12/32\n"
        "\n# Name: Alice\n"
        "[Peer]\n"
        "PublicKey = alice-key\n"
        "AllowedIPs = 10.66.66.8/32\n"
    )

    blocks = vpn_server_setup._extract_awg_peer_blocks(content)

    assert len(blocks) == 1
    assert "# Name: Alice" in blocks[0]
    assert "alice-key" in blocks[0]
    assert "REPLACE_WITH_CLIENT_PUBLIC_KEY" not in blocks[0]
    assert "10.66.66.12/32" not in blocks[0]


def test_build_awg_config_keeps_peer_blocks(monkeypatch):
    monkeypatch.setattr(
        vpn_server_setup,
        "_generate_awg_private_key",
        lambda: "test-awg-private-key",
    )

    hooks = awg_network.AwgNetworkHooks(
        wan_interface="ens3",
        post_up=("iptables -A TEST",),
        post_down=("iptables -D TEST",),
    )

    peer = (
        "# Name: Alice\n"
        "[Peer]\n"
        "PublicKey = alice-key\n"
        "AllowedIPs = 10.66.66.8/32\n"
    )

    config = vpn_server_setup._build_awg_config(
        peer_blocks=[peer],
        network_hooks=hooks,
    )

    assert "PostUp = iptables -A TEST" in config
    assert "PostDown = iptables -D TEST" in config
    assert peer.strip() in config


def test_setup_awg_server_preserves_peers_and_hooks_on_reconfigure(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "awg0.conf"
    original = (
        "[Interface]\n"
        "PrivateKey = preserved-server-key\n"
        "Address = 10.66.66.1/24\n"
        "ListenPort = 58352\n"
        "Jc = 4\nJmin = 40\nJmax = 70\n"
        "S1 = 117\nS2 = 74\nS3 = 63\nS4 = 82\n"
        "H1 = 1\nH2 = 2\nH3 = 3\nH4 = 4\n"
        "PostUp = iptables -A CUSTOM\n"
        "PostDown = iptables -D CUSTOM\n"
        "\n# Name: Alice\n[Peer]\n"
        "PublicKey = alice-key\n"
        "PresharedKey = alice-psk\n"
        "AllowedIPs = 10.66.66.8/32\n"
    )
    config_path.write_text(original, encoding="utf-8")

    monkeypatch.setattr(vpn_server_setup, "AWG_CONF", config_path)
    monkeypatch.setattr(awg_config_manager, "AWG_CONF", config_path)
    monkeypatch.setattr(
        vpn_server_setup, "get_awg_readiness",
        lambda content: (True, []),
    )
    monkeypatch.setattr(
        vpn_server_setup, "_run_command", lambda *args, **kwargs: ""
    )
    monkeypatch.setattr(
        vpn_server_setup, "get_service_state", lambda service: "inactive"
    )
    monkeypatch.setattr(
        vpn_server_setup, "save_awg_config",
        lambda content: config_path.write_text(content, encoding="utf-8"),
    )

    result = vpn_server_setup.setup_awg_server(port=58354, jc=6)

    updated = config_path.read_text(encoding="utf-8")
    assert result.created is True
    assert "PrivateKey = preserved-server-key" in updated
    assert "Address = 10.66.66.1/24" in updated
    assert "ListenPort = 58354" in updated
    assert "Jc = 6" in updated
    assert "PostUp = iptables -A CUSTOM" in updated
    assert "PostDown = iptables -D CUSTOM" in updated
    assert "# Name: Alice" in updated
    assert "PublicKey = alice-key" in updated
    assert "PresharedKey = alice-psk" in updated
    assert "AllowedIPs = 10.66.66.8/32" in updated
    assert list(tmp_path.glob("awg0.conf.bak-*"))




def test_setup_xray_server_reconfigures_reality_without_losing_identity(
    monkeypatch, tmp_path
):
    import json

    config_path = tmp_path / "config.json"
    original = {
        "inbounds": [
            {
                "protocol": "vless",
                "tag": "vless-in",
                "port": 2096,
                "settings": {
                    "clients": [
                        {"id": "uuid-kept", "email": "existing-user",
                         "flow": "xtls-rprx-vision"}
                    ]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "dest": "old.example:443",
                        "serverNames": ["old.example"],
                        "privateKey": "reality-private-key-kept",
                        "shortIds": ["0123456789abcdef"],
                    },
                },
            },
            {
                "protocol": "dokodemo-door",
                "tag": "api",
                "port": 10085,
            },
        ],
        "api": {"tag": "api", "services": ["HandlerService"]},
        "outbounds": [{"protocol": "freedom", "tag": "direct"}],
        "routing": {
            "rules": [
                {"type": "field", "inboundTag": ["api"], "outboundTag": "api"}
            ]
        },
    }
    config_path.write_text(json.dumps(original), encoding="utf-8")

    monkeypatch.setattr(vpn_server_setup, "XRAY_CONF", config_path)
    monkeypatch.setattr(xray_config_manager, "XRAY_CONF", config_path)
    monkeypatch.setattr(vpn_server_setup, "load_xray_config", lambda: original)
    monkeypatch.setattr(
        vpn_server_setup, "get_xray_readiness",
        lambda config: (True, []),
    )
    monkeypatch.setattr(
        vpn_server_setup, "validate_xray_config", lambda config: True
    )
    monkeypatch.setattr(
        vpn_server_setup, "get_service_state", lambda service: "inactive"
    )
    monkeypatch.setattr(
        vpn_server_setup, "save_xray_config",
        lambda config: config_path.write_text(
            json.dumps(config), encoding="utf-8"
        ),
    )

    result = vpn_server_setup.setup_xray_server(
        port=8443,
        sni="new.example",
        dest="new.example:443",
    )

    updated = json.loads(config_path.read_text(encoding="utf-8"))
    inbound = updated["inbounds"][0]
    reality = inbound["streamSettings"]["realitySettings"]

    assert result.created is True
    assert inbound["port"] == 8443
    assert inbound["settings"]["clients"][0]["id"] == "uuid-kept"
    assert inbound["settings"]["clients"][0]["email"] == "existing-user"
    assert inbound["settings"]["clients"][0]["flow"] == "xtls-rprx-vision"
    assert reality["privateKey"] == "reality-private-key-kept"
    assert reality["shortIds"] == ["0123456789abcdef"]
    assert reality["dest"] == "new.example:443"
    assert reality["serverNames"] == ["new.example"]
    assert updated["api"] == original["api"]
    assert updated["outbounds"] == original["outbounds"]
    assert updated["routing"] == original["routing"]
    assert list(tmp_path.glob("config.json.bak-*"))



def test_build_xray_config_accepts_custom_parameters(monkeypatch):
    monkeypatch.setattr(
        vpn_server_setup,
        "_generate_uuid",
        lambda: "test-uuid",
    )
    monkeypatch.setattr(
        vpn_server_setup,
        "_generate_reality_private_key",
        lambda: "test-private-key",
    )
    monkeypatch.setattr(
        vpn_server_setup,
        "_generate_short_id",
        lambda: "0123456789abcdef",
    )

    config = vpn_server_setup._build_xray_config(
        port=8443,
        sni="example.com",
        dest="example.com:443",
        flow="",
    )

    inbound = config["inbounds"][0]
    reality = inbound["streamSettings"]["realitySettings"]
    client = inbound["settings"]["clients"][0]

    assert inbound["port"] == 8443
    assert client["flow"] == ""
    assert reality["serverNames"] == ["example.com"]
    assert reality["dest"] == "example.com:443"


def test_build_awg_config_accepts_custom_parameters(monkeypatch):
    monkeypatch.setattr(
        vpn_server_setup,
        "_generate_awg_private_key",
        lambda: "test-awg-private-key",
    )

    config = vpn_server_setup._build_awg_config(
        port=51820,
        jc=5,
        jmin=30,
        jmax=80,
        s1=101,
        s2=102,
        s3=103,
        s4=104,
        h1=11,
        h2=12,
        h3=13,
        h4=14,
    )

    expected = {
        "ListenPort": 51820,
        "Jc": 5,
        "Jmin": 30,
        "Jmax": 80,
        "S1": 101,
        "S2": 102,
        "S3": 103,
        "S4": 104,
        "H1": 11,
        "H2": 12,
        "H3": 13,
        "H4": 14,
    }

    for key, value in expected.items():
        assert f"{key} = {value}" in config

    assert "Address = 10.66.66.1/24" in config


def test_setup_xray_initial_only_does_not_replace_existing_config(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "config.json"
    original = "{ broken existing config"

    config_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(vpn_server_setup, "XRAY_CONF", config_path)

    result = vpn_server_setup.setup_xray_server(initial_setup_only=True)

    assert result.created is False
    assert config_path.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob("config.json.bak-*"))


def test_setup_awg_initial_only_does_not_replace_existing_config(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "awg0.conf"
    original = "[Interface]\nPrivateKey = broken\n"

    config_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(vpn_server_setup, "AWG_CONF", config_path)

    result = vpn_server_setup.setup_awg_server(initial_setup_only=True)

    assert result.created is False
    assert config_path.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob("awg0.conf.bak-*"))


def test_xray_reconfigure_rolls_back_config_when_restart_fails(
    monkeypatch, tmp_path
):
    import json

    config_path = tmp_path / "config.json"
    original = {
        "inbounds": [{
            "protocol": "vless",
            "port": 2096,
            "settings": {
                "clients": [{"id": "preserved-uuid"}],
            },
            "streamSettings": {
                "network": "tcp",
                "security": "reality",
                "realitySettings": {
                    "dest": "old.example:443",
                    "serverNames": ["old.example"],
                    "privateKey": "preserved-private-key",
                    "shortIds": ["0123456789abcdef"],
                },
            },
        }],
        "outbounds": [{"protocol": "freedom"}],
    }
    original_text = json.dumps(original, indent=4) + "\n"
    config_path.write_text(original_text, encoding="utf-8")

    monkeypatch.setattr(vpn_server_setup, "XRAY_CONF", config_path)
    monkeypatch.setattr(
        xray_config_manager, "XRAY_CONF", config_path
    )
    monkeypatch.setattr(
        vpn_server_setup, "load_xray_config", lambda: original
    )
    monkeypatch.setattr(
        vpn_server_setup, "get_xray_readiness",
        lambda _config: (True, []),
    )
    monkeypatch.setattr(
        vpn_server_setup, "validate_xray_config",
        lambda _config: True,
    )
    monkeypatch.setattr(
        vpn_server_setup, "get_service_state",
        lambda _service: "active",
    )

    def save_config(config):
        config_path.write_text(json.dumps(config), encoding="utf-8")

    monkeypatch.setattr(
        vpn_server_setup, "save_xray_config", save_config
    )

    restart_calls = []

    def fail_first_restart(service):
        restart_calls.append(service)
        if len(restart_calls) == 1:
            raise RuntimeError("simulated restart failure")

    monkeypatch.setattr(
        vpn_server_setup, "restart_service", fail_first_restart
    )

    result = vpn_server_setup.setup_xray_server(
        port=8443,
        sni="new.example",
        dest="new.example:443",
    )

    assert result.created is False
    assert "simulated restart failure" in result.message
    assert config_path.read_text(encoding="utf-8") == original_text
    assert len(list(tmp_path.glob("config.json.bak-*"))) == 1
    assert restart_calls == ["xray", "xray"]


def test_awg_reconfigure_rolls_back_config_when_restart_fails(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "awg0.conf"
    original = (
        "[Interface]\n"
        "PrivateKey = preserved-private-key\n"
        "Address = 10.66.66.1/24\n"
        "ListenPort = 58352\n"
        "Jc = 4\nJmin = 40\nJmax = 70\n"
        "S1 = 117\nS2 = 74\nS3 = 63\nS4 = 82\n"
        "H1 = 1\nH2 = 2\nH3 = 3\nH4 = 4\n"
        "PostUp = iptables -A CUSTOM\n"
        "PostDown = iptables -D CUSTOM\n"
        "\n[Peer]\n"
        "PublicKey = preserved-peer\n"
        "AllowedIPs = 10.66.66.8/32\n"
    )
    config_path.write_text(original, encoding="utf-8")

    monkeypatch.setattr(vpn_server_setup, "AWG_CONF", config_path)
    monkeypatch.setattr(
        awg_config_manager, "AWG_CONF", config_path
    )
    monkeypatch.setattr(
        vpn_server_setup, "get_awg_readiness",
        lambda _content: (True, []),
    )
    monkeypatch.setattr(
        vpn_server_setup, "_validate_awg_candidate", lambda _content: None
    )
    monkeypatch.setattr(
        vpn_server_setup, "get_service_state",
        lambda _service: "active",
    )
    monkeypatch.setattr(
        vpn_server_setup, "save_awg_config",
        lambda content: config_path.write_text(content, encoding="utf-8"),
    )

    restart_calls = []

    def fail_first_restart(service):
        restart_calls.append(service)
        if len(restart_calls) == 1:
            raise RuntimeError("simulated restart failure")

    monkeypatch.setattr(
        vpn_server_setup, "restart_service", fail_first_restart
    )

    result = vpn_server_setup.setup_awg_server(
        port=58354,
        jc=6,
    )

    assert result.created is False
    assert "simulated restart failure" in result.message
    assert config_path.read_text(encoding="utf-8") == original
    assert len(list(tmp_path.glob("awg0.conf.bak-*"))) == 1
    assert restart_calls == [
        "awg-quick@awg0",
        "awg-quick@awg0",
    ]



def test_awg_reconfigure_rejects_duplicate_interface_section():
    content = """[Interface]
PrivateKey = SERVER_KEY
Address = 10.66.66.1/24
ListenPort = 58352

[Peer]
PublicKey = PEER_KEY
AllowedIPs = 10.66.66.2/32

[Interface]
PrivateKey = ANOTHER_KEY
"""

    try:
        vpn_server_setup._modify_awg_config(
            content, port=58353, params={}
        )
    except ValueError as exc:
        assert "ровно одну секцию [Interface]" in str(exc)
    else:
        raise AssertionError("Ожидался отказ при повторной секции [Interface]")


def test_awg_reconfigure_rejects_duplicate_interface_parameter():
    content = """[Interface]
PrivateKey = SERVER_KEY
Address = 10.66.66.1/24
ListenPort = 58352
ListenPort = 58353
"""

    try:
        vpn_server_setup._modify_awg_config(
            content, port=58354, params={}
        )
    except ValueError as exc:
        assert "Дублирующийся параметр AWG: listenport" in str(exc)
    else:
        raise AssertionError("Ожидался отказ при повторном ListenPort")


def test_awg_reconfigure_preserves_multiple_postup_postdown():
    content = """[Interface]
PrivateKey = SERVER_KEY
Address = 10.66.66.1/24
ListenPort = 58352
PostUp = first rule
PostUp = second rule
PostDown = first cleanup
PostDown = second cleanup

[Peer]
PublicKey = PEER_KEY
AllowedIPs = 10.66.66.2/32
"""

    result = vpn_server_setup._modify_awg_config(
        content, port=58350, params={"jc": 4}
    )

    assert "PostUp = first rule" in result
    assert "PostUp = second rule" in result
    assert "PostDown = first cleanup" in result
    assert "PostDown = second cleanup" in result
    assert result.count("PostUp =") == 3
    assert result.count("PostDown =") == 4
    assert "PostUp = first rule" in result
    assert "PostUp = second rule" in result
    assert "PostDown = first cleanup" in result
    assert "PostDown = second cleanup" in result
    assert "ListenPort = 58350" in result
    assert "Jc = 4" in result


def test_validate_awg_candidate_uses_valid_interface_filename(
    tmp_path, monkeypatch
):
    from pathlib import Path

    monkeypatch.setattr(
        vpn_server_setup, "AWG_CONF", tmp_path / "awg0.conf"
    )
    monkeypatch.setattr(
        vpn_server_setup, "get_awg_readiness",
        lambda _content: (True, []),
    )

    temp_dirs = []

    def fake_run_command(*args, **kwargs):
        path = Path(args[2])
        temp_dirs.append(path.parent)
        assert path.name == "awg0.conf"
        assert path.read_text(encoding="utf-8") == "test config"

    monkeypatch.setattr(vpn_server_setup, "_run_command", fake_run_command)

    vpn_server_setup._validate_awg_candidate("test config")

    assert len(temp_dirs) == 1
    assert not temp_dirs[0].exists()


def test_validate_awg_candidate_cleans_temp_directory_on_error(
    tmp_path, monkeypatch
):
    from pathlib import Path

    monkeypatch.setattr(
        vpn_server_setup, "AWG_CONF", tmp_path / "awg0.conf"
    )
    monkeypatch.setattr(
        vpn_server_setup, "get_awg_readiness",
        lambda _content: (True, []),
    )

    temp_dirs = []

    def fail_command(*args, **kwargs):
        path = Path(args[2])
        temp_dirs.append(path.parent)
        assert path.name == "awg0.conf"
        raise RuntimeError("validation failed")

    monkeypatch.setattr(vpn_server_setup, "_run_command", fail_command)

    try:
        vpn_server_setup._validate_awg_candidate("test config")
    except RuntimeError as exc:
        assert "validation failed" in str(exc)
    else:
        raise AssertionError("Ожидалась ошибка проверки AWG")

    assert len(temp_dirs) == 1
    assert not temp_dirs[0].exists()


def test_build_awg_input_firewall_hooks():
    post_up, post_down = awg_network.build_awg_input_firewall_hooks(
        listen_port=58354,
        previous_listen_port=58352,
    )

    assert len(post_up) == 1
    assert "--dport 58354" in post_up[0]
    assert "iptables -C INPUT" in post_up[0]
    assert "iptables -I INPUT" in post_up[0]
    assert "ZverTBot-AWG-INPUT" in post_up[0]

    assert len(post_down) == 2
    assert any("--dport 58352" in command for command in post_down)
    assert any("--dport 58354" in command for command in post_down)
    assert all("iptables -D INPUT" in command for command in post_down)


def test_build_awg_input_firewall_hooks_rejects_invalid_port():
    import pytest

    for port in (0, 65536, -1, True):
        with pytest.raises(ValueError, match="UDP-порт AWG"):
            awg_network.build_awg_input_firewall_hooks(port)


def test_awg_reconfigure_updates_managed_input_hooks_and_preserves_custom():
    original = (
        "[Interface]\n"
        "PrivateKey = preserved-server-key\n"
        "Address = 10.66.66.1/24\n"
        "ListenPort = 58352\n"
        "Jc = 4\nJmin = 40\nJmax = 70\n"
        "S1 = 117\nS2 = 74\nS3 = 63\nS4 = 82\n"
        "H1 = 1\nH2 = 2\nH3 = 3\nH4 = 4\n"
        "PostUp = iptables -A CUSTOM\n"
        "PostDown = iptables -D CUSTOM\n"
        "\n[Peer]\n"
        "PublicKey = preserved-peer\n"
        "AllowedIPs = 10.66.66.8/32\n"
    )

    updated = vpn_server_setup._modify_awg_config(
        original,
        port=58354,
        params={"jc": 6},
    )

    assert "ListenPort = 58354" in updated
    assert "PostUp = iptables -A CUSTOM" in updated
    assert "PostDown = iptables -D CUSTOM" in updated
    assert "PublicKey = preserved-peer" in updated

    assert "PostUp = iptables -C INPUT -p udp --dport 58354" in updated
    assert "--dport 58352" in updated
    assert "ZverTBot-AWG-INPUT" in updated

    # Повторная перенастройка не должна накапливать старые managed hooks.
    updated_again = vpn_server_setup._modify_awg_config(
        updated,
        port=58355,
        params={"jc": 7},
    )
    assert updated_again.count("ZverTBot-AWG-INPUT") == 6
    assert "--dport 58352" not in updated_again
    assert "--dport 58354" in updated_again
    assert "--dport 58355" in updated_again
