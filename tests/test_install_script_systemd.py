from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INSTALL = (ROOT / "deploy" / "botinstaller" / "install.sh").read_text()


def test_install_script_installs_core_directory():
    assert "systemd/core" in INSTALL
    assert "*.service" in INSTALL
    assert "*.timer" in INSTALL


def test_install_script_installs_optional_directory():
    assert "systemd/optional" in INSTALL
    assert "OPTIONAL_DIR" in INSTALL


def test_core_services_are_started():
    required = [
        "zvertbot.service",
        "stats-http.service",
        "vps-stats.service",
        "vps-stats.timer",
        "geoip-collect.timer",
        "healthcheck.service",
    ]

    missing = [x for x in required if x not in INSTALL]

    assert not missing, f"Core services missing from startup list: {missing}"


def test_optional_services_are_started():
    required = [
        "xray-traffic.timer",
        "zvertbot-backup.timer",
        "kuma-webhook.service",
    ]

    missing = [x for x in required if x not in INSTALL]

    assert not missing, f"Optional services missing from startup list: {missing}"


def test_every_timer_has_matching_service():
    folders = [
        ROOT / "deploy" / "botinstaller" / "systemd" / "core",
        ROOT / "deploy" / "botinstaller" / "systemd" / "optional",
    ]

    missing = []

    for folder in folders:
        for timer in folder.glob("*.timer"):
            service = folder / (timer.stem + ".service")

            if not service.exists():
                missing.append(str(service.relative_to(ROOT)))

    assert not missing, f"Timers without service files: {missing}"


def test_install_script_does_not_silently_ignore_systemd_failures():
    start = INSTALL.index("create_service()")
    end = INSTALL.index("\n}\n", start) + 2
    create_service = INSTALL[start:end]

    assert 'systemctl enable "$service"' in create_service
    assert 'systemctl restart "$service"' in create_service
    assert "|| true" not in create_service


def test_install_script_protects_existing_env_file():
    start = INSTALL.index("create_env()")
    end = INSTALL.index("\n}\n", start) + 2
    create_env = INSTALL[start:end]

    assert 'ENV_FILE="${INSTALL_DIR}/.env"' in create_env
    assert 'if [ -f "$ENV_FILE" ]; then' in create_env
    assert 'chmod 600 "$ENV_FILE"' in create_env


def test_install_script_reports_sysctl_apply_failure():
    start = INSTALL.index("enable_ip_forwarding()")
    end = INSTALL.index("\n}\n", start) + 2
    enable_ip_forwarding = INSTALL[start:end]

    assert "if ! sysctl -p >/dev/null 2>&1; then" in enable_ip_forwarding
    assert 'warn "Failed to apply sysctl configuration"' in enable_ip_forwarding
    assert "|| true" not in enable_ip_forwarding
