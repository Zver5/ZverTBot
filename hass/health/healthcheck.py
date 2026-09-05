#!/usr/bin/env python3

import http.server
import json
import os
import shutil
import socketserver
import subprocess
import urllib.request
from datetime import datetime, timezone

from config.secrets import HA_TUNNEL_IP
from utils.logger import logger

SERVICES = {
    "xray": {
        "required": False,
        "systemd": "xray.service",
        "proto": "tcp",
        "port": 443,
    },
    "amnezia_wg": {
        "required": False,
        "systemd": "awg-quick@awg0.service",
        "proto": "udp",
        "port": 58352,
    },
    "stats_http": {
        "required": True,
        "systemd": "stats-http.service",
        "proto": "tcp",
        "port": 8080,
        "http": "http://127.0.0.1:8080/stats.json",
    },
    "ssh": {
        "required": True,
        "systemd": "ssh.service",
        "proto": "tcp",
        "port": 22,
    },
    "fail2ban": {
        "required": True,
        "systemd": "fail2ban.service",
    },
}


def cmd(args):

    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=5)
    except subprocess.TimeoutExpired:
        logger.error("healthcheck.command.timeout | args=%s", args)
        return None
    except Exception as e:
        logger.exception("healthcheck.command.failed | error=%s", e)
        return None


def check_systemd(service):

    r = cmd(["systemctl", "is-active", service])

    return bool(r and r.stdout.strip() == "active")


def check_port(proto, port):

    flag = "-tlnp" if proto == "tcp" else "-ulnp"

    r = cmd(["ss", flag])

    if not r:
        return False

    return f":{port} " in r.stdout


def check_http(url):

    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status == 200

    except Exception as e:
        logger.exception("healthcheck.http.failed | error=%s", e)
        return False


def check_tunnel():

    if not HA_TUNNEL_IP:
        return True

    r = cmd(["ss", "-tn"])

    if not r:
        return False

    for line in r.stdout.splitlines():
        fields = line.split()

        if len(fields) < 5 or fields[0] != "ESTAB":
            continue

        local_addr = fields[3]
        remote_addr = fields[4]

        if not local_addr.endswith(":22"):
            continue

        if remote_addr.startswith(f"{HA_TUNNEL_IP}:"):
            return True

    return False


def system_info():

    disk = shutil.disk_usage("/")

    return {
        "load": os.getloadavg()[0],
        "ram": int(
            (1 - os.sysconf("SC_AVPHYS_PAGES") / os.sysconf("SC_PHYS_PAGES")) * 100
        ),
        "disk": int(disk.used / disk.total * 100),
    }


def run_checks():

    checks = {}
    failed = []

    for name, cfg in SERVICES.items():
        item = {"status": "ok"}

        if "systemd" in cfg:
            ok = check_systemd(cfg["systemd"])

            item["systemd"] = "active" if ok else "failed"

            if not ok:
                item["status"] = "fail"

                if cfg.get("required", True):
                    failed.append({"service": name, "reason": "systemd inactive"})

        if "port" in cfg:
            ok = check_port(cfg["proto"], cfg["port"])

            item["port"] = "open" if ok else "closed"

            if not ok:
                item["status"] = "fail"

                if cfg.get("required", True):
                    failed.append({"service": name, "reason": "port closed"})

        if "http" in cfg:
            ok = check_http(cfg["http"])

            item["http"] = "OK" if ok else "FAILED"

        checks[name] = item

    if HA_TUNNEL_IP:
        tunnel = check_tunnel()

        checks["ha_tunnel"] = {"status": "ok" if tunnel else "fail"}

        if not tunnel:
            checks["ha_tunnel"]["reason"] = "SSH tunnel disconnected"
            failed.append(
                {
                    "service": "ha_tunnel",
                    "reason": "SSH tunnel disconnected",
                }
            )

    return {
        "status": "healthy" if not failed else "degraded",
        "failed": failed,
        "checks": checks,
        "system": system_info(),
        "time": datetime.now(timezone.utc).isoformat(),
    }, not failed


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):

        if self.path != "/status":
            self.send_response(404)
            self.end_headers()
            return

        data, ok = run_checks()

        self.send_response(200 if ok else 503)

        self.send_header("Content-Type", "application/json")

        self.end_headers()

        self.wfile.write(json.dumps(data, indent=2).encode())

    def log_message(self, *args):
        pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    print("Smart healthcheck v1.2.4 :8081", flush=True)

    Server(("0.0.0.0", 8081), Handler).serve_forever()
