from services import vpn_config_status as status_module


def test_initial_setup_checks_protocols_independently(monkeypatch, tmp_path):
    xray = tmp_path / "xray.json"
    awg = tmp_path / "awg0.conf"
    xray.write_text("broken", encoding="utf-8")

    monkeypatch.setattr(status_module, "XRAY_CONF", xray)
    monkeypatch.setattr(status_module, "AWG_CONF", awg)
    monkeypatch.setattr(
        status_module,
        "get_vpn_config_status",
        lambda: {
            "xray": status_module.VpnConfigStatus("xray", True, False),
            "awg": status_module.VpnConfigStatus("awg", True, False),
        },
    )

    assert status_module.get_initial_setup_protocols() == ["awg"]


def test_initial_setup_ignores_existing_working_or_broken_configs(
    monkeypatch, tmp_path
):
    xray = tmp_path / "xray.json"
    awg = tmp_path / "awg0.conf"
    xray.write_text("broken", encoding="utf-8")
    awg.write_text("broken", encoding="utf-8")

    monkeypatch.setattr(status_module, "XRAY_CONF", xray)
    monkeypatch.setattr(status_module, "AWG_CONF", awg)
    monkeypatch.setattr(
        status_module,
        "get_vpn_config_status",
        lambda: {
            "xray": status_module.VpnConfigStatus("xray", True, False),
            "awg": status_module.VpnConfigStatus("awg", True, True),
        },
    )

    assert status_module.get_initial_setup_protocols() == []


def test_initial_setup_ignores_uninstalled_protocols(monkeypatch, tmp_path):
    monkeypatch.setattr(status_module, "XRAY_CONF", tmp_path / "xray.json")
    monkeypatch.setattr(status_module, "AWG_CONF", tmp_path / "awg0.conf")
    monkeypatch.setattr(
        status_module,
        "get_vpn_config_status",
        lambda: {
            "xray": status_module.VpnConfigStatus("xray", False, False),
            "awg": status_module.VpnConfigStatus("awg", False, False),
        },
    )

    assert status_module.get_initial_setup_protocols() == []


def test_initial_setup_treats_broken_symlink_as_existing(
    monkeypatch, tmp_path
):
    xray = tmp_path / "xray.json"
    xray.symlink_to(tmp_path / "missing-target.json")

    monkeypatch.setattr(status_module, "XRAY_CONF", xray)
    monkeypatch.setattr(status_module, "AWG_CONF", tmp_path / "awg0.conf")
    monkeypatch.setattr(
        status_module,
        "get_vpn_config_status",
        lambda: {
            "xray": status_module.VpnConfigStatus("xray", True, False),
            "awg": status_module.VpnConfigStatus("awg", True, False),
        },
    )

    assert status_module.get_initial_setup_protocols() == ["awg"]
