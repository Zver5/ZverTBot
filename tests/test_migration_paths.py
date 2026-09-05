from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_deploy_has_no_hardcoded_old_paths():
    """
    Проверяем, что deploy не привязан к старому серверу.
    """

    check_files = [
        ROOT / "deploy/botinstaller/install.sh",
        ROOT / "deploy/botinstaller/system_tuning.sh",
        ROOT / "deploy/botinstaller/checks.sh",
    ]

    old_paths = [
        "/root/ZverTBot",
        "/home/root/ZverTBot",
    ]

    for file in check_files:
        if not file.exists():
            continue

        text = file.read_text(errors="ignore")

        for old in old_paths:
            assert old not in text, f"Old hardcoded path found in {file}: {old}"


def test_systemd_templates_use_install_dir():
    """
    Systemd шаблоны должны использовать INSTALL_DIR,
    а не старый путь.
    """

    systemd_dir = ROOT / "deploy/botinstaller/systemd"

    if not systemd_dir.exists():
        return

    for service in systemd_dir.rglob("*.service"):
        text = service.read_text(errors="ignore")

        assert "/root/ZverTBot" not in text, f"Old path in systemd: {service}"
