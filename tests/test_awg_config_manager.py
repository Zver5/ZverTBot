import os
import stat

from services.awg import config_manager


def test_save_and_load_awg_config(tmp_path, monkeypatch):
    conf = tmp_path / "awg0.conf"

    monkeypatch.setattr(config_manager, "AWG_CONF", conf)

    content = """
[Interface]
PrivateKey = testkey
Address = 10.66.66.1/24
"""

    config_manager.save_awg_config(content)

    assert conf.exists()
    assert config_manager.load_awg_config() == content


def test_add_peer_to_config(tmp_path, monkeypatch):
    conf = tmp_path / "awg0.conf"

    monkeypatch.setattr(config_manager, "AWG_CONF", conf)

    conf.write_text("[Interface]\nPrivateKey=test\n", encoding="utf-8")

    config_manager.add_peer_to_config("testuser", "PUBLIC_KEY_TEST", "10.66.66.10")

    text = conf.read_text(encoding="utf-8")

    assert "# Name: testuser" in text
    assert "[Peer]" in text
    assert "PublicKey = PUBLIC_KEY_TEST" in text
    assert "AllowedIPs = 10.66.66.10/32" in text


def test_remove_peer_from_config(tmp_path, monkeypatch):
    conf = tmp_path / "awg0.conf"

    monkeypatch.setattr(config_manager, "AWG_CONF", conf)

    conf.write_text(
        """
[Interface]
PrivateKey=test

# Name: user1
[Peer]
PublicKey = PUB123
AllowedIPs = 10.66.66.10/32

# Name: user2
[Peer]
PublicKey = PUB456
AllowedIPs = 10.66.66.11/32
""",
        encoding="utf-8",
    )

    result = config_manager.remove_peer_from_config("PUB123")

    assert result is True

    text = conf.read_text(encoding="utf-8")

    assert "PUB123" not in text
    assert "user1" not in text
    assert "PUB456" in text


def test_remove_missing_peer_returns_false(tmp_path, monkeypatch):
    conf = tmp_path / "awg0.conf"

    monkeypatch.setattr(config_manager, "AWG_CONF", conf)

    conf.write_text("# empty\n", encoding="utf-8")

    result = config_manager.remove_peer_from_config("UNKNOWN")

    assert result is False


def test_rename_peer_in_config(tmp_path, monkeypatch):
    conf = tmp_path / "awg0.conf"

    monkeypatch.setattr(config_manager, "AWG_CONF", conf)

    conf.write_text(
        """
# Name: oldname
[Peer]
PublicKey = PUB
AllowedIPs = 10.66.66.10/32
""",
        encoding="utf-8",
    )

    result = config_manager.rename_peer_in_config("oldname", "newname")

    assert result is True

    text = conf.read_text(encoding="utf-8")

    assert "# Name: newname" in text
    assert "oldname" not in text


def test_rename_peer_does_not_match_name_prefix(tmp_path, monkeypatch):
    conf = tmp_path / "awg0.conf"

    monkeypatch.setattr(config_manager, "AWG_CONF", conf)

    conf.write_text(
        "# Name: old\n"
        "[Peer]\n"
        "PublicKey = PUB1\n"
        "AllowedIPs = 10.66.66.10/32\n"
        "\n"
        "# Name: old2\n"
        "[Peer]\n"
        "PublicKey = PUB2\n"
        "AllowedIPs = 10.66.66.11/32\n",
        encoding="utf-8",
    )

    result = config_manager.rename_peer_in_config("old", "new")

    assert result is True

    text = conf.read_text(encoding="utf-8")

    assert "# Name: new\n" in text
    assert "# Name: old2\n" in text
    assert "# Name: new2" not in text


def test_rename_missing_peer_returns_false(tmp_path, monkeypatch):
    conf = tmp_path / "awg0.conf"

    monkeypatch.setattr(config_manager, "AWG_CONF", conf)

    conf.write_text("# Name: user\n", encoding="utf-8")

    result = config_manager.rename_peer_in_config("unknown", "new")

    assert result is False


def test_awg_save_config_preserves_permissions(tmp_path, monkeypatch):
    conf = tmp_path / "awg0.conf"

    conf.write_text("[Interface]\nPrivateKey=test\n", encoding="utf-8")

    os.chmod(conf, 0o600)

    monkeypatch.setattr(config_manager, "AWG_CONF", conf)

    config_manager.save_awg_config("[Interface]\nPrivateKey=new\n")

    assert conf.read_text(encoding="utf-8") == "[Interface]\nPrivateKey=new\n"

    mode = stat.S_IMODE(conf.stat().st_mode)

    assert mode == 0o600


def test_awg_add_peer_preserves_permissions(tmp_path, monkeypatch):
    conf = tmp_path / "awg0.conf"

    conf.write_text("[Interface]\nPrivateKey=test\n", encoding="utf-8")

    os.chmod(conf, 0o600)

    monkeypatch.setattr(config_manager, "AWG_CONF", conf)

    config_manager.add_peer_to_config("user1", "PUBLICKEY123", "10.66.66.10")

    text = conf.read_text(encoding="utf-8")

    assert "# Name: user1" in text
    assert "PublicKey = PUBLICKEY123" in text

    mode = stat.S_IMODE(conf.stat().st_mode)

    assert mode == 0o600


from unittest.mock import patch


def test_remove_peer_from_config_exception(monkeypatch, tmp_path):
    conf = tmp_path / "awg0.conf"
    monkeypatch.setattr(config_manager, "AWG_CONF", conf)

    with patch("builtins.open", side_effect=PermissionError("Mocked error")):
        result = config_manager.remove_peer_from_config("PUB")
        assert result is False


def test_rename_peer_in_config_exception(monkeypatch, tmp_path):
    conf = tmp_path / "awg0.conf"
    monkeypatch.setattr(config_manager, "AWG_CONF", conf)

    with patch("builtins.open", side_effect=PermissionError("Mocked error")):
        result = config_manager.rename_peer_in_config("old", "new")
        assert result is False
