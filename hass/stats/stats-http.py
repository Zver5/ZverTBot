#!/usr/bin/env python3
import http.server
import json
import os
import socketserver

from config.paths import (
    AWG_USERS_JSON,
    GEOIP_JSON,
    STATS_JSON,
    USAGE_JSON,
)


def fmt_traffic(b):
    """Умное форматирование: <1 ГБ → МБ, ≥1 ГБ → ГБ"""
    try:
        b = float(b)
        if b >= 1073741824:
            return f"{b / 1073741824:.2f} GB"
        if b >= 1048576:
            return f"{b / 1048576:.0f} MB"
        return f"{b / 1024:.0f} KB"
    except Exception:
        return "0 KB"


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/stats.json":
            self.send_response(404)
            self.end_headers()
            return

        result = {}

        # 1. Базовая статистика (CPU, RAM, Disk, Live Peers)
        if os.path.exists(STATS_JSON):
            try:
                with open(STATS_JSON) as f:
                    result = json.load(f)
            except Exception:
                pass

        # 2. Загружаем GeoIP данные
        geoip_data = {}
        if os.path.exists(GEOIP_JSON):
            try:
                with open(GEOIP_JSON) as f:
                    geoip_data = json.load(f)
            except Exception:
                pass

        # 3. Накопительный трафик из usage.json
        if os.path.exists(USAGE_JSON):
            try:
                with open(USAGE_JSON) as f:
                    usage = json.load(f)
                clients = usage.get("clients", {})

                # --- AWG clients (из stats.json → peers → total_bytes) ---
                awg_clients = []
                awg_registry = {}
                if os.path.exists(AWG_USERS_JSON):
                    try:
                        with open(AWG_USERS_JSON) as reg:
                            awg_registry = json.load(reg)
                    except Exception:
                        pass

                # Берём трафик из stats.json → peers (там есть total_bytes)
                peers = result.get("peers", [])
                for peer in peers:
                    name = peer.get("name")
                    if not name:
                        continue

                    # Проверяем что это AWG-клиент (есть в awg_registry)
                    if name not in awg_registry:
                        continue

                    # Берём total_bytes из peers (накопительный трафик)
                    total_bytes = peer.get("total_bytes", 0)

                    # Разделяем на rx/tx (примерно 50/50, т.к. в peers нет разделения)
                    # В реальности нужно брать из usage.json если есть
                    usage_stats = clients.get(name, {})
                    down = usage_stats.get("downlink", 0)
                    up = usage_stats.get("uplink", 0)

                    # Если в usage.json 0, используем total_bytes из peers
                    if down == 0 and up == 0 and total_bytes > 0:
                        # Предполагаем 70% download, 30% upload (типично для VPN)
                        down = int(total_bytes * 0.7)
                        up = int(total_bytes * 0.3)

                    ip = awg_registry.get(name, {}).get("ip", "N/A")
                    total = down + up
                    client_data = {
                        "name": name,
                        "ip": ip,
                        "proto": "awg",
                        "rx": fmt_traffic(down),
                        "tx": fmt_traffic(up),
                        "downlink": down,
                        "uplink": up,
                        "total": fmt_traffic(total),
                    }
                    # Добавляем GeoIP если есть
                    if name in geoip_data:
                        client_data["geoip"] = geoip_data[name]
                    awg_clients.append(client_data)
                result["awg_clients"] = awg_clients

                # --- Xray clients (накопительно + online по _delta) ---
                xray_clients = []

                for name, stats in clients.items():
                    if stats.get("proto") != "vless":
                        continue

                    down = stats.get("downlink", 0)
                    up = stats.get("uplink", 0)
                    total = down + up
                    delta = stats.get("_delta", 0)

                    # Активен, если передал >100 байт за последние 5 мин.
                    is_online = delta > 100

                    last_ip = stats.get("last_ip", "")
                    last_seen = stats.get("last_seen", "never")

                    client_data = {
                        "name": name,
                        "ip": last_ip,
                        "last_ip": last_ip,
                        "endpoint": "active" if is_online else "offline",
                        "proto": "vless",
                        "rx": fmt_traffic(down),
                        "tx": fmt_traffic(up),
                        "downlink": down,
                        "uplink": up,
                        "total": fmt_traffic(total),
                        "online": is_online,
                        "hs": "active" if is_online else "offline",
                        "last_seen": last_seen,
                    }

                    # Добавляем GeoIP если есть
                    if name in geoip_data:
                        client_data["geoip"] = geoip_data[name]

                    xray_clients.append(client_data)

                result["xray_clients"] = xray_clients

            except Exception as e:
                print(f"Usage parse error: {e}")

        # 4. Отдаём JSON
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())

    def log_message(self, *a):
        pass


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


with ThreadingTCPServer(("127.0.0.1", 8080), Handler) as httpd:
    print("Stats HTTP Server started on 8080")
    httpd.serve_forever()
