import subprocess

import scripts.migrate_xray_telemetry as migration


def test_migrate_updates_config_and_restarts(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"old": true}')

    monkeypatch.setattr(migration, "XRAY_CONF", config_path)
    monkeypatch.setattr(migration.shutil, "which", lambda _: "/usr/local/bin/xray")
    monkeypatch.setattr(migration, "load_xray_config", lambda: {"old": True})
    monkeypatch.setattr(migration, "get_xray_readiness", lambda _: (True, []))
    monkeypatch.setattr(migration, "normalize_xray_api_config", lambda _: {"new": True})
    monkeypatch.setattr(migration, "create_backup", lambda: "backup.json")

    saved = []
    monkeypatch.setattr(
        migration,
        "save_xray_config",
        lambda value: saved.append(value),
    )

    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(migration.subprocess, "run", fake_run)

    assert migration.migrate() is True
    assert saved == [{"new": True}]
    assert calls == [
        ["systemctl", "is-active", "--quiet", "xray.service"],
        ["systemctl", "restart", "xray.service"],
    ]


def test_migrate_skips_template_and_defers_restart(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}")

    monkeypatch.setattr(migration, "XRAY_CONF", config_path)
    monkeypatch.setattr(migration.shutil, "which", lambda _: "/usr/local/bin/xray")
    monkeypatch.setattr(migration, "load_xray_config", lambda: {})
    monkeypatch.setattr(
        migration,
        "get_xray_readiness",
        lambda _: (False, ["privateKey is missing"]),
    )

    calls = []
    monkeypatch.setattr(
        migration.subprocess,
        "run",
        lambda *args, **kwargs: calls.append(args),
    )

    assert migration.migrate(restart_requested=True) is False
    assert calls == []


def test_migrate_does_not_restart_when_save_fails(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"old": true}')

    monkeypatch.setattr(migration, "XRAY_CONF", config_path)
    monkeypatch.setattr(migration.shutil, "which", lambda _: "/usr/local/bin/xray")
    monkeypatch.setattr(migration, "load_xray_config", lambda: {"old": True})
    monkeypatch.setattr(migration, "get_xray_readiness", lambda _: (True, []))
    monkeypatch.setattr(migration, "normalize_xray_api_config", lambda _: {"new": True})
    monkeypatch.setattr(migration, "create_backup", lambda: "backup.json")
    monkeypatch.setattr(
        migration,
        "save_xray_config",
        lambda _: (_ for _ in ()).throw(ValueError("validation failed")),
    )

    calls = []
    monkeypatch.setattr(
        migration.subprocess,
        "run",
        lambda *args, **kwargs: calls.append(args),
    )

    try:
        migration.migrate()
    except ValueError as exc:
        assert "validation failed" in str(exc)
    else:
        raise AssertionError("Expected validation failure")

    assert calls == []


def test_migrate_is_idempotent(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}")

    config = {"already": "normalized"}

    monkeypatch.setattr(migration, "XRAY_CONF", config_path)
    monkeypatch.setattr(migration.shutil, "which", lambda _: "/usr/local/bin/xray")
    monkeypatch.setattr(migration, "load_xray_config", lambda: config)
    monkeypatch.setattr(migration, "get_xray_readiness", lambda _: (True, []))
    monkeypatch.setattr(migration, "normalize_xray_api_config", lambda _: config)

    calls = []
    monkeypatch.setattr(
        migration.subprocess,
        "run",
        lambda *args, **kwargs: calls.append(args),
    )

    assert migration.migrate() is False
    assert calls == []


def test_migrate_skips_when_xray_binary_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(migration, "XRAY_CONF", tmp_path / "missing.json")
    monkeypatch.setattr(migration.shutil, "which", lambda _: None)

    assert migration.migrate(restart_requested=True) is False
