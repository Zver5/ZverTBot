"""
services/port_scanner.py
Модуль для сканирования открытых портов и классификации.
Используется в Telegram-боте для аудита безопасности.
"""

import subprocess

from services.vps_monitor import _discover_awg_units
from services.xray.config_manager import get_vless_inbounds, load_xray_config
from utils.logger import logger


def _get_expected_ports() -> dict[str, dict[str, str]]:
    """Build expected ports from static services and current VPN configuration."""
    expected = {
        # TCP
        "22": {"proto": "TCP", "service": "sshd", "desc": "SSH управление"},
        "8080": {"proto": "TCP", "service": "stats-http", "desc": "Метрики VPS -> HA"},
        "10085": {"proto": "TCP", "service": "xray-api", "desc": "gRPC StatsService"},
        "3001": {"proto": "TCP", "service": "uptime-kuma", "desc": "Веб-дашборд Kuma"},
    }

    try:
        for index, inbound in enumerate(
            get_vless_inbounds(load_xray_config()), start=1
        ):
            if not isinstance(inbound, dict):
                continue

            try:
                port = str(int(inbound["port"]))
            except (KeyError, TypeError, ValueError):
                continue

            tag = inbound.get("tag") or f"VLESS inbound #{index}"
            expected[port] = {
                "proto": "TCP",
                "service": "xray",
                "desc": f"VLESS+REALITY ({tag})",
            }
    except Exception as e:
        logger.warning("port_scanner.xray_discovery.failed | error=%s", e)

    awg_units = _discover_awg_units()

    if awg_units:
        for unit in awg_units:
            interface = unit.split("@", 1)[1] if "@" in unit else unit

            try:
                result = subprocess.run(
                    ["awg", "show", interface],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            except Exception as e:
                logger.warning(
                    "port_scanner.awg_discovery.failed | unit=%s error=%s",
                    unit,
                    e,
                )
                continue

            if result.returncode != 0:
                continue

            for line in result.stdout.splitlines():
                if not line.strip().startswith("listening port:"):
                    continue

                port = line.split(":", 1)[1].strip()
                if port.isdigit():
                    expected[port] = {
                        "proto": "UDP",
                        "service": "amneziawg",
                        "desc": f"AmneziaWG ({interface})",
                    }
                break

    return expected


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
        expected_ports = _get_expected_ports()
        expected_found = []
        suspicious = []

        for p in open_ports:
            port = p["port"]
            if (
                port in expected_ports
                and p["proto"] == expected_ports[port]["proto"]
            ):
                exp = expected_ports[port]
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
