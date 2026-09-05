from pathlib import Path


def test_ssh_keys_file_missing(monkeypatch):
    from services import ssh_keys

    fake = Path("/tmp/nonexistent_authorized_keys")

    monkeypatch.setattr(ssh_keys, "SSH_AUTHORIZED_KEYS", fake)

    result = ssh_keys.get_ssh_keys_list()

    assert "authorized_keys не найден" in result


def test_ssh_keys_empty_file(monkeypatch, tmp_path):
    from services import ssh_keys

    auth = tmp_path / "authorized_keys"
    auth.write_text("")

    monkeypatch.setattr(ssh_keys, "SSH_AUTHORIZED_KEYS", auth)

    result = ssh_keys.get_ssh_keys_list()

    assert "SSH-ключи не найдены" in result


def test_ssh_keys_one_key(monkeypatch, tmp_path):
    from services import ssh_keys

    auth = tmp_path / "authorized_keys"

    auth.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestKey123 PC_Test\n")

    monkeypatch.setattr(ssh_keys, "SSH_AUTHORIZED_KEYS", auth)

    class FakeResult:
        returncode = 0
        stdout = (
            "256 SHA256:testfingerprint123456789012345678901234567890 "
            "PC_Test (ED25519)\n"
        )
        stderr = ""

    monkeypatch.setattr(
        ssh_keys.subprocess, "run", lambda *args, **kwargs: FakeResult()
    )

    result = ssh_keys.get_ssh_keys_list()

    assert "SSH-ключи" in result


def test_delete_ssh_key(monkeypatch, tmp_path):
    from services import ssh_keys

    auth = tmp_path / "authorized_keys"

    auth.write_text("ssh-ed25519 AAAA KEY_ONE\nssh-ed25519 BBBB KEY_TWO\n")

    monkeypatch.setattr(ssh_keys, "SSH_AUTHORIZED_KEYS", auth)

    ok, result = ssh_keys.delete_ssh_key("KEY_ONE")

    assert ok is True
    assert "удалён" in result

    data = auth.read_text()

    assert "KEY_ONE" not in data
    assert "KEY_TWO" in data


def test_ssh_keys_with_broken_lines(monkeypatch, tmp_path):
    from services import ssh_keys

    auth = tmp_path / "authorized_keys"

    auth.write_text("broken line\nanother broken line\n")

    monkeypatch.setattr(ssh_keys, "SSH_AUTHORIZED_KEYS", auth)

    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(
        ssh_keys.subprocess, "run", lambda *args, **kwargs: FakeResult()
    )

    result = ssh_keys.get_ssh_keys_list()

    assert "SSH-ключи не найдены" in result


def test_delete_last_ssh_key(monkeypatch, tmp_path):
    from services import ssh_keys

    auth = tmp_path / "authorized_keys"

    auth.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILASTTESTKEY LAST_KEY\n")

    monkeypatch.setattr(ssh_keys, "SSH_AUTHORIZED_KEYS", auth)

    ok, result = ssh_keys.delete_ssh_key("LAST_KEY")

    assert ok is True
    assert "удалён" in result

    assert auth.read_text() == ""

    # Проверяем что пустой файл теперь нормально обрабатывается
    result = ssh_keys.get_ssh_keys_list()

    assert "SSH-ключи не найдены" in result
