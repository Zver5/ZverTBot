"""
Тесты services/xray/client_manager.py
"""

from unittest.mock import Mock

import pytest

import services.xray.client_manager as cm


@pytest.fixture(autouse=True)
def allow_awg_username(monkeypatch):
    monkeypatch.setattr(
        cm,
        "is_username_unique_awg",
        lambda username: True,
    )


# ==========================================================
# reload_xray
# ==========================================================


def test_reload_xray_calls_restart(monkeypatch):
    called = []

    monkeypatch.setattr(cm, "restart_service", lambda name: called.append(name))

    cm.reload_xray()

    assert called == ["xray"]


# ==========================================================
# validate_xray_config
# ==========================================================


def test_validate_xray_config_success(monkeypatch):
    monkeypatch.setattr(
        cm.subprocess, "run", lambda *args, **kwargs: Mock(returncode=0, stderr="")
    )

    assert cm.validate_xray_config() is True


def test_validate_xray_config_failed(monkeypatch):
    monkeypatch.setattr(
        cm.subprocess,
        "run",
        lambda *args, **kwargs: Mock(returncode=1, stderr="bad config"),
    )

    assert cm.validate_xray_config() is False


def test_validate_xray_config_exception(monkeypatch):
    def fail(*args, **kwargs):
        raise Exception("xray missing")

    monkeypatch.setattr(cm.subprocess, "run", fail)

    assert cm.validate_xray_config() is False


# ==========================================================
# xray_add_user
# ==========================================================


def test_xray_add_user_invalid_name(monkeypatch):
    monkeypatch.setattr(cm, "validate_username", lambda x: False)

    ok, msg = cm.xray_add_user("bad name")

    assert ok is False
    assert "Только латиница" in msg


def test_xray_add_user_duplicate(monkeypatch):
    monkeypatch.setattr(cm, "validate_username", lambda x: True)

    monkeypatch.setattr(cm, "load_xray_config", dict)

    monkeypatch.setattr(cm, "is_username_unique_vless", lambda x: False)

    ok, msg = cm.xray_add_user("user")

    assert ok is False
    assert "Уже существует" in msg


def test_xray_add_user_no_inbound(monkeypatch):
    monkeypatch.setattr(cm, "validate_username", lambda x: True)

    monkeypatch.setattr(cm, "load_xray_config", dict)

    monkeypatch.setattr(cm, "is_username_unique_vless", lambda x: True)

    monkeypatch.setattr(
        cm.subprocess, "run", lambda *args, **kwargs: Mock(stdout="uuid-test")
    )

    monkeypatch.setattr(cm, "add_client_to_all_inbounds", lambda *args: 0)

    ok, msg = cm.xray_add_user("user")

    assert ok is False
    assert "VLESS inbound" in msg


def test_xray_add_user_success(monkeypatch):
    config = {"inbounds": []}

    saved = []

    monkeypatch.setattr(cm, "validate_username", lambda x: True)

    monkeypatch.setattr(cm, "load_xray_config", lambda: config)

    monkeypatch.setattr(cm, "is_username_unique_vless", lambda x: True)

    monkeypatch.setattr(
        cm.subprocess, "run", lambda *args, **kwargs: Mock(stdout="uuid-test")
    )

    monkeypatch.setattr(cm, "add_client_to_all_inbounds", lambda *args: 1)

    monkeypatch.setattr(cm, "save_xray_config", lambda cfg: saved.append(cfg))

    monkeypatch.setattr(cm, "validate_xray_config", lambda: True)

    monkeypatch.setattr(cm, "reload_xray", lambda: None)

    ok, uuid = cm.xray_add_user("user")

    assert ok is True
    assert uuid == "uuid-test"
    assert saved


def test_xray_add_user_bad_config(monkeypatch):
    monkeypatch.setattr(cm, "validate_username", lambda x: True)

    monkeypatch.setattr(cm, "load_xray_config", dict)

    monkeypatch.setattr(cm, "is_username_unique_vless", lambda x: True)

    monkeypatch.setattr(
        cm.subprocess, "run", lambda *args, **kwargs: Mock(stdout="uuid-test")
    )

    monkeypatch.setattr(cm, "add_client_to_all_inbounds", lambda *args: 1)

    monkeypatch.setattr(cm, "save_xray_config", lambda cfg: None)

    # save_xray_config теперь сам валидирует candidate-конфиг
    # до замены рабочего config.
    monkeypatch.setattr(
        cm,
        "save_xray_config",
        lambda cfg: (_ for _ in ()).throw(ValueError("Конфиг Xray не прошёл проверку")),
    )

    ok, msg = cm.xray_add_user("user")

    assert ok is False
    assert "не прошёл проверку" in msg


def test_xray_add_user_xray_not_installed(monkeypatch):
    monkeypatch.setattr(cm.shutil, "which", lambda name: None)

    ok, msg = cm.xray_add_user("user")

    assert ok is False
    assert msg == "❌ Xray не установлен"


def test_xray_add_user_config_missing(monkeypatch):
    monkeypatch.setattr(cm.shutil, "which", lambda name: "/usr/bin/xray")

    class MissingConfig:
        def is_file(self):
            return False

        def __str__(self):
            return "/etc/xray/config.json"

    monkeypatch.setattr(cm, "XRAY_CONF", MissingConfig())

    ok, msg = cm.xray_add_user("user")

    assert ok is False
    assert msg == "❌ Путь Xray не найден: /etc/xray/config.json"


def test_xray_add_user_uuid_command(monkeypatch):
    config = {"inbounds": []}
    calls = []
    saved = []

    monkeypatch.setattr(cm.shutil, "which", lambda name: "/usr/bin/xray")

    class ExistingConfig:
        def is_file(self):
            return True

        def __str__(self):
            return "/etc/xray/config.json"

    monkeypatch.setattr(cm, "XRAY_CONF", ExistingConfig())

    monkeypatch.setattr(cm, "validate_username", lambda username: True)
    monkeypatch.setattr(cm, "load_xray_config", lambda: config)
    monkeypatch.setattr(
        cm,
        "is_username_unique_vless",
        lambda username: True,
    )

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return Mock(stdout="uuid-test\n")

    monkeypatch.setattr(cm.subprocess, "run", fake_run)
    monkeypatch.setattr(
        cm,
        "add_client_to_all_inbounds",
        lambda cfg, username, uuid: 1,
    )
    monkeypatch.setattr(
        cm,
        "save_xray_config",
        lambda cfg: saved.append(cfg),
    )
    monkeypatch.setattr(cm, "validate_xray_config", lambda: True)

    reloaded = []
    monkeypatch.setattr(
        cm,
        "reload_xray",
        lambda: reloaded.append(True),
    )

    ok, uuid = cm.xray_add_user("user")

    assert ok is True
    assert uuid == "uuid-test"
    assert calls == [
        (
            ["xray", "uuid"],
            {
                "capture_output": True,
                "text": True,
                "check": True,
            },
        )
    ]
    assert saved == [config]
    assert reloaded == [True]


def test_xray_add_user_exception_returns_error(monkeypatch):
    monkeypatch.setattr(cm.shutil, "which", lambda name: "/usr/bin/xray")

    class ExistingConfig:
        def is_file(self):
            return True

        def __str__(self):
            return "/etc/xray/config.json"

    monkeypatch.setattr(cm, "XRAY_CONF", ExistingConfig())

    monkeypatch.setattr(
        cm,
        "validate_username",
        lambda username: True,
    )
    monkeypatch.setattr(
        cm,
        "load_xray_config",
        lambda: (_ for _ in ()).throw(RuntimeError("load failed")),
    )

    logged = []
    monkeypatch.setattr(
        cm.logger,
        "error",
        lambda message, *args: logged.append((message, args)),
    )

    ok, msg = cm.xray_add_user("user")

    assert ok is False
    assert msg == "❌ Ошибка Xray: load failed"
    assert len(logged) == 1
    assert logged[0][0] == "xray.client.add_failed | username=%s | error=%s"
    assert logged[0][1][0] == "user"
    assert str(logged[0][1][1]) == "load failed"


def test_xray_add_user_duplicate_in_awg(monkeypatch):
    monkeypatch.setattr(
        cm,
        "validate_username",
        lambda username: True,
    )
    monkeypatch.setattr(
        cm,
        "load_xray_config",
        dict,
    )
    monkeypatch.setattr(
        cm,
        "is_username_unique_vless",
        lambda username: True,
    )
    monkeypatch.setattr(
        cm,
        "is_username_unique_awg",
        lambda username: False,
    )

    ok, msg = cm.xray_add_user("user")

    assert ok is False
    assert "Уже существует" in msg
