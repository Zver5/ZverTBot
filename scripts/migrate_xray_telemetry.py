#!/usr/bin/env python3
"""Idempotent migration of Xray VLESS telemetry configuration."""

import argparse
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from config.paths import XRAY_CONF
from services.xray.config_manager import (
    get_xray_readiness,
    load_xray_config,
    normalize_xray_api_config,
    save_xray_config,
)


def create_backup() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup = XRAY_CONF.with_name(f"{XRAY_CONF.name}.bak-{timestamp}")
    shutil.copy2(XRAY_CONF, backup)
    return str(backup)


def restart_xray() -> None:
    active = (
        subprocess.run(
            ["systemctl", "is-active", "--quiet", "xray.service"],
            check=False,
        ).returncode
        == 0
    )

    if active:
        subprocess.run(
            ["systemctl", "restart", "xray.service"],
            check=True,
        )
        print("Xray service restarted.")
    else:
        print("Xray is not active; restart skipped.")


def migrate(restart_requested: bool = False) -> bool:
    if not shutil.which("xray"):
        print("Xray binary not found; migration skipped.")
        return False

    if not XRAY_CONF.is_file():
        raise FileNotFoundError(f"Xray config not found: {XRAY_CONF}")

    current = load_xray_config()
    ready, problems = get_xray_readiness(current)

    changed = False

    if not ready:
        print("Xray config is not ready for VLESS Reality; migration skipped.")
        for problem in problems:
            print(f"  - {problem}")
    else:
        normalized = normalize_xray_api_config(current)
        changed = normalized != current

        if changed:
            backup = create_backup()
            print(f"Backup created: {backup}")

            # Validates the candidate before atomically replacing config.json.
            save_xray_config(normalized)
            print("Xray telemetry configuration migrated.")
        else:
            print("Xray telemetry configuration already up to date.")

    if changed:
        restart_xray()
    elif restart_requested:
        if ready:
            restart_xray()
        else:
            print("Xray restart deferred: VLESS Reality config is not ready.")

    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Restart active Xray after systemd drop-in changes.",
    )
    args = parser.parse_args()

    try:
        migrate(restart_requested=args.restart)
    except Exception as exc:
        print(f"Xray telemetry migration failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
