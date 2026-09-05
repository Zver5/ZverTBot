import os
import subprocess
from pathlib import Path

import pytest

import config
from handlers.navigation_registry import register_navigation_screens

# В тестах используем ту же единую startup-регистрацию screens, что и main.py.
register_navigation_screens()


@pytest.fixture(scope="session")
def deploy_archive(tmp_path_factory):
    """Build a fresh deployment archive in a temporary directory."""
    root = Path(__file__).resolve().parent.parent
    output_dir = tmp_path_factory.mktemp("deploy-output")
    build_dir = tmp_path_factory.mktemp("deploy-build")

    env = os.environ.copy()
    env["OUTPUT_DIR"] = str(output_dir)
    env["BUILD_DIR"] = str(build_dir)

    subprocess.run(
        ["bash", str(root / "deploy/build.sh")],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    archives = sorted(output_dir.glob("ZverTBot-deploy-*.tar.gz"))
    assert len(archives) == 1, (
        f"Expected exactly one deploy archive, found {len(archives)}"
    )

    return archives[0]


def isolate_bot_history(tmp_path, monkeypatch):
    """Изолирует историю тестов от рабочей bot_history.json."""
    test_history = tmp_path / "bot_history.json"
    test_history.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(
        config,
        "BOT_HISTORY",
        str(test_history),
    )


@pytest.fixture(autouse=True)
def disable_history_side_effects(monkeypatch):
    """Не позволяет обычным тестам записывать историю действий."""

    def fake_save_history(*args, **kwargs):
        return None

    def fake_log_action(*args, **kwargs):
        return None

    modules = [
        "utils.notifications",
        "utils.helpers",
        "handlers.admin.clients",
        "handlers.admin.management",
        "handlers.admin.bindings",
        "handlers.features.ssh_keys",
        "handlers.features.fail2ban",
        "handlers.features.processes",
        "handlers.commands",
    ]

    for name in modules:
        try:
            module = __import__(name, fromlist=["log_action"])
        except Exception:
            continue

        if hasattr(module, "log_action"):
            monkeypatch.setattr(
                module,
                "log_action",
                fake_log_action,
            )
