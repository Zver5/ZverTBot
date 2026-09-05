"""
Unit-тесты бизнес-логики services.ssh_keys.
"""

from pathlib import Path
from unittest.mock import Mock, patch

from services import ssh_keys


class TestGetSSHKeysList:
    def test_missing_file(self, tmp_path):
        auth = tmp_path / "missing_authorized_keys"

        with patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth):
            result = ssh_keys.get_ssh_keys_list()

        assert result == "❌ Файл authorized_keys не найден"

    def test_empty_file(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("")

        with patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth):
            result = ssh_keys.get_ssh_keys_list()

        assert "SSH-ключи не найдены" in result

    def test_ssh_keygen_error(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("ssh-ed25519 AAAA TEST\n")

        result = Mock(returncode=1, stdout="", stderr="ssh-keygen failed")

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(ssh_keys.subprocess, "run", return_value=result),
        ):
            text = ssh_keys.get_ssh_keys_list()

        assert text == "❌ Ошибка: ssh-keygen failed"

    def test_no_fingerprint_matches(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("broken line\n")

        result = Mock(
            returncode=0,
            stdout="256 invalid-fingerprint comment\n",
            stderr="",
        )

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(ssh_keys.subprocess, "run", return_value=result),
        ):
            text = ssh_keys.get_ssh_keys_list()

        assert "SSH-ключи не найдены" in text

    def test_known_ed25519_key(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("ssh-ed25519 AAAA TEST\n")

        fingerprint = "SHA256:" + "A" * 43
        result = Mock(
            returncode=0,
            stdout=f"256 {fingerprint} PC_Test (ED25519)\n",
            stderr="",
        )

        key_map = {
            fingerprint: {
                "name": "PC_Test",
                "desc": "Тестовый ключ",
                "emoji": "🔑",
            }
        }

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(ssh_keys.subprocess, "run", return_value=result),
            patch.object(ssh_keys, "SSH_KEY_MAP", key_map),
        ):
            text = ssh_keys.get_ssh_keys_list()

        assert "SSH-ключи (1)" in text
        assert "PC Test" in text
        assert "Тестовый ключ" in text
        assert "ED25519" in text

    def test_known_rsa_key(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("ssh-rsa AAAA TEST\n")

        fingerprint = "SHA256:" + "B" * 43
        result = Mock(
            returncode=0,
            stdout=f"4096 {fingerprint} PC_RSA (RSA)\n",
            stderr="",
        )

        key_map = {
            fingerprint: {
                "name": "PC_RSA",
                "desc": "RSA ключ",
                "emoji": "🔐",
            }
        }

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(ssh_keys.subprocess, "run", return_value=result),
            patch.object(ssh_keys, "SSH_KEY_MAP", key_map),
        ):
            text = ssh_keys.get_ssh_keys_list()

        assert "PC RSA" in text
        assert "RSA" in text

    def test_unknown_key_uses_comment(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("ssh-ed25519 AAAA UNKNOWN\n")

        fingerprint = "SHA256:" + "C" * 43
        result = Mock(
            returncode=0,
            stdout=f"256 {fingerprint} UnknownKey (ED25519)\n",
            stderr="",
        )

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(ssh_keys.subprocess, "run", return_value=result),
            patch.object(ssh_keys, "SSH_KEY_MAP", {}),
        ):
            text = ssh_keys.get_ssh_keys_list()

        assert "UnknownKey" in text
        assert "Неизвестный ключ" in text
        assert "ED25519" in text

    def test_unknown_type_defaults_to_ed25519(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("unknown AAAA UNKNOWN\n")

        fingerprint = "SHA256:" + "D" * 43
        result = Mock(
            returncode=0,
            stdout=f"256 {fingerprint} UnknownKey (UNKNOWN)\n",
            stderr="",
        )

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(ssh_keys.subprocess, "run", return_value=result),
            patch.object(ssh_keys, "SSH_KEY_MAP", {}),
        ):
            text = ssh_keys.get_ssh_keys_list()

        assert "ED25519" in text

    def test_exception(self, tmp_path):
        auth = tmp_path / "authorized_keys"

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(
                ssh_keys.os.path,
                "exists",
                side_effect=RuntimeError("boom"),
            ),
            patch.object(ssh_keys.logger, "error") as mock_error,
        ):
            text = ssh_keys.get_ssh_keys_list()

        assert text == "❌ Ошибка: boom"
        mock_error.assert_called_once()


class TestDeleteSSHKey:
    def test_missing_file(self, tmp_path):
        auth = tmp_path / "missing_authorized_keys"

        with patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth):
            ok, text = ssh_keys.delete_ssh_key("TEST")

        assert ok is False
        assert text == "❌ Файл authorized_keys не найден"

    def test_delete_existing_key(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("ssh-ed25519 AAAA KEY_ONE\nssh-ed25519 BBBB KEY_TWO\n")

        with patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth):
            ok, text = ssh_keys.delete_ssh_key("KEY_ONE")

        assert ok is True
        assert "удалён" in text
        assert "KEY_ONE" not in auth.read_text()
        assert "KEY_TWO" in auth.read_text()

    def test_delete_last_key(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("ssh-ed25519 AAAA LAST_KEY\n")

        with patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth):
            ok, text = ssh_keys.delete_ssh_key("LAST_KEY")

        assert ok is True
        assert "удалён" in text
        assert auth.read_text() == ""

    def test_key_not_found_restores_backup(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        original = "ssh-ed25519 AAAA KEY_ONE\nssh-ed25519 BBBB KEY_TWO\n"
        auth.write_text(original)

        with patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth):
            ok, text = ssh_keys.delete_ssh_key("MISSING")

        assert ok is False
        assert "не найден" in text
        assert auth.read_text() == original

    def test_grep_error(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("ssh-ed25519 AAAA KEY_ONE\n")

        result = Mock(
            returncode=2,
            stdout="",
            stderr="grep error",
        )

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(ssh_keys.subprocess, "run", return_value=result),
        ):
            ok, text = ssh_keys.delete_ssh_key("KEY_ONE")

        assert ok is False
        assert "Ошибка поиска ключа" in text
        assert "grep error" in text

    def test_grep_returncode_one_with_stdout(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("ssh-ed25519 AAAA KEY_ONE\n")

        result = Mock(
            returncode=1,
            stdout="unexpected output",
            stderr="",
        )

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(ssh_keys.subprocess, "run", return_value=result),
        ):
            ok, text = ssh_keys.delete_ssh_key("KEY_ONE")

        assert ok is False
        assert "Ошибка удаления ключа" in text

    def test_unexpected_delete_error(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("ssh-ed25519 AAAA KEY_ONE\n")

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(
                ssh_keys.shutil,
                "copy2",
                side_effect=OSError("copy failed"),
            ),
        ):
            ok, text = ssh_keys.delete_ssh_key("KEY_ONE")

        assert ok is False
        assert text == "❌ Ошибка: copy failed"

    def test_count_unchanged_restores_original(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        original = "ssh-ed25519 AAAA KEY_ONE\n"
        auth.write_text(original)

        result = Mock(
            returncode=0,
            stdout=original,
            stderr="",
        )

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(ssh_keys.subprocess, "run", return_value=result),
        ):
            ok, text = ssh_keys.delete_ssh_key("MISSING")

        assert ok is False
        assert "не найден" in text
        assert auth.read_text() == original


class TestGetSSHHistory:
    def test_last_error(self):
        result = Mock(
            returncode=1,
            stdout="",
            stderr="last failed",
        )

        with (
            patch.object(ssh_keys.subprocess, "run", return_value=result),
            patch.object(ssh_keys.logger, "error") as mock_error,
        ):
            text = ssh_keys.get_ssh_history()

        assert "Не удалось получить историю SSH" in text
        mock_error.assert_called_once()

    def test_malformed_lines_are_skipped(self):
        result = Mock(
            returncode=0,
            stdout=(
                "garbage\n"
                "wtmp begins Tue Aug 1 00:00:00 2026\n"
                "reboot system boot 6.8.0 Tue Aug 1 00:00\n"
                "root pts/0 Mon Aug 24 18:32 - 19:00 (00:28) 203.0.113.11\n"
            ),
            stderr="",
        )

        with patch.object(ssh_keys.subprocess, "run", return_value=result):
            text = ssh_keys.get_ssh_history()

        assert "SSH-входы*" in text
        assert "· 1" in text
        assert "203.0.113.11" in text

    def test_non_terminal_session_is_skipped(self):
        lines = [
            "root pts/0 Mon Aug 14 01:02 - 02:00 (00:58) 203.0.113.11",
            "root :0 Mon Aug 14 02:03 - 03:00 (00:57) 203.0.113.12",
        ]

        result = Mock(
            returncode=0,
            stdout="\n".join(lines) + "\n",
            stderr="",
        )

        with patch.object(ssh_keys.subprocess, "run", return_value=result):
            text = ssh_keys.get_ssh_history()

        assert "203.0.113.11" in text
        assert "203.0.113.12" not in text

    def test_short_line_after_length_check_is_skipped(self):
        result = Mock(
            returncode=0,
            stdout=(
                "root pts/0 Mon Aug 14\n"
                "root pts/1 Mon Aug 14 02:03 - 03:00 (00:57) 203.0.113.13\n"
            ),
            stderr="",
        )

        with patch.object(ssh_keys.subprocess, "run", return_value=result):
            text = ssh_keys.get_ssh_history()

        assert "203.0.113.13" in text

    def test_successful_connection(self):
        line = "root pts/0 Mon Aug 14 01:02 - 02:00 (00:58) 203.0.113.11"

        result = Mock(
            returncode=0,
            stdout=line + "\n",
            stderr="",
        )

        with patch.object(ssh_keys.subprocess, "run", return_value=result):
            text = ssh_keys.get_ssh_history()

        assert "SSH-входы*" in text
        assert "· 1" in text
        assert "root" in text
        assert "203.0.113.11" in text
        assert "14.Aug 01:02" in text

    def test_unknown_ip_is_skipped_only_for_local_addresses(self):
        line = "root pts/0 Mon Aug 14 02:03 - 03:00 (00:57) 10.0.0.1"

        result = Mock(
            returncode=0,
            stdout=line + "\n",
            stderr="",
        )

        with patch.object(ssh_keys.subprocess, "run", return_value=result):
            text = ssh_keys.get_ssh_history()

        assert "10.0.0.1" in text
        assert "Unknown" not in text

    def test_local_ip_entries_are_skipped(self):
        lines = [
            "root pts/0 Mon Aug 14 02:03 - 03:00 (00:57) 0.0.0.0",
            "root pts/1 Mon Aug 14 03:04 - 03:00 (00:56) ::1",
            "root pts/2 Mon Aug 14 03:05 - 03:00 (00:55) localhost",
            "root pts/3 Mon Aug 14 03:06 - 03:00 (00:54) -",
        ]

        result = Mock(
            returncode=0,
            stdout="\n".join(lines) + "\n",
            stderr="",
        )

        with patch.object(ssh_keys.subprocess, "run", return_value=result):
            text = ssh_keys.get_ssh_history()

        assert "Успешных подключений не найдено" in text

    def test_duplicate_entries_are_removed(self):
        line = "root pts/0 Mon Aug 14 04:05 - 05:00 (00:55) 203.0.113.11"

        result = Mock(
            returncode=0,
            stdout=f"{line}\n{line}\n",
            stderr="",
        )

        with patch.object(ssh_keys.subprocess, "run", return_value=result):
            text = ssh_keys.get_ssh_history()

        assert "SSH-входы*" in text
        assert "· 1" in text

    def test_limit_and_reverse_order(self):
        lines = []

        for hour in range(1, 6):
            lines.append(
                f"root pts/0 Mon Aug 14 {hour:02d}:00 - 02:00 (01:00) 10.0.0.{hour}"
            )

        result = Mock(
            returncode=0,
            stdout="\n".join(lines) + "\n",
            stderr="",
        )

        with patch.object(ssh_keys.subprocess, "run", return_value=result):
            text = ssh_keys.get_ssh_history(limit=2)

        assert "SSH-входы*" in text
        assert "· 2" in text
        assert "10.0.0.1" in text
        assert "10.0.0.2" in text
        assert "10.0.0.3" not in text

    def test_limit_zero(self):
        line = "root pts/0 Mon Aug 14 07:08 - 08:00 (00:52) 10.0.0.7"

        result = Mock(
            returncode=0,
            stdout=line + "\n",
            stderr="",
        )

        with patch.object(ssh_keys.subprocess, "run", return_value=result):
            text = ssh_keys.get_ssh_history(limit=0)

        assert "SSH-входы*" in text
        assert "· 0" in text

    def test_exception(self):
        with patch.object(
            ssh_keys.subprocess,
            "run",
            side_effect=RuntimeError("history boom"),
        ):
            text = ssh_keys.get_ssh_history()

        assert text == "❌ Ошибка: history boom"


class TestGetSSHStatus:
    def test_active_with_secure_configuration(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("ssh-ed25519 AAAA KEY_ONE\nssh-ed25519 BBBB KEY_TWO\n")

        sshd_result = Mock(
            returncode=0,
            stdout=(
                "port 2222\n"
                "passwordauthentication no\n"
                "permitrootlogin without-password\n"
            ),
            stderr="",
        )

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(ssh_keys, "service_is_active", return_value=True),
            patch.object(
                ssh_keys.subprocess,
                "run",
                return_value=sshd_result,
            ),
        ):
            text = ssh_keys.get_ssh_status()

        assert "🟢 работает" in text
        assert "`2222`" in text
        assert "отключён" in text
        assert "только ключи" in text

    def test_inactive_password_and_root_allowed(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("ssh-ed25519 AAAA KEY_ONE\n")

        sshd_result = Mock(
            returncode=0,
            stdout=("port 22\npasswordauthentication yes\npermitrootlogin yes\n"),
            stderr="",
        )

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(ssh_keys, "service_is_active", return_value=False),
            patch.object(
                ssh_keys.subprocess,
                "run",
                return_value=sshd_result,
            ),
        ):
            text = ssh_keys.get_ssh_status()

        assert "🔴 не работает" in text
        assert "разрешён" in text

    def test_root_login_disabled(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("")

        sshd_result = Mock(
            returncode=0,
            stdout=("port 22\npasswordauthentication no\npermitrootlogin no\n"),
            stderr="",
        )

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(ssh_keys, "service_is_active", return_value=False),
            patch.object(
                ssh_keys.subprocess,
                "run",
                return_value=sshd_result,
            ),
        ):
            text = ssh_keys.get_ssh_status()

        assert "запрещён полностью" in text

    def test_unknown_configuration(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("broken\n")

        sshd_result = Mock(
            returncode=0,
            stdout="",
            stderr="",
        )

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(ssh_keys, "service_is_active", return_value=False),
            patch.object(
                ssh_keys.subprocess,
                "run",
                return_value=sshd_result,
            ),
        ):
            text = ssh_keys.get_ssh_status()

        assert "unknown" in text
        assert "`22`" in text
        assert "неизвестно" in text

    def test_sshd_config_error_is_ignored(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("")

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(ssh_keys, "service_is_active", return_value=False),
            patch.object(
                ssh_keys.subprocess,
                "run",
                side_effect=RuntimeError("sshd unavailable"),
            ),
        ):
            text = ssh_keys.get_ssh_status()

        assert "🔐 *SSH-меню*" in text
        assert "`22`" in text
        assert "неизвестно" in text

    def test_authorized_keys_read_error_is_ignored(self, tmp_path):
        auth = tmp_path / "authorized_keys"

        sshd_result = Mock(
            returncode=0,
            stdout="port 22\n",
            stderr="",
        )

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(ssh_keys, "service_is_active", return_value=True),
            patch.object(
                ssh_keys.subprocess,
                "run",
                return_value=sshd_result,
            ),
            patch(
                "builtins.open",
                side_effect=PermissionError("permission denied"),
            ),
        ):
            text = ssh_keys.get_ssh_status()

        assert "🔐 *SSH-меню*" in text

    def test_service_check_tries_sshd_after_ssh(self, tmp_path):
        auth = tmp_path / "authorized_keys"
        auth.write_text("")

        sshd_result = Mock(
            returncode=0,
            stdout="port 22\n",
            stderr="",
        )

        with (
            patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth),
            patch.object(
                ssh_keys,
                "service_is_active",
                side_effect=[False, True],
            ) as mock_active,
            patch.object(
                ssh_keys.subprocess,
                "run",
                return_value=sshd_result,
            ),
        ):
            text = ssh_keys.get_ssh_status()

        assert "🟢 работает" in text
        assert mock_active.call_count == 2

    def test_status_exception(self):
        with patch.object(
            ssh_keys,
            "service_is_active",
            side_effect=RuntimeError("status boom"),
        ):
            text = ssh_keys.get_ssh_status()

        assert text.startswith("❌ Ошибка SSH статуса:")


class TestAuthorizedKeysPath:
    def test_returns_string_path(self, tmp_path):
        auth = Path(tmp_path) / "authorized_keys"

        with patch.object(ssh_keys, "SSH_AUTHORIZED_KEYS", auth):
            result = ssh_keys.get_authorized_keys_path()

        assert result == str(auth)


class TestExports:
    def test_all_exports(self):
        assert "SSH_IP_MAP" in ssh_keys.__all__
        assert "SSH_KEY_MAP" in ssh_keys.__all__
        assert "delete_ssh_key" in ssh_keys.__all__
        assert "get_authorized_keys_path" in ssh_keys.__all__
        assert "get_ssh_history" in ssh_keys.__all__
        assert "get_ssh_keys_list" in ssh_keys.__all__
        assert "get_ssh_status" in ssh_keys.__all__
