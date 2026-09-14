#!/usr/bin/env python3
import importlib.util
import json
import logging
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from config import SERVER_IP
from config.secrets import HA_TUNNEL_IP as SOCKS5_IP  # noqa: E402
from services.awg.config_manager import get_awg_peers
from services.xray.config_manager import get_all_clients, load_xray_config
from utils.atomic import atomic_write  # noqa: E402
from utils.service_control import (
    get_service_state,
    get_service_uptime_seconds,
    list_service_units,
    service_exists,
)

logger = logging.getLogger(__name__)

paths_file = PROJECT_ROOT / "config" / "paths.py"

spec = importlib.util.spec_from_file_location("paths", paths_file)

paths = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paths)

GEOIP_JSON = paths.GEOIP_JSON
USAGE_JSON = paths.USAGE_JSON
RCLONE_STATUS_JSON = paths.RCLONE_STATUS_JSON
STATS_JSON = paths.STATS_JSON
XRAY_ACCESS_LOG = paths.XRAY_ACCESS_LOG


def run(args):
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        ).stdout.strip()
    except Exception:
        return ""


# --- GeoIP Data ---
def load_geoip_data():
    """Загружает GeoIP данные из geoip.json"""
    try:
        with open(GEOIP_JSON) as f:
            return json.load(f)
    except Exception:
        return {}


# === НОВАЯ ФУНКЦИЯ: статус systemd-сервисов ===
def get_services_status():
    """Возвращает статус основных и обнаруженных AWG systemd-сервисов."""
    status = {}

    def format_uptime(seconds):
        if seconds is None:
            return None

        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)

        if days:
            return f"{days}д {hours}ч"
        if hours:
            return f"{hours}ч {minutes}м"
        return f"{minutes}м"

    def build_status(service, *, known_exists=False):
        if not known_exists and not service_exists(service):
            return {"status": -1, "uptime": None}

        state = get_service_state(service)
        is_active = state == "active"

        return {
            "status": 1 if is_active else 0,
            "uptime": (
                format_uptime(get_service_uptime_seconds(service))
                if is_active
                else None
            ),
        }

    for service in ["xray", "stats-http", "zvertbot", "fail2ban"]:
        status[service] = build_status(service)

    awg_units = [
        unit for unit in list_service_units()
        if "awg-quick@" in unit
    ]

    for unit in awg_units:
        status[unit] = build_status(unit, known_exists=True)

    if not awg_units:
        status["awg-quick@awg0"] = {"status": -1, "uptime": None}

    return status


# =================================================


# --- Xray real client IP from access.log ---
def get_xray_online_ips():
    try:
        from services.xray.access_log import get_last_client_ips

        return get_last_client_ips(XRAY_ACCESS_LOG, 500)
    except Exception as e:
        logger.warning("vps_stats.xray_access_log.read_failed | error=%s", e)
        return {}


def fmt_hs(raw):
    if not raw or "never" in raw.lower():
        return "never"
    raw = raw.replace(" ago", "").strip().lower()
    sec = 0
    for unit, mult in [("day", 86400), ("hour", 3600), ("min", 60), ("sec", 1)]:
        m = re.search(r"(\d+)\s*" + unit, raw)
        if m:
            sec += int(m.group(1)) * mult
    if sec < 60:
        return f"{sec}sec"
    if sec < 3600:
        return f"{sec // 60}min"
    if sec < 86400:
        return f"{sec // 3600}hour"
    return f"{sec // 86400}day"


def fmt_size(bytes_val):
    if not isinstance(bytes_val, (int, float)) or bytes_val <= 0:
        return "0 Б"
    if bytes_val < 1024:
        return f"{int(bytes_val)} Б"
    elif bytes_val < 1048576:
        return f"{bytes_val / 1024:.2f} КБ"
    elif bytes_val < 1073741824:
        return f"{bytes_val / 1048576:.2f} МБ"
    else:
        return f"{bytes_val / 1073741824:.2f} ГБ"


def clean_ip(ip):
    if not ip:
        return "offline"
    ip = ip.strip("[]")
    if "::ffff:" in ip:
        ip = ip.split("::ffff:")[-1]
    return ip


def collect_stats():
    """Собирает статистику VPS и сохраняет её в STATS_JSON."""
    global geoip_data
    global vpn_total_gb
    global config_peers
    global live_peers
    global hs_times
    global awg_clients
    global f2b_stats
    global xray_port
    global xray_clients_raw
    global ip_data
    global all_conns
    global xray_clients
    global xray_ips
    global usage_data
    global rclone_status
    global server_ip
    global stats_data
    global content

    geoip_data = load_geoip_data()

    # --- 1. Трафик ---
    vpn_total_gb = 0
    usage_data = {}
    usage_clients = {}

    try:
        with open(USAGE_JSON) as f:
            usage_data = json.load(f)

        if not isinstance(usage_data, dict):
            usage_data = {}

        usage_clients = usage_data.get("clients", {})
        if not isinstance(usage_clients, dict):
            usage_clients = {}

        vpn_total_bytes = sum(
            c.get("total", 0)
            for c in usage_clients.values()
            if isinstance(c, dict)
        )
        vpn_total_gb = round(vpn_total_bytes / 1073741824, 2)
    except Exception as exc:
        logger.warning("vps_stats.usage.read_failed | error=%s", exc)

    # --- 2. AmneziaWG ---
    try:
        config_peers = [
            {
                "name": peer.name,
                "key": peer.public_key,
                "ip": peer.allowed_ip,
            }
            for peer in get_awg_peers()
        ]
    except OSError as exc:
        logger.warning("vps_stats.awg_config.load_failed | error=%s", exc)
        config_peers = []

    from services.awg.runtime import extract_endpoint_ip, get_runtime_peers

    try:
        live_peers = get_runtime_peers()
    except Exception as exc:
        logger.warning("vps_stats.awg_runtime.load_failed | error=%s", exc)
        live_peers = {}

    from services.awg.runtime import get_latest_handshakes

    hs_times = get_latest_handshakes() if live_peers else {}

    awg_clients = []
    for c in config_peers:
        p = {
            "name": c["name"],
            "ip": c["ip"],
            "endpoint": "offline",
            "last_ip": "",
            "rx": "0 ГБ",
            "tx": "0 ГБ",
            "hs": "never",
        }
        lp = live_peers.get(c["key"])
        if lp:
            if lp.endpoint:
                p["endpoint"] = lp.endpoint
                p["last_ip"] = extract_endpoint_ip(lp.endpoint) or ""
            if lp.allowed_ip:
                p["ip"] = lp.allowed_ip
            p["hs"] = fmt_hs(lp.latest_handshake)

            usage_stats = usage_clients.get(c["name"], {})
            if not isinstance(usage_stats, dict):
                usage_stats = {}

            downlink = usage_stats.get("downlink", 0)
            uplink = usage_stats.get("uplink", 0)
            total_bytes = downlink + uplink

            p["rx"] = fmt_size(downlink)
            p["tx"] = fmt_size(uplink)
            p["downlink"] = downlink
            p["uplink"] = uplink
            p["total"] = fmt_size(total_bytes)
            p["total_bytes"] = total_bytes

            # Надежная проверка online:
            # handshake был и он был менее 300 секунд (5 мин) назад
            current_time = int(time.time())
            last_hs = hs_times.get(c["key"], 0)
            p["online"] = (last_hs > 0) and ((current_time - last_hs) < 300)
            p["last_seen"] = (
                time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(last_hs))
                if last_hs > 0
                else "never"
            )
        else:
            usage_stats = usage_clients.get(c["name"], {})
            if not isinstance(usage_stats, dict):
                usage_stats = {}

            downlink = usage_stats.get("downlink", 0)
            uplink = usage_stats.get("uplink", 0)
            total_bytes = downlink + uplink

            p["rx"] = fmt_size(downlink)
            p["tx"] = fmt_size(uplink)
            p["downlink"] = downlink
            p["uplink"] = uplink
            p["total"] = fmt_size(total_bytes)
            p["total_bytes"] = total_bytes
            p["online"] = False
            p["last_seen"] = "never"
        # Добавляем GeoIP данные
        p["geoip"] = geoip_data.get(c["name"], {})
        p["proto"] = "awg"
        awg_clients.append(p)

    # --- 3. Fail2Ban ---
    f2b_stats = {"total_banned": 0, "currently_banned": 0}
    try:
        result = subprocess.run(
            ["fail2ban-client", "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )

        if result.returncode == 0:
            match = re.search(r"Jail list:\s*(.+)", result.stdout)
            if match:
                jails = [
                    jail.strip() for jail in match.group(1).split(",") if jail.strip()
                ]

                total = current = 0

                for jail in jails:
                    result = subprocess.run(
                        ["fail2ban-client", "status", jail],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=5,
                    )

                    j_stat = result.stdout

                    cm = re.search(r"Currently banned:\s+(\d+)", j_stat)
                    tm = re.search(r"Total banned:\s+(\d+)", j_stat)

                    if cm:
                        current += int(cm.group(1))
                    if tm:
                        total += int(tm.group(1))

                f2b_stats["currently_banned"] = current
                f2b_stats["total_banned"] = total
    except Exception as e:
        logger.warning("vps_stats.fail2ban.status_check_failed | error=%s", e)

    # --- 4. Настройки ---

    xray_port = None
    xray_clients_raw = []
    try:
        cfg = load_xray_config()
        for client in get_all_clients(cfg):
            xray_clients_raw.append(
                {"name": client["name"], "id": client["id"]}
            )

        for inbound in cfg.get("inbounds", []):
            if inbound.get("protocol") in {"vmess", "vless", "shadowsocks", "trojan"}:
                if inbound.get("port") is not None:
                    xray_port = inbound["port"]
                    break
    except (FileNotFoundError, ValueError) as exc:
        logger.warning("vps_stats.xray_config.load_failed | error=%s", exc)

    # --- 5. Сбор соединений ---
    ip_data = {}
    ss_lines = run(["ss", "-tnip"]).split("\n")
    current_conn = None

    for line in ss_lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("ESTAB"):
            parts = line.split()
            if len(parts) >= 5:
                current_conn = {"local": parts[3], "peer": parts[4], "rx": 0, "tx": 0}
        elif "bytes_received" in line and current_conn:
            rx_m = re.search(r"bytes_received:(\d+)", line)
            tx_m = re.search(r"bytes_acked:(\d+)", line)
            if rx_m:
                current_conn["rx"] += int(rx_m.group(1))
            if tx_m:
                current_conn["tx"] += int(tx_m.group(1))

            local_port = (
                current_conn["local"].rsplit(":", 1)[-1]
                if ":" in current_conn["local"]
                else ""
            )
            peer_ip = clean_ip(current_conn["peer"].rsplit(":", 1)[0])

            service_type = None

            # HA SSH tunnel with SOCKS5 proxy (-D 1080)
            # Это специально наш Home Assistant туннель
            if local_port == "22" and peer_ip == SOCKS5_IP:
                service_type = "HA-Tunnel"

            # Xray исключён из активных туннелей
            # Клиенты Xray отображаются отдельно через xray_clients

            if service_type:
                key = (peer_ip, service_type)
                if key not in ip_data:
                    ip_data[key] = {"rx": 0, "tx": 0, "port": local_port}
                ip_data[key]["rx"] += current_conn["rx"]
                ip_data[key]["tx"] += current_conn["tx"]
            current_conn = None

    # --- 6. Формирование списков ---
    all_conns = []

    for (ip, service), data in ip_data.items():
        rx_bytes = data["rx"]
        tx_bytes = data["tx"]

        if data["rx"] + data["tx"] > 1024:
            entry = {
                "name": service,
                "ip": ip,
                "port": data.get("port", "-"),
                "rx": fmt_size(rx_bytes),
                "tx": fmt_size(tx_bytes),
                "hs": "active",
            }
            all_conns.append(entry)

    # --- 7. Xray Clients ---

    # --- 7. Xray clients (с online по _delta из usage.json) ---
    xray_clients = []

    # Реальные IP клиентов из Xray access.log
    xray_ips = get_xray_online_ips()

    for cl in xray_clients_raw:
        name = cl["name"]
        client_usage = usage_data.get("clients", {}).get(name, {})
        delta = client_usage.get("_delta", 0)
        is_online = delta > 100  # Активен, если передал >100 байт за последние 5 мин

        last_seen = client_usage.get("last_seen", "never")

        if is_online:
            last_seen = time.strftime(
                "%d.%m.%Y %H:%M:%S",
                time.localtime(),
            )

        xray_clients.append(
            {
                "name": name,
                "ip": xray_ips.get(name, ""),
                "last_ip": xray_ips.get(name, client_usage.get("last_ip", "")),
                "endpoint": "active" if is_online else "offline",
                "rx": fmt_size(client_usage.get("downlink", 0)),
                "tx": fmt_size(client_usage.get("uplink", 0)),
                "downlink": client_usage.get("downlink", 0),
                "uplink": client_usage.get("uplink", 0),
                "total": fmt_size(
                    client_usage.get("downlink", 0)
                    + client_usage.get("uplink", 0)
                ),
                "total_bytes": (
                    client_usage.get("downlink", 0)
                    + client_usage.get("uplink", 0)
                ),
                "online": is_online,
                "hs": "active" if is_online else "offline",
                "last_seen": last_seen,
                "geoip": geoip_data.get(name, {}),
            }
        )

    # --- 8. Rclone backup status ---
    rclone_status = {
        "status": "unknown",
        "last_backup": "never",
        "size_mb": 0,
        "next_run": "unknown",
    }
    try:
        with open(RCLONE_STATUS_JSON) as f:
            rclone_status = json.load(f)
    except Exception as e:
        logger.warning("vps_stats.rclone_status.read_failed | error=%s", e)

    # --- Public IP сервера ---
    server_ip = SERVER_IP or "unknown"

    # --- 9. Вывод JSON (ДОБАВЛЕНО: "services") ---
    stats_data = {
        "cpu": float(run(["awk", "{print $1}", "/proc/loadavg"]) or 0),
        "mem": (
            lambda lines: (
                round(float(lines[1].split()[2]) / float(lines[1].split()[1]) * 100, 1)
                if len(lines) > 1 and len(lines[1].split()) >= 3
                else 0
            )
        )(run(["free"]).splitlines()),
        "disk": (
            lambda s: {
                "used_gb": round((s.f_blocks - s.f_bfree) * s.f_frsize / 1024**3, 2),
                "total_gb": round(s.f_blocks * s.f_frsize / 1024**3, 2),
                "free_gb": round(s.f_bfree * s.f_frsize / 1024**3, 2),
                "percent": int((s.f_blocks - s.f_bfree) / s.f_blocks * 100),
            }
        )(__import__("os").statvfs("/")),
        "vpn_total_gb": vpn_total_gb,
        "server_ip": server_ip,
        "awg_clients": awg_clients,
        "xray_clients": xray_clients,
        "connections": all_conns,
        "fail2ban": f2b_stats,
        "rclone": rclone_status,
        "services": get_services_status(),
        "check_timestamp": datetime.now(ZoneInfo("Europe/Moscow")).strftime(
            "%d.%m.%Y %H:%M:%S"
        ),
        "vps_stats_last_check": datetime.now(ZoneInfo("Europe/Moscow")).isoformat(),
    }
    content = json.dumps(stats_data, indent=2)
    atomic_write(STATS_JSON, content)
    return stats_data


if __name__ == "__main__":
    collect_stats()
