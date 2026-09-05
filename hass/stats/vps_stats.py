#!/usr/bin/env python3
import importlib.util
import json
import logging
import os
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
from utils.atomic import atomic_write  # noqa: E402

logger = logging.getLogger(__name__)

paths_file = PROJECT_ROOT / "config" / "paths.py"

spec = importlib.util.spec_from_file_location("paths", paths_file)

paths = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paths)

GEOIP_JSON = paths.GEOIP_JSON
USAGE_JSON = paths.USAGE_JSON
RCLONE_STATUS_JSON = paths.RCLONE_STATUS_JSON
STATS_JSON = paths.STATS_JSON
AWG_CONF = paths.AWG_CONF
XRAY_CONF = paths.XRAY_CONF
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
    """
    Автоматическое определение systemd сервисов.

    Возвращает:
    {
        "service": {
            "status": 1,
            "uptime": "15д 23ч",
        }
    }

    status:
    1  = работает
    0  = установлен, но остановлен
    -1 = не установлен
    """

    status = {}

    def get_service_uptime(service):
        """Вернуть краткое время работы active systemd-сервиса."""
        try:
            result = subprocess.run(
                ["systemctl", "show", service, "-p", "ActiveEnterTimestampMonotonic"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            value = result.stdout.strip().partition("=")[2]

            if not value.isdigit() or int(value) <= 0:
                return None

            now = int(
                subprocess.run(
                    ["cat", "/proc/uptime"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                .stdout.split()[0]
                .split(".")[0]
            )

            active_seconds = max(0, now - int(value) // 1_000_000)

            days, remainder = divmod(active_seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, _ = divmod(remainder, 60)

            if days:
                return f"{days}д {hours}ч"

            if hours:
                return f"{hours}ч {minutes}м"

            return f"{minutes}м"

        except Exception:
            return None

    # обычные сервисы
    services = ["xray", "stats-http", "zvertbot", "fail2ban"]

    for svc in services:
        try:
            exists = subprocess.run(
                ["systemctl", "list-unit-files", svc + ".service"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if svc + ".service" not in exists.stdout:
                status[svc] = {"status": -1, "uptime": None}
                continue

            active = subprocess.run(
                ["systemctl", "is-active", svc],
                capture_output=True,
                text=True,
                timeout=5,
            )

            is_active = active.stdout.strip() == "active"
            status[svc] = {
                "status": 1 if is_active else 0,
                "uptime": get_service_uptime(svc) if is_active else None,
            }

        except Exception:
            status[svc] = {"status": -1, "uptime": None}

    # ========================================================
    # AmneziaWG - поиск реально существующих экземпляров
    # ========================================================

    try:
        units = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all", "--no-legend"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        awg_found = []

        for line in units.stdout.splitlines():
            if "awg-quick@" in line:
                name = line.split()[0].replace(".service", "")
                awg_found.append(name)

        for awg in awg_found:
            active = subprocess.run(
                ["systemctl", "is-active", awg],
                capture_output=True,
                text=True,
                timeout=5,
            )

            is_active = active.stdout.strip() == "active"
            status[awg] = {
                "status": 1 if is_active else 0,
                "uptime": get_service_uptime(awg) if is_active else None,
            }

        if not awg_found:
            status["awg-quick@awg0"] = {"status": -1, "uptime": None}

    except Exception:
        status["awg-quick@awg0"] = {"status": -1, "uptime": None}

    return status


# =================================================


# --- Xray real client IP from access.log ---
def get_xray_online_ips():
    result = {}

    try:
        log_file = XRAY_ACCESS_LOG

        if not os.path.exists(log_file):
            return result

        with open(log_file, errors="ignore") as f:
            lines = f.readlines()[-500:]

        for line in lines:
            m = re.search(r"from ([0-9.]+):\d+ .*email: ([^\s]+)", line)

            if m:
                ip = m.group(1)
                name = m.group(2)

                result[name] = ip

    except Exception as e:
        logger.warning("vps_stats.xray_access_log.read_failed | error=%s", e)

    return result


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
    global wg_peers
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
    # --- 1. Трафик (из usage.json, только VPN-клиенты) ---
    vpn_total_gb = 0
    try:
        with open(USAGE_JSON) as f:
            usage_data = json.load(f)
            vpn_total_bytes = sum(
                c.get("total", 0) for c in usage_data.get("clients", {}).values()
            )
            vpn_total_gb = round(vpn_total_bytes / 1073741824, 2)
    except Exception:
        vpn_total_gb = 0


    # --- 2. AmneziaWG ---
    # --- 2. AmneziaWG ---
    config_peers = []

    if AWG_CONF.exists():
        cur = {"name": "Unknown", "key": "", "ip": ""}
        pending_name = None

        with open(AWG_CONF) as conf_file:
            for line in conf_file:
                line = line.strip()
                if not line:
                    continue

                if line.startswith("#"):
                    if "Name:" in line:
                        pending_name = line.split("Name:", 1)[1].strip()

                elif line.lower() == "[peer]":
                    if cur["key"]:
                        config_peers.append(cur)

                    cur = {"name": pending_name or "Unknown", "key": "", "ip": ""}
                    pending_name = None

                elif line.lower().startswith("publickey"):
                    cur["key"] = re.sub(r"\s+", "", line.split("=", 1)[1])

                elif line.lower().startswith("allowed"):
                    cur["ip"] = line.split("=", 1)[1].strip().split("/")[0]

        if cur["key"]:
            config_peers.append(cur)

    live_peers = {}
    cur = {}
    for line in run(["awg", "show", "awg0"]).split("\n"):
        s = line.strip()
        low = s.lower()
        if low.startswith("peer:"):
            if cur.get("key"):
                live_peers[cur["key"]] = cur
            cur = {
                "key": re.sub(r"\s+", "", s.split(":", 1)[1]),
                "endpoint": "",
                "ip": "",
                "hs": "never",
                "rx": 0.0,
                "tx": 0.0,
            }
        elif low.startswith("endpoint"):
            val = s.split(":", 1)[1].strip()
            cur["endpoint"] = "" if val in ["(none)", "(no endpoint)", "-"] else val
        elif "allowed" in low and "ip" in low:
            cur["ip"] = s.split(":", 1)[1].strip().split("/")[0]
        elif "handshake" in low:
            cur["hs"] = fmt_hs(s.split("latest handshake:", 1)[1].strip())
        elif low.startswith("transfer"):
            rx = re.search(r"([\d.]+)\s*(KiB|MiB|GiB|B)\s*received", s)
            tx = re.search(r"([\d.]+)\s*(KiB|MiB|GiB|B)\s*sent", s)
            if rx:
                v, u = float(rx.group(1)), rx.group(2)
                cur["rx"] = (
                    v
                    if u == "GiB"
                    else v / 1024
                    if u == "MiB"
                    else v / 1048576
                    if u == "KiB"
                    else v / 1073741824
                )
            if tx:
                v, u = float(tx.group(1)), tx.group(2)
                cur["tx"] = (
                    v
                    if u == "GiB"
                    else v / 1024
                    if u == "MiB"
                    else v / 1048576
                    if u == "KiB"
                    else v / 1073741824
                )
    if cur.get("key"):
        live_peers[cur["key"]] = cur

    # Получаем точные времена handshake (unix timestamp) для надежной проверки online
    hs_times = {}
    try:
        hs_out = subprocess.run(
            ["awg", "show", "awg0", "latest-handshakes"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
        for line in hs_out.split("\n"):
            if "\t" in line:
                key, ts = line.split("\t")
                hs_times[key.strip()] = int(ts)
    except Exception as e:
        logger.warning("vps_stats.awg.handshake_check_failed | error=%s", e)

    wg_peers = []
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
            if lp["endpoint"]:
                p["endpoint"] = lp["endpoint"]
                p["last_ip"] = lp["endpoint"].split(":")[0]
            if lp["ip"]:
                p["ip"] = lp["ip"]
            p["hs"] = lp["hs"]
            p["rx"] = fmt_size(lp["rx"])
            p["tx"] = fmt_size(lp["tx"])
            p["total_bytes"] = (lp["rx"] + lp["tx"]) * 1073741824  # ГБ → байты
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
            p["total_bytes"] = 0
            p["online"] = False
            p["last_seen"] = "never"
        # Добавляем GeoIP данные
        p["geoip"] = geoip_data.get(c["name"], {})
        wg_peers.append(p)

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
                    jail.strip()
                    for jail in match.group(1).split(",")
                    if jail.strip()
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
        with open(XRAY_CONF) as f:
            cfg = json.load(f)
        for ib in cfg.get("inbounds", []):
            if ib.get("protocol") in ["vmess", "vless", "shadowsocks", "trojan"]:
                if not xray_port:
                    xray_port = ib.get("port")
                for cl in ib.get("settings", {}).get("clients", []):
                    xray_clients_raw.append(
                        {"name": cl.get("email", "Unknown"), "id": cl.get("id")}
                    )
    except Exception as e:
        logger.warning("vps_stats.xray_config.load_failed | error=%s", e)

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

    # Читаем usage.json для получения реальных дельт трафика и статуса online
    usage_data = {}
    try:
        with open(USAGE_JSON) as f:
            usage_data = json.load(f)
    except Exception as e:
        logger.warning("vps_stats.xray_usage.read_failed | error=%s", e)

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
                "total": fmt_size(client_usage.get("total", 0)),
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
        "peers": wg_peers,
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
