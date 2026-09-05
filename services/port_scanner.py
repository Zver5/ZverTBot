"""
services/port_scanner.py
Модуль для сканирования открытых портов и классификации.
Используется в Telegram-боте для аудита безопасности.
"""

import subprocess

from utils.logger import logger

# Ожидаемые порты (из SERVER-PASSPORT.md)
EXPECTED_PORTS = {
    # TCP внешние
    "22": {"proto": "TCP", "service": "sshd", "desc": "SSH управление"},
    "443": {"proto": "TCP", "service": "xray", "desc": "VLESS+REALITY MTS"},
    "2096": {"proto": "TCP", "service": "xray", "desc": "VLESS+REALITY Beeline"},
    "8085": {"proto": "TCP", "service": "zvertbot", "desc": "Telegram-бот"},
    # UDP внешние
    "58352": {"proto": "UDP", "service": "amneziawg", "desc": "AmneziaWG основной"},
    "5802": {"proto": "UDP", "service": "amneziawg", "desc": "AmneziaWG тестовый"},
    "51878": {"proto": "UDP", "service": "wireguard", "desc": "WireGuard обычный"},
    # TCP локальные
    "8080": {"proto": "TCP", "service": "stats-http", "desc": "Метрики VPS -> HA"},
    "8081": {"proto": "TCP", "service": "healthcheck", "desc": "Healthcheck для Kuma"},
    "8082": {"proto": "TCP", "service": "kuma-webhook", "desc": "Webhook для Kuma"},
    "10085": {"proto": "TCP", "service": "xray-api", "desc": "gRPC StatsService"},
    # Docker
    "3001": {"proto": "TCP", "service": "uptime-kuma", "desc": "Веб-дашборд Kuma"},
}


def scan_open_ports():
    """Сканирует открытые порты и классифицирует их"""
    try:
        # Сканируем TCP порты
        tcp_result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        tcp_lines = tcp_result.stdout.strip().split("\n")[1:]  # Пропускаем заголовок

        # Сканируем UDP порты
        udp_result = subprocess.run(
            ["ss", "-ulnp"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        udp_lines = udp_result.stdout.strip().split("\n")[1:]  # Пропускаем заголовок

        # Парсим открытые порты
        open_ports = []

        for line in tcp_lines:
            parts = line.split()
            if len(parts) >= 4:
                state = parts[0] if parts else ""
                if state != "LISTEN":
                    continue  # Пропускаем established/исходящие соединения
                addr = parts[3]
                if ":" in addr:
                    port = addr.split(":")[-1]
                    proc = "unknown"
                    if "users:" in line:
                        proc_part = line.split("users:")[1].split(")")[0]
                        if "((" in proc_part:
                            proc = proc_part.split("((")[1].split(",")[0]
                    open_ports.append({"port": port, "proto": "TCP", "proc": proc})

        for line in udp_lines:
            parts = line.split()
            if len(parts) >= 4:
                addr = parts[3]
                if ":" in addr:
                    if addr.startswith("*:"):
                        continue
                    if not (addr.startswith("0.0.0.0:") or addr.startswith("[::]:")):
                        continue
                    port = addr.split(":")[-1]
                    proc = "unknown"
                    if "users:" in line:
                        proc_part = line.split("users:")[1].split(")")[0]
                        if "((" in proc_part:
                            proc = proc_part.split("((")[1].split(",")[0]
                    open_ports.append({"port": port, "proto": "UDP", "proc": proc})

        # Убираем дубликаты
        unique_ports = {}
        for p in open_ports:
            key = (p["port"], p["proto"])
            if key not in unique_ports:
                unique_ports[key] = p
        open_ports = list(unique_ports.values())

        # Классифицируем порты
        expected_found = []
        suspicious = []

        for p in open_ports:
            port = p["port"]
            if port in EXPECTED_PORTS:
                exp = EXPECTED_PORTS[port]
                expected_found.append(
                    {
                        "port": port,
                        "proto": p["proto"],
                        "service": exp["service"],
                        "desc": exp["desc"],
                        "proc": p["proc"],
                    }
                )
            else:
                suspicious.append(
                    {"port": port, "proto": p["proto"], "proc": p["proc"]}
                )

        # Формируем текст
        text = "🔍 *Результат сканирования портов*\n"
        text += "✅ *Открытые порты (ожидаемые):*\n"
        for p in sorted(expected_found, key=lambda x: int(x["port"])):
            text += (
                f"• `{p['port']}/{p['proto'].lower()}` ({p['service']}) — {p['desc']}\n"
            )

        if suspicious:
            text += "\n⚠️ *Подозрительные порты:*\n"
            for p in sorted(suspicious, key=lambda x: int(x["port"])):
                text += f"• `{p['port']}/{p['proto'].lower()}` — процесс: {p['proc']}\n"
        else:
            text += "\n✅ *Подозрительных портов не обнаружено*\n"

        text += "\n━━━━━━━━━━━━━━━━━━━━━\n"
        text += "📊 *Статистика:*\n"
        text += f"• Всего открытых: {len(open_ports)}\n"
        text += f"• Ожидаемых: {len(expected_found)}\n"
        text += f"• Подозрительных: {len(suspicious)}\n"

        return text
    except Exception as e:
        logger.error("port_scanner.scan.failed | error=%s", e)
        return f"❌ Ошибка сканирования: {e}"
