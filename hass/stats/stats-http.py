#!/usr/bin/env python3
import http.server
import json
import socketserver

from services.vps_status import build_vps_status
from services.vps_status_source import (
    DEFAULT_MAX_STATS_AGE_SECONDS,
    is_stats_payload_fresh,
    load_prepared_vps_payload,
    stats_payload_age_seconds,
)


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/vps-status.json":
            self.send_response(404)
            self.end_headers()
            return

        raw = load_prepared_vps_payload()
        if not raw:
            self._send_json(503, {"error": "vps_stats_unavailable"})
            return

        if not is_stats_payload_fresh(
            raw,
            max_age_seconds=DEFAULT_MAX_STATS_AGE_SECONDS,
        ):
            age = stats_payload_age_seconds(raw)
            details = {
                "error": "vps_stats_stale",
                "max_age_seconds": DEFAULT_MAX_STATS_AGE_SECONDS,
                "age_seconds": None if age is None else int(age),
            }
            self._send_json(503, details)
            return

        result = build_vps_status(raw).to_dict()
        self._send_json(200, result)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


with ThreadingTCPServer(("127.0.0.1", 8080), Handler) as httpd:
    print("Stats HTTP Server started on 8080")
    httpd.serve_forever()
