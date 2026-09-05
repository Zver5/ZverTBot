import re
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_deploy_required_files_exist():
    required = [
        "deploy/build.sh",
        "deploy/botinstaller/install.sh",
        "deploy/botinstaller/system_tuning.sh",
        "deploy/botinstaller/packages.txt",
    ]

    for item in required:
        assert (ROOT / item).exists(), f"Missing deploy file: {item}"


def test_config_env_example_contains_required_keys():
    env_file = ROOT / ".env.example"

    text = env_file.read_text()

    required = [
        "BOT_TOKEN",
        "ADMIN_CHAT",
        "SERVER_IP",
        "SERVER_FLAG",
        "HASS_FLAG",
        "HA_TUNNEL_IP",
        "XRAY_CONF",
        "AWG_CONF",
        "KUMA_HEALTHCHECK_URL",
    ]

    for key in required:
        assert re.search(rf"^{key}=", text, re.MULTILINE), f"Missing env key: {key}"


def test_system_tuning_contains_required_settings():
    tuning = (ROOT / "deploy/botinstaller/system_tuning.sh").read_text()

    required = [
        "nf_conntrack_max=262144",
        "nf_conntrack_tcp_timeout_established=432000",
        "nf_conntrack_tcp_timeout_close_wait=60",
        "nf_conntrack_tcp_timeout_time_wait=120",
        "precedence ::ffff:0:0/96  100",
        "SystemMaxUse",
        "RuntimeMaxUse",
        "MaxRetentionSec",
        "Compress",
    ]

    for item in required:
        assert item in tuning, f"Missing tuning parameter: {item}"


def test_packages_contains_required_tools():
    packages = (ROOT / "deploy/botinstaller/packages.txt").read_text()

    required = [
        "rclone",
        "iptables-persistent",
        "netfilter-persistent",
        "fail2ban",
    ]

    for item in required:
        assert item in packages, f"Missing package: {item}"


def test_deploy_archive_contains_env_template(deploy_archive):
    with tarfile.open(deploy_archive) as tar:
        names = tar.getnames()

    assert any(name.endswith("/deploy/botinstaller/.env.example") for name in names), (
        "Deploy archive does not contain deploy/botinstaller/.env.example"
    )


def test_deploy_archive_is_clean(deploy_archive):
    forbidden_names = [
        ".env",
        ".venv",
        ".git",
        ".pytest_cache",
        ".ruff_cache",
    ]

    with tarfile.open(deploy_archive) as tar:
        names = tar.getnames()

    for name in names:
        parts = Path(name).parts

        assert not any(part in forbidden_names for part in parts), (
            f"Forbidden item in archive: {name}"
        )

        assert not name.endswith(".pyc"), f"Forbidden pyc file: {name}"

        assert "__pycache__" not in parts, f"Forbidden cache dir: {name}"


def test_systemd_templates_exist():
    systemd = ROOT / "deploy/botinstaller/systemd"

    assert systemd.exists()

    services = list(systemd.rglob("*.service"))

    assert services, "No systemd services found"


def test_system_tuning_reports_conntrack_module_failure():
    tuning = (ROOT / "deploy" / "botinstaller" / "system_tuning.sh").read_text()

    assert "if ! modprobe nf_conntrack; then" in tuning
    assert 'echo "⚠️ nf_conntrack module could not be loaded"' in tuning
    assert "modprobe nf_conntrack || true" not in tuning


def test_backup_reports_remote_delete_failure():
    backup = (ROOT / "scripts" / "backup-to-yandex.sh").read_text()

    assert "if ! rclone delete \\" in backup
    assert 'log_warn "backup.remote_retention.delete_failed | file=${FILE}"' in backup
    assert (
        "rclone delete \\\n"
        '"${BACKUP_REMOTE}:${BACKUP_ROOT_DIR}/configs/${FILE}" \\\n'
        "2>/dev/null || true"
    ) not in backup


def test_backup_reports_upload_failures():
    backup = (ROOT / "scripts" / "backup-to-yandex.sh").read_text()

    assert "if ! rclone copy \\" in backup
    assert '"status": "failed"' in backup
    assert 'write_failed_status 1 "Failed to upload backup to remote"' in backup
    assert 'write_failed_status 1 "Uploaded archive was not found on remote"' in backup
    assert 'write_failed_status 1 "Failed to upload passports to remote"' in backup


def test_backup_has_unexpected_error_status_handler():
    backup = (ROOT / "scripts" / "backup-to-yandex.sh").read_text()

    assert "STATUS_WRITTEN=0" in backup
    assert "write_failed_status()" in backup
    assert "handle_unexpected_error()" in backup
    assert "trap 'handle_unexpected_error' ERR" in backup
    assert "set -E" in backup
    assert '"status": "failed"' in backup
    assert '"error": "${error}"' in backup


def test_backup_does_not_silently_ignore_amneziawg_copy_failure():
    backup = (ROOT / "scripts" / "backup-to-yandex.sh").read_text()

    assert (
        "find /etc/amnezia/amneziawg -type f -exec cp --parents {} "
        '"${TEMP_DIR}/" \\; 2>/dev/null || true'
    ) not in backup
