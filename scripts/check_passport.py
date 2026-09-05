#!/usr/bin/env python3

import sys
from pathlib import Path

# Если запущено системным Python — перезапускаем через venv проекта
PROJECT_DIR = Path(__file__).resolve().parent.parent
VENV_PYTHON = PROJECT_DIR / ".venv/bin/python"

if sys.executable != str(VENV_PYTHON) and VENV_PYTHON.exists():
    import os

    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

import json  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import socket  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
import urllib.request  # noqa: E402
from datetime import datetime  # noqa: E402

# Добавляем корень проекта для запуска напрямую из scripts/
INSTALL_DIR = Path(__file__).resolve().parent.parent

if str(INSTALL_DIR) not in sys.path:
    sys.path.insert(0, str(INSTALL_DIR))

import unicodedata  # noqa: E402

from config.paths import AWG_DEFAULT_CONF, XRAY_CONF  # noqa: E402
from config.secrets import HA_TUNNEL_IP  # noqa: E402

# ==============================
# ZverTBot SERVER PASSPORT CHECK v1.1
# ==============================

OK = 0
WARN = 0
FAIL = 0

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def run(cmd, timeout=5):
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""
    except OSError:
        return ""


def header(text):
    print()
    print(f"{BLUE}{BOLD}{'═' * 50}{RESET}")
    print(f"{BLUE}{BOLD}{text.center(50)}{RESET}")
    print(f"{BLUE}{BOLD}{'═' * 50}{RESET}")


def section(text):
    print()
    print(f"{CYAN}{BOLD}{text}{RESET}")
    print("─" * 50)


def ok(text):
    global OK
    OK += 1
    print(f"{GREEN}🟢 {text}{RESET}")


def warn(text):
    global WARN
    WARN += 1
    print(f"{YELLOW}🟡 {text}{RESET}")


def fail(text):
    global FAIL
    FAIL += 1
    print(f"{RED}🔴 {text}{RESET}")


def check_file(path):
    if Path(path).exists():
        ok(f"Файл: {path}")
    else:
        fail(f"Файл отсутствует: {path}")


def check_enabled_active_unit(unit, active_label):
    """Проверяет systemd unit на enabled + active."""
    enabled = run(["systemctl", "is-enabled", unit])
    active = run(["systemctl", "is-active", unit])
    width = SERVICE_NAME_WIDTH

    if enabled == "enabled" and active == "active":
        ok(f"{unit:<{width}} ВКЛ + {active_label}")
    elif active == "active":
        warn(f"{unit:<{width}} {active_label}, НЕ ВКЛЮЧЕН")
    elif enabled == "enabled":
        fail(f"{unit:<{width}} ВКЛЮЧЕН, НО НЕ {active_label}")
    else:
        fail(
            f"{unit:<{width}} "
            f"{enabled or 'НЕ ВКЛЮЧЕН'} + "
            f"{active or f'НЕ {active_label}'}"
        )


def discover_awg_interfaces():
    """Возвращает AWG-интерфейсы по native-конфигам AmneziaWG."""
    return sorted(config.stem for config in AWG_DEFAULT_CONF.parent.glob("*.conf"))


def discover_tcp_port(service_name):
    """Возвращает реальный TCP LISTEN-порт systemd-сервиса."""
    # Сначала получаем MainPID именно нужного systemd-сервиса.
    pid_output = run(
        ["systemctl", "show", "-p", "MainPID", "--value", f"{service_name}.service"]
    ).strip()

    if not pid_output.isdigit() or pid_output == "0":
        return None

    pid = pid_output

    # Затем ищем LISTEN-сокет именно этого PID.
    output = run(["ss", "-H", "-ltnp"])

    for line in output.splitlines():
        if f"pid={pid}," not in line and f"pid={pid})" not in line:
            continue

        match = re.search(r":(\d+)\s", line)
        if match:
            return int(match.group(1))

    return None


def discover_udp_ports():
    """Возвращает реальные UDP LISTEN-порты AWG."""
    output = run(["awg", "show", "all", "listen-port"])
    result = []

    for line in output.splitlines():
        parts = line.split()

        if len(parts) != 2 or not parts[1].isdigit():
            continue

        result.append((parts[0], int(parts[1])))

    return result


def discover_sshd_port():
    """Возвращает реальный порт SSH из sshd effective config."""
    output = run(["sshd", "-T"])
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].lower() == "port":
            try:
                return int(parts[1])
            except ValueError:
                pass

    return None


def discover_docker_subnets():
    """Возвращает реальные IPv4 subnet Docker-сетей."""
    network_ids = run(["docker", "network", "ls", "-q"]).split()

    if not network_ids:
        return []

    output = run(
        [
            "docker",
            "network",
            "inspect",
            *network_ids,
            "--format",
            "{{range .IPAM.Config}}{{.Subnet}}{{end}}",
        ]
    )

    return list(
        dict.fromkeys(subnet.strip() for subnet in output.split() if subnet.strip())
    )


def discover_docker_ports():
    """Возвращает опубликованные TCP-порты Docker-контейнеров."""
    output = run(["docker", "ps", "--format", "{{.Names}}\\t{{.Ports}}"])

    items = []

    for line in output.splitlines():
        if "\t" not in line:
            continue

        name, ports = line.split("\t", 1)

        for match in re.finditer(
            r"(?:0\.0\.0\.0|127\.0\.0\.1|\[::\]|:::):(?P<port>\d+)->",
            ports,
        ):
            items.append((name, int(match.group("port"))))

    return list(dict.fromkeys(items))


def load_xray_passport_config():
    """Читает порты и Reality SNI непосредственно из XRAY_CONF."""
    result = {
        "api_port": None,
        "reality": [],
    }

    try:
        with XRAY_CONF.open("r", encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        warn(f"Xray passport config: не удалось прочитать ({e})")
        return result

    for inbound in config.get("inbounds", []):
        port = inbound.get("port")
        tag = inbound.get("tag", "")

        if tag == "api":
            result["api_port"] = port

        for server_name in (
            inbound.get("streamSettings", {})
            .get("realitySettings", {})
            .get("serverNames", [])
        ):
            result["reality"].append(
                {
                    "port": port,
                    "sni": server_name,
                }
            )

    return result


XRAY_PASSPORT = load_xray_passport_config()


header("🐺 ZverTBot SERVER PASSPORT CHECK v1.1")
print(f"{BOLD}Дата:{RESET} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{BOLD}Сервер:{RESET} {socket.gethostname()}")
print(f"{BOLD}Установка:{RESET} {INSTALL_DIR}")


section("📦 ПРОЕКТ")
check_file(INSTALL_DIR / "main.py")
check_file(INSTALL_DIR / ".env")
check_file(INSTALL_DIR / ".venv/bin/python")


section("⚙️ SYSTEMD SERVICES")

# Все имена сервисов занимают одинаковую ширину.
SERVICE_NAME_WIDTH = 32

main_services = [
    "healthcheck.service",
    "stats-http.service",
    "kuma-webhook.service",
]

for s in main_services:
    check_enabled_active_unit(s, "РАБОТАЕТ")

# Остальные системные сервисы.
for s in ["xray.service", "fail2ban.service"] + [
    f"awg-quick@{iface}.service" for iface in discover_awg_interfaces()
]:
    active = run(["systemctl", "is-active", s])

    if active == "active":
        ok(f"{s:<{SERVICE_NAME_WIDTH}} РАБОТАЕТ")
    else:
        fail(f"{s:<{SERVICE_NAME_WIDTH}} {active or 'НЕ РАБОТАЕТ'}")

section("⏱ TIMERS")

timers = [
    "vps-stats.timer",
    "geoip-collect.timer",
    "xray-traffic.timer",
    "zvertbot-backup.timer",
]

for t in timers:
    check_enabled_active_unit(t, "АКТИВЕН")


section("🌐 HTTP ПРОВЕРКИ")
for url, name in [
    ("http://127.0.0.1:8080/stats.json", "Stats HTTP"),
    ("http://127.0.0.1:8081/status", "Healthcheck"),
]:
    if run(["curl", "-fs", "--max-time", "3", url]):
        ok(f"{name:<25} ДОСТУПЕН")
    else:
        warn(f"{name:<25} НЕДОСТУПЕН")


section("🌍 ПОРТЫ И ПОЛИТИКА ДОСТУПА")

# ============================================================
# ПОРТЫ И ПОЛИТИКА ДОСТУПА
#
# ВАЖНО:
# - один порт = одна итоговая проверка;
# - здесь не печатается сырой вывод ss;
# - отдельные проверки rate-limit / PasswordAuthentication
#   ниже повторно НЕ выполняются.
# ============================================================


def port_listening(port, proto):
    if proto == "TCP":
        return bool(run(["ss", "-H", "-ltn", f"( sport = :{port} )"]))
    return bool(run(["ss", "-H", "-lun", f"( sport = :{port} )"]))


def port_policy_ok(
    port,
    policy_type,
    service=None,
    firewall="",
    docker_subnets=None,
):
    """
    Проверяет именно access-policy.
    Ничего не печатает и не меняет счётчики.
    """

    if docker_subnets is None:
        docker_subnets = []

    # --------------------------------------------------------
    # ZverTBot
    #
    # Порт берётся динамически.
    # Ограничение: максимум 5 новых соединений
    # за 60 секунд с одного IP.
    # --------------------------------------------------------
    if service == "zvertbot":
        return (
            f"--dport {port}" in firewall
            and "zvertbot" in firewall
            and "--update" in firewall
            and "--seconds 60" in firewall
            and "--hitcount 6" in firewall
            and "-j DROP" in firewall
        )

    # --------------------------------------------------------
    # WORLD
    #
    # Внешние сервисы дополнительно не ограничиваем.
    # Сам факт LISTEN уже проверяется отдельно.
    # --------------------------------------------------------
    if policy_type == "world":
        return True

    # --------------------------------------------------------
    # LOCAL
    #
    # Разрешаем localhost.
    # Если сервис опубликован Docker-ом, проверяем реальные
    # Docker subnet, полученные от docker network inspect.
    # --------------------------------------------------------
    if policy_type == "local":
        if "127.0.0.1" in firewall or "localhost" in firewall:
            return True

        return any(subnet in firewall for subnet in docker_subnets)

    # --------------------------------------------------------
    # Xray API
    #
    # API должен слушать только localhost.
    # --------------------------------------------------------
    if policy_type == "localhost":
        api_port = XRAY_PASSPORT.get("api_port")

        if not api_port:
            return False

        listening = run(["ss", "-H", "-ltn", f"( sport = :{api_port} )"])

        return f"127.0.0.1:{api_port}" in listening

    # --------------------------------------------------------
    # Docker
    #
    # Никаких жёстко заданных Docker-портов и сетей.
    #
    # Порт уже обнаружен через docker ps.
    # Доступ проверяем по реальным Docker subnet.
    # --------------------------------------------------------
    if policy_type == "docker":
        if "127.0.0.1" in firewall:
            return True

        if HA_TUNNEL_IP and HA_TUNNEL_IP in firewall:
            return True

        return any(subnet in firewall for subnet in docker_subnets)

    return True


def visual_width(text):
    """Возвращает ширину строки в терминале с учётом Unicode/emoji."""
    width = 0

    for char in str(text):
        if unicodedata.combining(char):
            continue

        east = unicodedata.east_asian_width(char)

        if east in ("W", "F"):
            width += 2
        else:
            width += 1

    return width


def visual_ljust(text, width):
    """Дополняет строку пробелами до заданной визуальной ширины."""
    text = str(text)
    return text + " " * max(0, width - visual_width(text))


def print_port_table(title, ports):
    print()
    print(title)

    # Фиксированные визуальные ширины колонок.
    # Важно: ширина считается с учётом emoji.
    port_w = 16
    service_w = 16
    policy_w = 40
    status_w = 12

    print(
        visual_ljust("ПОРТ/ПРОТОКОЛ", port_w)
        + visual_ljust("   СЕРВИС", service_w)
        + visual_ljust("    ПОЛИТИКА", policy_w)
        + visual_ljust("    СТАТУС", status_w)
    )

    print("─" * port_w + "─" * service_w + "─" * policy_w + "───────")

    rules = run(["iptables-save"])
    nft_rules = run(["nft", "list", "ruleset"])
    firewall = rules or nft_rules or ""
    docker_subnets = discover_docker_subnets()

    for port, proto, service, policy, policy_type in ports:
        listening = port_listening(port, proto)
        policy_ok = listening and port_policy_ok(
            port,
            policy_type,
            service,
            firewall,
            docker_subnets,
        )

        if policy_ok:
            status = "ДОСТУПЕН"
        else:
            status = "ПОЛИТИКА" if listening else "НЕДОСТУПЕН"

        line = (
            visual_ljust(f"{port}/{proto}", port_w)
            + visual_ljust(service, service_w)
            + visual_ljust(policy, policy_w)
            + visual_ljust(status.lstrip(), status_w)
        )

        if policy_ok:
            ok(line)
        else:
            fail(line)


# ============================================================
# Динамически обнаруженные сетевые сервисы
# ============================================================

ssh_port = discover_sshd_port()

tcp_services = []

if ssh_port:
    tcp_services.append(
        (
            ssh_port,
            "TCP",
            "sshd",
            "🌐 WORLD · 🔑 SSH KEY · 🛡 Fail2ban",
            "world",
        )
    )

port = discover_tcp_port("zvertbot")
if port:
    tcp_services.append(
        (
            port,
            "TCP",
            "zvertbot",
            "🌐 WORLD · ⚡ 5 new conn/min/IP",
            "world",
        )
    )

for item in XRAY_PASSPORT["reality"]:
    if item.get("port"):
        tcp_services.append(
            (
                item["port"],
                "TCP",
                "xray",
                f"🌐 WORLD · SNI {item['sni']}",
                "world",
            )
        )

print_port_table(
    "🔴 ВНЕШНИЙ ДОСТУП",
    tcp_services
    + [
        (
            port,
            "UDP",
            iface,
            "🌐 WORLD · AmneziaWG",
            "world",
        )
        for iface, port in discover_udp_ports()
    ],
)


# ============================================================
# Локальные сервисы.
# Порты берём из фактических LISTEN.
# ============================================================

local_services = []

for service_name, pattern in (
    ("stats-http", "stats-http"),
    ("healthcheck", "healthcheck"),
    ("kuma-webhook", "kuma-webhook"),
):
    port = discover_tcp_port(pattern)
    if port:
        local_services.append(
            (
                port,
                "TCP",
                service_name,
                "127.0.0.1 · Docker",
                "local",
            )
        )

api_port = XRAY_PASSPORT.get("api_port")
if api_port:
    local_services.append(
        (
            api_port,
            "TCP",
            "xray-api",
            "127.0.0.1 ONLY",
            "localhost",
        )
    )

print_port_table(
    "🔵 ЛОКАЛЬНЫЙ ДОСТУП",
    local_services,
)


docker_services = []

for name, port in discover_docker_ports():
    docker_services.append(
        (
            port,
            "TCP",
            name,
            f"127.0.0.1 · {HA_TUNNEL_IP}" if HA_TUNNEL_IP else "127.0.0.1",
            "docker",
        )
    )


print_port_table(
    "🟣 DOCKER",
    docker_services,
)


section("🛡️ БЕЗОПАСНОСТЬ И ДОСТУП (SSH)")
auth_keys = Path.home() / ".ssh" / "authorized_keys"

if auth_keys.exists():
    mode = oct(auth_keys.stat().st_mode)[-3:]

    if mode == "600":
        ok("SSH authorized_keys             права 600")
    else:
        fail(f"SSH authorized_keys             права {mode} (требуется 600)")
else:
    warn("SSH authorized_keys       ФАЙЛ НЕ НАЙДЕН")


ssh_password_auth = run(["sshd", "-T"])

if any(
    line.strip().lower() == "passwordauthentication no"
    for line in ssh_password_auth.splitlines()
):
    ok("SSH PasswordAuthentication OFF")
else:
    warn("SSH PasswordAuthentication НЕ ОТКЛЮЧЕН")


section("🌐 СЕТЬ И ЯДРО")

if "1" in run(["sysctl", "-n", "net.ipv4.ip_forward"]):
    ok("IPv4 forwarding           ВКЛЮЧЕН")
else:
    warn("IPv4 forwarding           ОТКЛЮЧЕН")


# Системный приоритет IPv4/IPv6
gai_conf = Path("/etc/gai.conf")

if gai_conf.exists():
    try:
        gai_config = any(
            line.strip().split() == ["precedence", "::ffff:0:0/96", "100"]
            for line in gai_conf.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    except OSError:
        gai_config = False

    if gai_config:
        ok("IPv4 priority             precedence ::ffff:0:0/96 100")
    else:
        warn("IPv4 priority                   не настроен")
else:
    warn("IPv4 priority             /etc/gai.conf НЕ НАЙДЕН")


if "262144" in run(["sysctl", "-n", "net.netfilter.nf_conntrack_max"]):
    ok("nf_conntrack_max          262144")
else:
    warn("nf_conntrack_max          != 262144")


if run(["systemctl", "is-active", "netfilter-persistent"]) == "active":
    ok("netfilter-persistent      РАБОТАЕТ")
else:
    warn("netfilter-persistent      НЕ АКТИВЕН")


section("⚙️ SYSTEMD OVERRIDES")
check_file("/etc/systemd/system/xray.service.d/limits.conf")
awg_overrides = sorted(
    Path("/etc/systemd/system").glob("awg-quick@*.service.d/override.conf")
)

for override in awg_overrides:
    check_file(override)


section("🗜️ ЛОГИ И ОБНОВЛЕНИЯ")

journald_conf = Path("/etc/systemd/journald.conf")

try:
    journald_config = any(
        line.strip() == "SystemMaxUse=100M"
        for line in journald_conf.read_text(encoding="utf-8").splitlines()
    )
except OSError:
    journald_config = False

if journald_config:
    ok("journald                  SystemMaxUse=100M")
else:
    warn("journald                  SystemMaxUse НЕ НАСТРОЕН")


unattended_conf = Path("/etc/apt/apt.conf.d/50unattended-upgrades")

try:
    unattended_config = any(
        "wireguard" in line.lower() and not line.lstrip().startswith("//")
        for line in unattended_conf.read_text(encoding="utf-8").splitlines()
    )
except OSError:
    unattended_config = False

if unattended_config:
    ok("unattended-upgrades        ЧЁРНЫЙ СПИСОК ВКЛЮЧЕН")
else:
    warn("unattended-upgrades           чёрный список не настроен")


section("💾 БЭКАПЫ")

rclone_conf = Path.home() / ".config" / "rclone" / "rclone.conf"

if rclone_conf.exists():
    ok(f"Файл: {rclone_conf}")
else:
    warn("rclone token               НЕ НАЙДЕН")


section("🔐 XRAY")
check_file(str(XRAY_CONF))

# Проверка конфигурации тем же бинарником Xray,
# который используется systemd. Xray при этом не запускается.
if XRAY_CONF.exists():
    xray_test = run(["/usr/local/bin/xray", "run", "-test", "-config", str(XRAY_CONF)])

    if "Configuration OK." in xray_test:
        ok("Xray configuration         ПРОВЕРЕН")
    else:
        fail("Xray configuration         НЕКОРРЕКТНО")
else:
    warn("Xray configuration         НЕ НАЙДЕН")

if run(["systemctl", "is-active", "xray.service"]) == "active":
    ok("Xray service              РАБОТАЕТ")
else:
    fail("Xray service              НЕ АКТИВЕН")


section("🛡 AMNEZIAWG")

if shutil.which("awg"):
    ok("awg binary                НАЙДЕН")
else:
    fail("awg binary                НЕ НАЙДЕН")


if run(["modinfo", "amneziawg"]):
    ok("kernel module amneziawg   ЗАГРУЖЕН")
else:
    warn("kernel module amneziawg   НЕ ЗАГРУЖЕН")


for iface in discover_awg_interfaces():
    if run(["awg", "show", iface]):
        ok(f"{iface} интерфейс АКТИВЕН")
    else:
        warn(f"{iface} интерфейс НЕ АКТИВЕН или не существует")


# ============================================================
# КОНВЕЙЕР ДАННЫХ HASS
# ============================================================

section("📡 КОНВЕЙЕР ДАННЫХ HASS")


def check_json_endpoint(url, name):
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            data = r.read().decode()

        obj = json.loads(data)

        return obj

    except (OSError, json.JSONDecodeError) as e:
        warn(f"{name:<25} ОШИБКА ДАННЫХ ({e})")
        return None


# ------------------------------------------------------------
# stats.json
# ------------------------------------------------------------

stats = check_json_endpoint(
    "http://127.0.0.1:8080/stats.json",
    "stats.json",
)

if stats:
    required_fields = (
        "services",
        "peers",
        "xray_clients",
    )

    missing_fields = [key for key in required_fields if key not in stats]

    if missing_fields:
        warn(
            "stats.json                "
            "НЕКОРРЕКТНО: отсутствуют " + ", ".join(missing_fields)
        )
    else:
        ok("stats.json                ПРОВЕРЕН")

    peers = stats.get("peers")

    if isinstance(peers, list):
        ok(f"AWG клиентов               {len(peers)}")
    else:
        warn("AWG клиентов               ДАННЫЕ НЕКОРРЕКТНЫ")

    xray_clients = stats.get("xray_clients")

    if isinstance(xray_clients, list):
        ok(f"Xray клиентов              {len(xray_clients)}")
    else:
        warn("Xray клиентов              ДАННЫЕ НЕКОРРЕКТНЫ")


# ------------------------------------------------------------
# healthcheck
# ------------------------------------------------------------

health = check_json_endpoint(
    "http://127.0.0.1:8081/status",
    "healthcheck",
)

if health:
    if health.get("status") in ("healthy", "ok"):
        ok("состояние healthcheck      НОРМА")
    else:
        warn(f"health status             {health.get('status')}")


section("📁 ФАЙЛЫ ДАННЫХ HASS")

for name, path in [
    (
        "stats.json",
        INSTALL_DIR / "hass/stats/stats.json",
    ),
    (
        "usage.json",
        INSTALL_DIR / "hass/traffic/usage.json",
    ),
    (
        "geoip.json",
        INSTALL_DIR / "hass/geo/geoip.json",
    ),
]:
    if path.exists():
        age = int(time.time() - path.stat().st_mtime)

        if age < 3600:
            ok(f"{name:<15} СВЕЖИЙ ({age}s)")
        else:
            warn(f"{name:<15} устарел ({age}s)")
    else:
        warn(f"{name:<15} отсутствует")


# ============================================================
# RESULT (В САМОМ КОНЦЕ)
# ============================================================

section("📊 РЕЗУЛЬТАТ")

total = OK + WARN + FAIL

print()
print(f"Всего проверок: {total}")
print(f"{GREEN}Успешно: {OK}{RESET}")
print(f"{YELLOW}Предупреждений: {WARN}{RESET}")
print(f"{RED}Ошибок: {FAIL}{RESET}")
print()

if FAIL:
    print("PASSPORT_STATUS: FAIL")
    print(f"{RED}{BOLD}❌ СЕРВЕР НЕ ГОТОВ (Есть критические ошибки){RESET}")
elif WARN:
    print("PASSPORT_STATUS: WARN")
    print(f"{YELLOW}{BOLD}⚠️ СЕРВЕР ГОТОВ С ПРЕДУПРЕЖДЕНИЯМИ (Требует внимания){RESET}")
else:
    print("PASSPORT_STATUS: READY")
    print(
        f"{GREEN}{BOLD}"
        "✅ СЕРВЕР ГОТОВ К ИСПОЛЬЗОВАНИЮ "
        "(Все проверки пройдены успешно)"
        f"{RESET}"
    )

print()

sys.exit(FAIL)
