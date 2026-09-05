"""
Тесты генерации VLESS Reality ссылок Xray.
"""

from urllib.parse import urlsplit

import services.xray.link_generator as lg

TEST_PRIVATE_KEY = "test-private-key"
TEST_PUBLIC_KEY = "test-public-key"
TEST_SHORT_ID = "a4f95e5638be4edd"


def make_inbound(port, sni, clients):
    return {
        "protocol": "vless",
        "port": port,
        "settings": {
            "clients": clients,
        },
        "streamSettings": {
            "network": "tcp",
            "security": "reality",
            "realitySettings": {
                "serverNames": [sni],
                "privateKey": TEST_PRIVATE_KEY,
                "shortIds": [TEST_SHORT_ID],
            },
        },
    }


def sample_config():
    return {
        "inbounds": [
            make_inbound(
                443,
                "mts.example.com",
                [
                    {
                        "id": "uuid-1",
                        "email": "user1",
                    }
                ],
            ),
            make_inbound(
                2096,
                "beeline.example.com",
                [
                    {
                        "id": "uuid-1",
                        "email": "user1",
                    }
                ],
            ),
        ]
    }


def decode_vless_userinfo(link):
    return urlsplit(link).netloc


def patch_reality_public_key(monkeypatch):
    monkeypatch.setattr(
        lg,
        "_get_reality_public_key",
        lambda private_key: TEST_PUBLIC_KEY,
    )


def test_xray_get_link_two_inbounds(monkeypatch):
    monkeypatch.setattr(
        lg,
        "load_xray_config",
        lambda: sample_config(),
    )
    patch_reality_public_key(monkeypatch)

    result = lg.xray_get_link("user1")

    links = result.split("\n")

    assert len(links) == 2
    assert ":443" in decode_vless_userinfo(links[0])
    assert ":2096" in decode_vless_userinfo(links[1])


def test_xray_get_link_single_inbound(monkeypatch):
    cfg = {
        "inbounds": [
            make_inbound(
                443,
                "test.example.com",
                [
                    {
                        "id": "uuid-1",
                        "email": "user1",
                    }
                ],
            )
        ]
    }

    monkeypatch.setattr(
        lg,
        "load_xray_config",
        lambda: cfg,
    )
    patch_reality_public_key(monkeypatch)

    result = lg.xray_get_link("user1")

    assert result.startswith("vless://")
    assert ":443" in decode_vless_userinfo(result)


def test_xray_get_link_missing_user(monkeypatch):
    monkeypatch.setattr(
        lg,
        "load_xray_config",
        lambda: sample_config(),
    )
    patch_reality_public_key(monkeypatch)

    result = lg.xray_get_link("unknown")

    assert result == ""


def test_xray_get_link_missing_clients(monkeypatch):
    cfg = {
        "inbounds": [
            {
                "protocol": "vless",
                "port": 443,
                "settings": {},
                "streamSettings": {
                    "security": "reality",
                    "realitySettings": {
                        "serverNames": ["test.example.com"],
                        "privateKey": TEST_PRIVATE_KEY,
                        "shortIds": [TEST_SHORT_ID],
                    },
                },
            }
        ]
    }

    monkeypatch.setattr(
        lg,
        "load_xray_config",
        lambda: cfg,
    )
    patch_reality_public_key(monkeypatch)

    assert lg.xray_get_link("user1") == ""


def test_xray_get_link_for_port(monkeypatch):
    monkeypatch.setattr(
        lg,
        "load_xray_config",
        lambda: sample_config(),
    )
    patch_reality_public_key(monkeypatch)

    result = lg.xray_get_link_for_port(
        "user1",
        2096,
    )

    assert result.startswith("vless://")
    assert ":2096" in decode_vless_userinfo(result)


def test_xray_get_link_for_wrong_port(monkeypatch):
    monkeypatch.setattr(
        lg,
        "load_xray_config",
        lambda: sample_config(),
    )
    patch_reality_public_key(monkeypatch)

    result = lg.xray_get_link_for_port(
        "user1",
        9999,
    )

    assert result == ""


def test_reality_public_key_is_taken_from_private_key(monkeypatch):
    calls = []

    def fake_public_key(private_key):
        calls.append(private_key)
        return TEST_PUBLIC_KEY

    monkeypatch.setattr(
        lg,
        "_get_reality_public_key",
        fake_public_key,
    )

    cfg = sample_config()

    monkeypatch.setattr(
        lg,
        "load_xray_config",
        lambda: cfg,
    )

    result = lg.xray_get_link("user1")

    assert result
    assert calls == [
        TEST_PRIVATE_KEY,
        TEST_PRIVATE_KEY,
    ]


def test_reality_settings_missing_private_key(monkeypatch):
    cfg = sample_config()
    del cfg["inbounds"][0]["streamSettings"]["realitySettings"]["privateKey"]

    monkeypatch.setattr(
        lg,
        "load_xray_config",
        lambda: cfg,
    )

    result = lg.xray_get_link("user1")

    assert result == ""


def test_reality_settings_missing_short_id(monkeypatch):
    cfg = sample_config()
    cfg["inbounds"][0]["streamSettings"]["realitySettings"]["shortIds"] = []

    monkeypatch.setattr(
        lg,
        "load_xray_config",
        lambda: cfg,
    )

    result = lg.xray_get_link("user1")

    assert result == ""


def test_get_reality_public_key_success(monkeypatch):
    class FakeResult:
        stdout = "Password (PublicKey): my-public-key\n"

    monkeypatch.setattr(lg.subprocess, "run", lambda *args, **kwargs: FakeResult())

    result = lg._get_reality_public_key("my-private-key")
    assert result == "my-public-key"


def test_get_reality_public_key_no_match(monkeypatch):
    class FakeResult:
        stdout = "Some other output\n"

    monkeypatch.setattr(lg.subprocess, "run", lambda *args, **kwargs: FakeResult())

    import pytest

    with pytest.raises(RuntimeError, match="Xray не вернул PublicKey для Reality"):
        lg._get_reality_public_key("my-private-key")


def test_xray_get_ports_success(monkeypatch):
    cfg = {
        "inbounds": [
            {
                "protocol": "vless",
                "port": 443,
                "settings": {"clients": [{"email": "user1"}]},
            },
            {
                "protocol": "vless",
                "port": 8443,
                "settings": {"clients": [{"email": "user2"}]},
            },
        ]
    }
    monkeypatch.setattr(lg, "load_xray_config", lambda: cfg)

    assert lg.xray_get_ports("user1") == [443]


def test_xray_get_ports_missing_port(monkeypatch):
    cfg = {
        "inbounds": [
            {
                "protocol": "vless",
                "settings": {"clients": [{"email": "user1"}]},
            }
        ]
    }
    monkeypatch.setattr(lg, "load_xray_config", lambda: cfg)

    assert lg.xray_get_ports("user1") == []


def test_xray_get_ports_missing_clients(monkeypatch):
    cfg = {
        "inbounds": [
            {
                "protocol": "vless",
                "port": 443,
                "settings": {},
            }
        ]
    }
    monkeypatch.setattr(lg, "load_xray_config", lambda: cfg)

    assert lg.xray_get_ports("user1") == []


def test_xray_get_ports_exception(monkeypatch):
    monkeypatch.setattr(lg, "load_xray_config", lambda: 1 / 0)

    assert lg.xray_get_ports("user1") == []


def test_xray_get_sni_by_port_exception(monkeypatch):
    monkeypatch.setattr(lg, "load_xray_config", lambda: 1 / 0)

    assert lg.xray_get_sni_by_port() == {}


def test_xray_get_link_for_port_missing_clients(monkeypatch):
    cfg = {
        "inbounds": [
            {
                "protocol": "vless",
                "port": 443,
                "settings": {},
                "streamSettings": {
                    "realitySettings": {
                        "serverNames": ["test.com"],
                        "privateKey": "pk",
                        "shortIds": ["id"],
                    }
                },
            }
        ]
    }
    monkeypatch.setattr(lg, "load_xray_config", lambda: cfg)
    monkeypatch.setattr(lg, "_get_reality_public_key", lambda pk: "pub")

    assert lg.xray_get_link_for_port("user1", 443) == ""


def test_xray_get_link_for_port_missing_sni(monkeypatch):
    cfg = {
        "inbounds": [
            {
                "protocol": "vless",
                "port": 443,
                "settings": {"clients": [{"id": "uuid", "email": "user1"}]},
                "streamSettings": {
                    "realitySettings": {
                        "serverNames": [],
                        "privateKey": "pk",
                        "shortIds": ["id"],
                    }
                },
            }
        ]
    }
    monkeypatch.setattr(lg, "load_xray_config", lambda: cfg)
    monkeypatch.setattr(lg, "_get_reality_public_key", lambda pk: "pub")

    assert lg.xray_get_link_for_port("user1", 443) == ""


def test_xray_get_link_for_port_exception(monkeypatch):
    monkeypatch.setattr(lg, "load_xray_config", lambda: 1 / 0)

    assert lg.xray_get_link_for_port("user1", 443) == ""


def test_xray_get_link_for_port_missing_user_in_inbound(monkeypatch):
    cfg = {
        "inbounds": [
            {
                "protocol": "vless",
                "port": 443,
                "settings": {"clients": [{"id": "uuid", "email": "other_user"}]},
                "streamSettings": {
                    "realitySettings": {
                        "serverNames": ["test.com"],
                        "privateKey": "pk",
                        "shortIds": ["id"],
                    }
                },
            }
        ]
    }
    monkeypatch.setattr(lg, "load_xray_config", lambda: cfg)
    monkeypatch.setattr(lg, "_get_reality_public_key", lambda pk: "pub")

    assert lg.xray_get_link_for_port("user1", 443) == ""
