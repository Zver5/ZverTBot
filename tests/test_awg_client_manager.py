import pytest


@pytest.fixture(autouse=True)
def allow_vless_username(monkeypatch):
    from services.awg import client_manager as cm

    monkeypatch.setattr(cm, "is_username_unique_vless", lambda username: True)


def test_awg_add_user_success(monkeypatch):
    from services.awg import client_manager as cm

    registry = {}

    monkeypatch.setattr(cm, "is_username_unique_awg", lambda username: True)

    def fake_run(*args, **kwargs):
        class Result:
            stdout = "KEY123\n"

        return Result()

    monkeypatch.setattr(cm.subprocess, "run", fake_run)

    monkeypatch.setattr(cm, "find_free_awg_ip", lambda: "10.66.66.10")

    monkeypatch.setattr(cm, "load_awg_registry", lambda: registry)

    monkeypatch.setattr(cm, "save_awg_registry", lambda data: registry.update(data))

    monkeypatch.setattr(cm, "add_peer_to_config", lambda *args: None)

    ok, result = cm.awg_add_user("testuser")

    assert ok is True
    assert result == "10.66.66.10"
    assert "testuser" in registry
    assert registry["testuser"]["ip"] == "10.66.66.10"


def test_awg_add_user_runtime_failure_rolls_back_registry(monkeypatch):
    from services.awg import client_manager as cm

    registry = {}

    monkeypatch.setattr(cm, "is_username_unique_awg", lambda username: True)

    monkeypatch.setattr(cm, "find_free_awg_ip", lambda: "10.66.66.10")

    monkeypatch.setattr(cm, "load_awg_registry", lambda: registry)

    monkeypatch.setattr(cm, "save_awg_registry", lambda data: registry.update(data))

    class Result:
        stdout = "KEY123\\n"
        returncode = 1
        stderr = "runtime failure"

    monkeypatch.setattr(cm.subprocess, "run", lambda *args, **kwargs: Result())

    ok, result = cm.awg_add_user("testuser")

    assert ok is False
    assert "Ошибка AWG runtime" in result
    assert "testuser" not in registry


def test_awg_add_user_config_failure_does_not_leave_partial_state(monkeypatch):
    from services.awg import client_manager as cm

    registry = {}

    monkeypatch.setattr(
        cm,
        "is_username_unique_awg",
        lambda username: True,
    )

    monkeypatch.setattr(
        cm,
        "find_free_awg_ip",
        lambda: "10.66.66.10",
    )

    monkeypatch.setattr(
        cm,
        "load_awg_registry",
        lambda: registry,
    )

    monkeypatch.setattr(
        cm,
        "save_awg_registry",
        lambda data: registry.update(data),
    )

    calls = []

    class Result:
        stdout = "KEY123\\n"
        returncode = 0
        stderr = ""

    def fake_run(*args, **kwargs):
        calls.append(args[0])
        return Result()

    monkeypatch.setattr(
        cm.subprocess,
        "run",
        fake_run,
    )

    def fail_add_peer(*args):
        raise RuntimeError("config write failure")

    monkeypatch.setattr(
        cm,
        "add_peer_to_config",
        fail_add_peer,
    )

    ok, result = cm.awg_add_user("testuser")

    assert ok is False
    assert "Ошибка AWG" in result
    assert "testuser" not in registry
    assert calls[-1] == [
        "awg",
        "set",
        "awg0",
        "peer",
        "KEY123\\n",
        "remove",
    ]


def test_awg_add_user_duplicate(monkeypatch):
    from services.awg import client_manager as cm

    monkeypatch.setattr(cm, "is_username_unique_awg", lambda username: False)

    ok, result = cm.awg_add_user("testuser")

    assert ok is False
    assert "Уже существует" in result


def test_awg_add_user_without_free_ip(monkeypatch):
    from services.awg import client_manager as cm

    monkeypatch.setattr(cm, "is_username_unique_awg", lambda username: True)

    monkeypatch.setattr(cm, "find_free_awg_ip", lambda: None)

    def fake_run(*args, **kwargs):
        class Result:
            stdout = "KEY\n"

        return Result()

    monkeypatch.setattr(cm.subprocess, "run", fake_run)

    ok, result = cm.awg_add_user("testuser")

    assert ok is False
    assert "Нет свободных IP" in result


def test_awg_del_user_success(monkeypatch):
    from services.awg import client_manager as cm

    registry = {"user1": {"pubkey": "PUB123", "ip": "10.66.66.10"}}

    monkeypatch.setattr(cm, "load_awg_registry", lambda: registry)

    monkeypatch.setattr(cm, "save_awg_registry", lambda data: registry.update(data))

    monkeypatch.setattr(cm.subprocess, "run", lambda *args, **kwargs: None)

    monkeypatch.setattr(cm, "remove_peer_from_config", lambda pub: True)

    ok, result = cm.awg_del_user("user1")

    assert ok is True
    assert result == "Удалён"


def test_awg_del_user_runtime_failure_keeps_registry(monkeypatch):
    from services.awg import client_manager as cm

    registry = {
        "user1": {
            "pubkey": "PUB123",
            "ip": "10.66.66.10",
        }
    }

    monkeypatch.setattr(
        cm,
        "load_awg_registry",
        lambda: registry,
    )

    monkeypatch.setattr(
        cm,
        "save_awg_registry",
        lambda data: registry.update(data),
    )

    class Result:
        returncode = 1
        stderr = "runtime delete failure"

    monkeypatch.setattr(
        cm.subprocess,
        "run",
        lambda *args, **kwargs: Result(),
    )

    ok, result = cm.awg_del_user("user1")

    assert ok is False
    assert "Ошибка AWG runtime" in result
    assert "user1" in registry
    assert registry["user1"]["pubkey"] == "PUB123"


def test_awg_del_user_config_failure_keeps_registry(monkeypatch):
    from services.awg import client_manager as cm

    registry = {
        "user1": {
            "pubkey": "PUB123",
            "ip": "10.66.66.10",
        }
    }

    monkeypatch.setattr(
        cm,
        "load_awg_registry",
        lambda: registry,
    )

    monkeypatch.setattr(
        cm,
        "save_awg_registry",
        lambda data: registry.update(data),
    )

    class Result:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(
        cm.subprocess,
        "run",
        lambda *args, **kwargs: Result(),
    )

    monkeypatch.setattr(
        cm,
        "remove_peer_from_config",
        lambda pub: False,
    )

    ok, result = cm.awg_del_user("user1")

    assert ok is False
    assert "awg0.conf" in result
    assert "user1" in registry
    assert registry["user1"]["pubkey"] == "PUB123"


def test_awg_del_user_config_failure_restores_runtime_peer(monkeypatch):
    from services.awg import client_manager as cm

    registry = {
        "user1": {
            "pubkey": "PUB123",
            "ip": "10.66.66.10",
        }
    }
    calls = []

    monkeypatch.setattr(cm, "load_awg_registry", lambda: registry)
    monkeypatch.setattr(
        cm,
        "save_awg_registry",
        lambda data: registry.update(data),
    )

    class Result:
        returncode = 0
        stderr = ""

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return Result()

    monkeypatch.setattr(cm.subprocess, "run", fake_run)
    monkeypatch.setattr(cm, "remove_peer_from_config", lambda pub: False)

    ok, result = cm.awg_del_user("user1")

    assert ok is False
    assert "awg0.conf" in result
    assert calls == [
        ["awg", "set", "awg0", "peer", "PUB123", "remove"],
        ["awg", "set", "awg0", "peer", "PUB123", "allowed-ips", "10.66.66.10/32"],
    ]


def test_awg_del_user_logs_failed_runtime_rollback(monkeypatch):
    from services.awg import client_manager as cm

    registry = {
        "user1": {
            "pubkey": "PUB123",
            "ip": "10.66.66.10",
        }
    }
    commands = []
    errors = []

    monkeypatch.setattr(cm, "load_awg_registry", lambda: registry)
    monkeypatch.setattr(cm, "save_awg_registry", lambda data: registry.update(data))
    monkeypatch.setattr(cm, "remove_peer_from_config", lambda pub: False)

    class Result:
        def __init__(self, returncode, stderr=""):
            self.returncode = returncode
            self.stderr = stderr

    def fake_run(cmd, *args, **kwargs):
        commands.append(cmd)
        if "remove" in cmd:
            return Result(0)
        return Result(1, "rollback failed")

    monkeypatch.setattr(cm.subprocess, "run", fake_run)
    monkeypatch.setattr(
        cm.logger,
        "error",
        lambda message, *args: errors.append((message, args)),
    )

    ok, result = cm.awg_del_user("user1")

    assert ok is False
    assert "awg0.conf" in result
    assert commands[0][-1] == "remove"
    assert commands[1][-1] == "10.66.66.10/32"
    assert errors
    assert any(
        message == "awg.config.delete_failed | username=%s | reason=%s"
        and args == ("user1", "peer_not_removed")
        for message, args in errors
    )
    assert any(
        message == "awg.runtime.rollback_failed | username=%s | error=%s"
        and args == ("user1", "rollback failed")
        for message, args in errors
    )


def test_awg_del_user_missing(monkeypatch):
    from services.awg import client_manager as cm

    monkeypatch.setattr(cm, "load_awg_registry", dict)

    ok, result = cm.awg_del_user("unknown")

    assert ok is False
    assert "Не найден" in result


def test_awg_del_user_without_pubkey(monkeypatch):
    from services.awg import client_manager as cm

    monkeypatch.setattr(cm, "load_awg_registry", lambda: {"user": {}})

    ok, result = cm.awg_del_user("user")

    assert ok is False
    assert "Нет PublicKey" in result


def test_awg_add_user_awg_not_installed(monkeypatch):
    from services.awg import client_manager as cm

    monkeypatch.setattr(cm, "is_username_unique_awg", lambda u: True)
    monkeypatch.setattr(cm.shutil, "which", lambda cmd: None)

    ok, msg = cm.awg_add_user("test_user")

    assert ok is False
    assert "AWG не установлен" in msg


def test_awg_add_user_conf_not_found(monkeypatch, tmp_path):
    from services.awg import client_manager as cm

    monkeypatch.setattr(cm, "is_username_unique_awg", lambda u: True)
    monkeypatch.setattr(cm.shutil, "which", lambda cmd: "/usr/bin/awg")
    monkeypatch.setattr(cm, "AWG_CONF", tmp_path / "nonexistent.conf")

    ok, msg = cm.awg_add_user("test_user")

    assert ok is False
    assert "Путь AWG не найден" in msg


def test_awg_add_user_config_failure_rollback_fails(monkeypatch, tmp_path):
    from unittest.mock import Mock

    from services.awg import client_manager as cm

    # Создаем временный файл конфига
    conf_file = tmp_path / "awg0.conf"
    conf_file.write_text("# test config")

    monkeypatch.setattr(cm, "is_username_unique_awg", lambda u: True)
    monkeypatch.setattr(cm.shutil, "which", lambda cmd: "/usr/bin/awg")
    monkeypatch.setattr(cm, "AWG_CONF", conf_file)

    call_count = {"genkey": 0, "pubkey": 0, "set": 0, "rollback": 0}

    def fake_run(cmd, *args, **kwargs):
        result = Mock()
        if cmd == ["awg", "genkey"]:
            call_count["genkey"] += 1
            result.stdout = "private_key"
            result.returncode = 0
        elif cmd == ["awg", "pubkey"]:
            call_count["pubkey"] += 1
            result.stdout = "public_key"
            result.returncode = 0
        elif (
            cmd[:3] == ["awg", "set", "awg0"] and "peer" in cmd and "remove" not in cmd
        ):
            call_count["set"] += 1
            result.returncode = 0
        elif cmd[:3] == ["awg", "set", "awg0"] and "remove" in cmd:
            call_count["rollback"] += 1
            result.returncode = 1
            result.stderr = "rollback failed"
        return result

    monkeypatch.setattr(cm.subprocess, "run", fake_run)
    monkeypatch.setattr(cm, "find_free_awg_ip", lambda: "10.66.66.10")
    monkeypatch.setattr(cm, "load_awg_registry", lambda: {})
    monkeypatch.setattr(cm, "save_awg_registry", lambda r: None)
    monkeypatch.setattr(
        cm,
        "add_peer_to_config",
        lambda u, p, i: (_ for _ in ()).throw(Exception("config add failed")),
    )

    ok, msg = cm.awg_add_user("test_user")

    assert ok is False
    assert "Ошибка AWG" in msg
    assert call_count["rollback"] == 1


def test_awg_add_user_unexpected_exception(monkeypatch, tmp_path):
    from unittest.mock import Mock

    from services.awg import client_manager as cm

    # Создаем временный файл конфига
    conf_file = tmp_path / "awg0.conf"
    conf_file.write_text("# test config")

    monkeypatch.setattr(cm, "is_username_unique_awg", lambda u: True)
    monkeypatch.setattr(cm.shutil, "which", lambda cmd: "/usr/bin/awg")
    monkeypatch.setattr(cm, "AWG_CONF", conf_file)
    monkeypatch.setattr(
        cm.subprocess, "run", Mock(side_effect=RuntimeError("unexpected"))
    )

    ok, msg = cm.awg_add_user("test_user")

    assert ok is False
    assert "Ошибка AWG" in msg


def test_awg_del_user_unexpected_exception(monkeypatch):
    from unittest.mock import Mock

    from services.awg import client_manager as cm

    monkeypatch.setattr(
        cm, "load_awg_registry", lambda: {"test_user": {"pubkey": "pub"}}
    )
    monkeypatch.setattr(
        cm.subprocess, "run", Mock(side_effect=RuntimeError("unexpected"))
    )

    ok, msg = cm.awg_del_user("test_user")

    assert ok is False
    assert "Ошибка AWG" in msg


def test_awg_add_user_duplicate_in_vless(monkeypatch):
    from services.awg import client_manager as cm

    monkeypatch.setattr(cm, "is_username_unique_awg", lambda username: True)
    monkeypatch.setattr(cm, "is_username_unique_vless", lambda username: False)

    ok, result = cm.awg_add_user("testuser")

    assert ok is False
    assert "Уже существует" in result
