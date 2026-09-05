#!/usr/bin/env python3
# xray-traffic-collect.py — v7.0 (Cumulative: Xray VLESS + AmneziaWG)
import importlib.util
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

import grpc

from utils.atomic import atomic_write
from utils.client_operation_lock import client_operation_lock
from utils.logger import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]

paths_file = PROJECT_ROOT / "config" / "paths.py"

spec = importlib.util.spec_from_file_location("paths", paths_file)

paths = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paths)

TRAFFIC_DIR = paths.TRAFFIC_DIR
DATA_DIR = paths.DATA_DIR
USAGE_JSON = paths.USAGE_JSON
ARCHIVE_JSON = paths.ARCHIVE_JSON
AWG_USERS_JSON = paths.AWG_USERS_JSON


XRAY_CONF = paths.XRAY_CONF


def sync_and_archive(data):
    """Синхронизирует usage.json с реальными конфигами и архивирует удаленных"""
    try:
        active_users = set()
        # Собираем активных Xray
        if XRAY_CONF.exists():
            with open(XRAY_CONF) as f:
                cfg = json.load(f)
                for inb in cfg.get("inbounds", []):
                    if inb.get("protocol") == "vless":
                        for c in inb.get("settings", {}).get("clients", []):
                            if c.get("email"):
                                active_users.add(c["email"])
        # Собираем активных AWG
        if AWG_USERS_JSON.exists():
            with open(AWG_USERS_JSON) as f:
                for name in json.load(f):
                    active_users.add(name)

        clients = data.get("clients", {})
        archive_file = ARCHIVE_JSON

        # Переносим "призраков" в архив
        ghosts = [n for n in list(clients.keys()) if n not in active_users]
        if ghosts:
            if os.path.exists(archive_file):
                with open(archive_file) as archive_file_obj:
                    archive = json.load(archive_file_obj)
            else:
                archive = {}
            for ghost in ghosts:
                archive[ghost] = clients.pop(ghost)
                print(f"📦 {ghost} перенесен в архив")
            content = json.dumps(archive, indent=2)
            atomic_write(archive_file, content)

        # Добавляем новичков, которых нет в stats
        for user in active_users:
            if user not in clients:
                proto = "vless"
                if AWG_USERS_JSON.exists():
                    with open(AWG_USERS_JSON) as awg_users_file:
                        awg_users = json.load(awg_users_file)
                    if user in awg_users:
                        proto = "awg"
                clients[user] = {
                    "uplink": 0,
                    "downlink": 0,
                    "total": 0,
                    "_snap_up": 0,
                    "_snap_down": 0,
                    "proto": proto,
                }
                print(f"🆕 {user} добавлен в мониторинг ({proto})")

        data["clients"] = clients
    except Exception as e:
        print(f"Ошибка sync_and_archive: {e}")


API = "127.0.0.1:10085"
OUT = USAGE_JSON
LOG = str(paths.XRAY_TRAFFIC_LOG)
AWG_REGISTRY = AWG_USERS_JSON


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"[{datetime.now().isoformat()}] {msg}\n")


def query_xray_stat(name):
    try:
        ch = grpc.insecure_channel(API)
        method = "/v2ray.core.app.stats.command.StatsService/QueryStats"
        req = b"\x0a" + bytes([len(name)]) + name.encode() + b"\x10\x00"
        resp = ch.unary_unary(method)(req, timeout=2)
        m = re.search(rb"\x10([\x80-\xff]*[\x00-\x7f])", resp)
        if m:
            val, shift = 0, 0
            for b in m.group(1):
                val |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break
            return val
        return 0
    except Exception as e:
        logger.exception("xray_traffic.query.failed | error=%s", e)
        return 0


def parse_size(s):
    if not s:
        return 0
    s = s.strip().lower()
    for w in ["received", "sent"]:
        s = s.replace(w, "")
    s = s.strip()
    units = {"gib": 1024**3, "mib": 1024**2, "kib": 1024, "b": 1}
    for u, mult in units.items():
        if u in s:
            try:
                return int(float(s.replace(u, "").strip()) * mult)
            except Exception as e:
                logger.exception("xray_traffic.parse_size.failed | error=%s", e)
                return 0
    try:
        return int(float(s))
    except Exception as e:
        logger.exception("xray_traffic.parse_size.convert_failed | error=%s", e)
        return 0


def get_awg_raw_stats():
    res = {}
    try:
        if os.path.exists(AWG_REGISTRY):
            with open(AWG_REGISTRY) as registry_file:
                reg = json.load(registry_file)
        else:
            reg = {}
        out = subprocess.run(
            ["awg", "show", "awg0"],
            capture_output=True,
            text=True,
        ).stdout
        lines = out.split("\n")
        for name, data in reg.items():
            ip = data.get("ip")
            if not ip:
                continue
            rx = tx = 0
            for i, line in enumerate(lines):
                if ip in line and "allowed ips" in line:
                    for j in range(i, min(i + 5, len(lines))):
                        current_line = lines[j].strip()
                        if "transfer:" in current_line:
                            parts = current_line.split(":")[1].split(",")
                            if len(parts) >= 2:
                                rx = parse_size(parts[0].strip())
                                tx = parse_size(
                                    parts[1].strip().replace("sent", "").strip()
                                )
                    break
            res[name] = {"up": rx, "down": tx}
    except Exception as e:
        log(f"AWG parse err: {e}")
    return res


def get_xray_last_ips():
    result = {}

    try:
        log_file = paths.XRAY_ACCESS_LOG

        if not os.path.exists(log_file):
            return result

        with open(log_file, errors="ignore") as f:
            lines = f.readlines()[-1000:]

        for line in lines:
            m = re.search(r"from ([0-9.]+):\d+ .*email: ([^\s]+)", line)

            if m:
                ip = m.group(1)
                name = m.group(2)
                result[name] = ip

    except Exception as e:
        log(f"IP parse error: {e}")

    return result


@client_operation_lock
def collect():
    old = {}
    if os.path.exists(OUT):
        try:
            with open(OUT) as f:
                old = json.load(f)
        except Exception as e:
            logger.exception("xray_traffic.collect.load_failed | error=%s", e)

    ts = datetime.now().isoformat()
    xray_last_ips = get_xray_last_ips()
    new = {"updated": ts, "clients": old.get("clients", {}).copy()}
    old_cl = old.get("clients", {})

    # Динамическое получение списка Xray клиентов из config.json
    xray_users = []
    if XRAY_CONF.exists():
        with open(XRAY_CONF) as f:
            cfg = json.load(f)
            for inb in cfg.get("inbounds", []):
                if inb.get("protocol") == "vless":
                    for c in inb.get("settings", {}).get("clients", []):
                        if c.get("email"):
                            xray_users.append(c["email"])

    for u in xray_users:
        r_up = query_xray_stat(f"user>>>{u}>>>traffic>>>uplink")
        r_dn = query_xray_stat(f"user>>>{u}>>>traffic>>>downlink")
        h = old_cl.get(u, {})
        s_up = h.get("uplink", 0)
        s_dn = h.get("downlink", 0)
        ls_up = h.get("_snap_up", r_up)
        ls_dn = h.get("_snap_down", r_dn)
        d_up = r_up - ls_up if r_up >= ls_up else r_up
        d_dn = r_dn - ls_dn if r_dn >= ls_dn else r_dn
        f_up = s_up + d_up
        f_dn = s_dn + d_dn
        delta = d_up + d_dn

        client_data = {
            "uplink": f_up,
            "downlink": f_dn,
            "total": f_up + f_dn,
            "last_ip": xray_last_ips.get(u, h.get("last_ip", "")),
            "_snap_up": r_up,
            "_snap_down": r_dn,
            "_delta": delta,
            "proto": "vless",
        }

        # Сохраняем последнее реальное время активности Xray-клиента.
        # При offline старое значение не затирается.
        if delta > 100:
            client_data["last_seen"] = ts
        else:
            client_data["last_seen"] = h.get("last_seen", "never")

        new["clients"][u] = client_data
        log(f"Xray {u}: raw={r_up}/{r_dn} -> total={f_up}/{f_dn}")

    awg = get_awg_raw_stats()

    for u, stat in awg.items():
        r_up = stat["up"]
        r_dn = stat["down"]

        h = old_cl.get(u, {})

        old_up = h.get("uplink", 0)
        old_dn = h.get("downlink", 0)

        snap_up = h.get("_snap_up", r_up)
        snap_dn = h.get("_snap_down", r_dn)

        delta_up = r_up - snap_up
        delta_dn = r_dn - snap_dn

        if delta_up < 0:
            delta_up = r_up

        if delta_dn < 0:
            delta_dn = r_dn

        total_up = old_up + delta_up
        total_dn = old_dn + delta_dn

        new["clients"][u] = {
            "uplink": total_up,
            "downlink": total_dn,
            "total": total_up + total_dn,
            "_snap_up": r_up,
            "_snap_down": r_dn,
            "_delta": delta_up + delta_dn,
            "proto": "awg",
        }

        log(
            f"AWG {u}: "
            f"raw={r_up}/{r_dn} "
            f"delta={delta_up}/{delta_dn} "
            f"total={total_up}/{total_dn}"
        )

    sync_and_archive(new)
    content = json.dumps(new, indent=2)
    atomic_write(OUT, content)
    log("✓ v7.0 saved")


if __name__ == "__main__":
    collect()
