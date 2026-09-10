#!/usr/bin/env python3
import http.server
import json
import socketserver

from services.vps_status import build_vps_status
from services.vps_status_source import load_prepared_vps_payload


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
        if self.path not in ("/stats.json", "/vps-status.json"):
            self.send_response(404)
            self.end_headers()
            return

        result = load_prepared_vps_payload()

        # 4. New stable public VPS contract for Home Assistant.
        if self.path == "/vps-status.json":
            result = build_vps_status(result).to_dict()

        # 5. Отдаём JSON
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
