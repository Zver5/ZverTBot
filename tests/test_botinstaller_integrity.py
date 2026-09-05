from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOTINSTALLER = ROOT / "deploy" / "botinstaller"


def test_required_botinstaller_files_exist():
    required = [
        "install.sh",
        "checks.sh",
        "system_tuning.sh",
        "packages.txt",
    ]

    missing = [x for x in required if not (BOTINSTALLER / x).exists()]

    assert not missing, f"Missing botinstaller files: {missing}"


def test_required_systemd_core_templates():
    core = BOTINSTALLER / "systemd" / "core"

    required = [
        "zvertbot.service",
        "stats-http.service",
        "healthcheck.service",
        "geoip-collect.service",
        "geoip-collect.timer",
        "vps-stats.service",
        "vps-stats.timer",
    ]

    missing = [x for x in required if not (core / x).exists()]

    assert not missing, f"Missing core templates: {missing}"


def test_required_optional_templates():
    optional = BOTINSTALLER / "systemd" / "optional"

    required = [
        "kuma-webhook.service",
        "xray-traffic.service",
        "xray-traffic.timer",
        "zvertbot-backup.service",
        "zvertbot-backup.timer",
    ]

    missing = [x for x in required if not (optional / x).exists()]

    assert not missing, f"Missing optional templates: {missing}"
