#!/usr/bin/env python3
"""
GeoIP collector v2.

Источники:
    DB-IP City Lite  -> страна, регион, город, координаты
    DB-IP ASN Lite   -> ASN, организация
    asn_types.json   -> локальная классификация и emoji

Результат:
    hass/geo/geoip.json

Особенности:
    - никаких HTTP-запросов к GeoIP API;
    - MMDB читается локально;
    - сохраняются клиентские поля;
    - GeoIP обновляется только при изменении IP;
    - запись geoip.json атомарная;
    - ASN классифицируются только по локальной базе asn_types.json;
    - неизвестные ASN не изменяют локальную базу автоматически;
    - IPv4 и IPv6 поддерживаются.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import maxminddb

from utils.atomic import atomic_write
from utils.logger import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from config.paths import (  # noqa: E402
    ASN_DB_PATH,
    AWG_USERS_JSON,
    GEOIP_ASN_DB,
    GEOIP_CITY_DB,
    GEOIP_JSON,
    LOG_DIR,
    XRAY_ACCESS_LOG,
)

LOG_FILE = LOG_DIR / "geoip-collect.log"
AWG_USERS_PATH = AWG_USERS_JSON


logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


UNKNOWN_GEO = {
    "country": "Unknown",
    "city": "Unknown",
    "lat": "Unknown",
    "lon": "Unknown",
}


# ------------------------------------------------------------------
# JSON helpers
# ------------------------------------------------------------------


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as exc:
        logger.error("geoip.json.read_failed | path=%s | error=%s", path, exc)
        return default


def atomic_write_json(path: Path, data: Any) -> None:
    """
    Безопасно заменяет JSON-файл через общий atomic_write().
    """
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    atomic_write(path, content)


def get_awg_users_map() -> dict[str, str]:
    """PublicKey -> имя клиента."""
    users = load_json(AWG_USERS_PATH, {})

    if not isinstance(users, dict):
        return {}

    result: dict[str, str] = {}

    for name, data in users.items():
        if not isinstance(data, dict):
            continue

        pubkey = data.get("pubkey")

        if pubkey:
            result[str(pubkey)] = str(name)

    return result


def extract_endpoint_ip(endpoint: str) -> str | None:
    """
    Извлекает IP из WireGuard endpoint.

    Поддерживает:
        1.2.3.4:12345
        [2001:db8::1]:12345
        1.2.3.4
        2001:db8::1
    """
    endpoint = endpoint.strip()

    if not endpoint or endpoint == "(none)":
        return None

    if endpoint.startswith("["):
        end = endpoint.find("]")

        candidate = endpoint[1:end] if end != -1 else endpoint

    elif endpoint.count(":") == 1:
        candidate = endpoint.rsplit(":", 1)[0]

    elif endpoint.count(":") > 1:
        # IPv6 без порта
        candidate = endpoint

    else:
        candidate = endpoint

    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def get_awg_peers() -> dict[str, str]:
    """Получает endpoint IP подключённых AWG peers."""
    peers: dict[str, str] = {}

    try:
        result = subprocess.run(
            ["awg", "show", "awg0", "endpoints"],
            capture_output=True,
            text=True,
            check=True,
        )

        for line in result.stdout.splitlines():
            parts = line.split("\t", 1)

            if len(parts) != 2:
                continue

            pubkey, endpoint = parts

            ip = extract_endpoint_ip(endpoint)

            if ip:
                peers[pubkey] = ip

    except FileNotFoundError:
        logger.warning("geoip.awg.command_not_found")
    except subprocess.CalledProcessError as exc:
        logger.error("geoip.awg.endpoints_command_failed | error=%s", exc)
    except Exception as exc:
        logger.error("geoip.awg.endpoints_failed | error=%s", exc)

    return peers


# ------------------------------------------------------------------
# Xray
# ------------------------------------------------------------------


XRAY_LOG_PATTERN = re.compile(
    r"from\s+(\[[0-9a-fA-F:]+\]|[0-9.]+):\d+\s+accepted.*?email:\s+(\S+)"
)


def get_xray_clients_from_log() -> dict[str, str]:
    """
    Берёт последние подключения Xray из access.log.

    Возвращает:
        email -> последний IP
    """
    clients: dict[str, str] = {}

    if not XRAY_ACCESS_LOG.exists():
        return clients

    try:
        result = subprocess.run(
            ["tail", "-n", "5000", str(XRAY_ACCESS_LOG)],
            capture_output=True,
            text=True,
            check=True,
        )

        for line in result.stdout.splitlines():
            match = XRAY_LOG_PATTERN.search(line)

            if not match:
                continue

            raw_ip, email = match.groups()
            ip = raw_ip.strip("[]")

            try:
                ip = str(ipaddress.ip_address(ip))
            except ValueError:
                continue

            clients[email] = ip

    except FileNotFoundError:
        logger.warning("geoip.xray.tail_command_not_found")
    except subprocess.CalledProcessError as exc:
        logger.error("geoip.xray.log_read_failed | error=%s", exc)
    except Exception as exc:
        logger.error("geoip.xray.log_parse_failed | error=%s", exc)

    return clients


# ------------------------------------------------------------------
# ASN database
# ------------------------------------------------------------------


def load_asn_types() -> dict[str, dict[str, Any]]:
    data = load_json(ASN_DB_PATH, {})

    if not isinstance(data, dict):
        return {}

    return data


# ------------------------------------------------------------------
# MMDB
# ------------------------------------------------------------------


def get_city_data(
    ip: str,
    city_db: maxminddb.extension.Reader,
) -> dict[str, str]:
    result = dict(UNKNOWN_GEO)

    try:
        data = city_db.get(ip)

        if not isinstance(data, dict):
            return result

        country = data.get("country", {})
        city = data.get("city", {})
        location = data.get("location", {})

        country_names = country.get("names", {})
        city_names = city.get("names", {})

        result["country"] = (
            country.get("iso_code")
            or country_names.get("ru")
            or country_names.get("en")
            or "Unknown"
        )

        result["city"] = city_names.get("ru") or city_names.get("en") or "Unknown"

        lat = location.get("latitude")
        lon = location.get("longitude")

        if lat is not None:
            result["lat"] = str(lat)

        if lon is not None:
            result["lon"] = str(lon)

        return result

    except Exception as exc:
        logger.error("geoip.city_mmdb.lookup_failed | ip=%s | error=%s", ip, exc)
        return result


def get_asn_data(
    ip: str,
    asn_db: maxminddb.extension.Reader,
) -> tuple[str, str]:
    """
    Возвращает:
        ASN, organization
    """
    try:
        data = asn_db.get(ip)

        if not isinstance(data, dict):
            return "Unknown", "Unknown"

        number = data.get("autonomous_system_number")
        org = data.get("autonomous_system_organization")

        asn = f"AS{number}" if number else "Unknown"

        return asn, str(org or "Unknown")

    except Exception as exc:
        logger.error("geoip.asn_mmdb.lookup_failed | ip=%s | error=%s", ip, exc)
        return "Unknown", "Unknown"


def classify_ip(
    ip: str,
    city_db: maxminddb.extension.Reader,
    asn_db: maxminddb.extension.Reader,
    cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Полная классификация IP.

    Один IP -> один MMDB lookup за запуск.
    """
    if ip in cache:
        return cache[ip]

    try:
        ipaddress.ip_address(ip)
    except ValueError:
        info = {
            "type": "unknown",
            "emoji": "❓",
            "isp": "Unknown",
            "country": "Unknown",
            "city": "Unknown",
            "lat": "Unknown",
            "lon": "Unknown",
            "asn": "Unknown",
        }

        cache[ip] = info
        return info

    geo = get_city_data(ip, city_db)
    asn, org = get_asn_data(ip, asn_db)

    info = {
        "type": "unknown",
        "emoji": "📶",
        "isp": org,
        "country": geo["country"],
        "city": geo["city"],
        "lat": geo["lat"],
        "lon": geo["lon"],
        "asn": asn,
    }

    cache[ip] = info

    return info


# ------------------------------------------------------------------
# Client records
# ------------------------------------------------------------------


def apply_asn_classification(
    record: dict[str, Any],
    asn_types: dict[str, dict[str, Any]],
) -> bool:
    """
    Обновляет type/emoji существующей записи
    по локальной базе ASN без MMDB lookup.

    Возвращает True, если классификация изменилась.
    """
    asn = record.get("asn")
    manual = asn_types.get(asn)

    if manual:
        new_type = manual.get("type", "unknown")
        new_emoji = manual.get("emoji", "📶")
    else:
        new_type = "unknown"
        new_emoji = "📶"

    changed = record.get("type") != new_type or record.get("emoji") != new_emoji

    if changed:
        record["type"] = new_type
        record["emoji"] = new_emoji

    return changed


def build_client_record(
    old: dict[str, Any],
    ip: str,
    protocol: str,
    pubkey: str | None,
    info: dict[str, Any],
) -> dict[str, Any]:
    """
    Обновляет только GeoIP-составляющую,
    сохраняя важные поля старой записи.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    record = dict(old)

    record["ip"] = ip
    record["protocol"] = protocol

    if pubkey:
        record["pubkey"] = pubkey

    record.update(
        {
            "country": info["country"],
            "city": info["city"],
            "isp": info["isp"],
            "type": info["type"],
            "emoji": info["emoji"],
            "asn": info["asn"],
            "lat": info["lat"],
            "lon": info["lon"],
            "last_update": now,
        }
    )

    return record


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main() -> None:
    if not GEOIP_CITY_DB.exists():
        logger.error("geoip.config.city_db_not_found | path=%s", GEOIP_CITY_DB)
        print(f"ERROR: City DB not found: {GEOIP_CITY_DB}")
        return

    if not GEOIP_ASN_DB.exists():
        logger.error("geoip.config.asn_db_not_found | path=%s", GEOIP_ASN_DB)
        print(f"ERROR: ASN DB not found: {GEOIP_ASN_DB}")
        return

    asn_types = load_asn_types()
    geoip_data = load_json(GEOIP_JSON, {})

    if not isinstance(geoip_data, dict):
        geoip_data = {}

    awg_users_map = get_awg_users_map()
    awg_peers = get_awg_peers()
    xray_clients = get_xray_clients_from_log()

    city_db = maxminddb.open_database(str(GEOIP_CITY_DB))
    asn_db = maxminddb.open_database(str(GEOIP_ASN_DB))

    cache: dict[str, dict[str, Any]] = {}
    updated_count = 0

    try:
        # ============================================================
        # AWG
        # ============================================================

        for pubkey, ip in awg_peers.items():
            client_name = awg_users_map.get(pubkey, pubkey[:8])

            old = geoip_data.get(client_name, {})

            if old.get("ip") == ip:
                # IP не изменился — GeoIP lookup не нужен.
                continue

            info = classify_ip(
                ip,
                city_db,
                asn_db,
                cache,
            )

            geoip_data[client_name] = build_client_record(
                old=old,
                ip=ip,
                protocol="awg",
                pubkey=pubkey,
                info=info,
            )

            updated_count += 1

        # ============================================================
        # XRAY
        # ============================================================

        for email, ip in xray_clients.items():
            old = geoip_data.get(email, {})

            if old.get("ip") == ip:
                # IP не изменился — GeoIP lookup не нужен.
                continue

            info = classify_ip(
                ip,
                city_db,
                asn_db,
                cache,
            )

            geoip_data[email] = build_client_record(
                old=old,
                ip=ip,
                protocol="xray",
                pubkey=None,
                info=info,
            )

            updated_count += 1

        # ============================================================
        # APPLY GEOIP LOCATION ACCURACY
        # ============================================================
        #
        # Для мобильных операторов GeoIP показывает точку выхода
        # мобильной сети, а не обязательно фактическое положение
        # телефона. Поэтому такая география считается приблизительной.
        #
        MOBILE_ASN_TYPES = {
            "mobile",
            "cellular",
            "wireless",
        }

        for _record_name, _record in geoip_data.items():
            if not isinstance(_record, dict):
                continue

            if _record.get("protocol") not in ("awg", "xray"):
                continue

            _type = str(_record.get("type", "")).lower()

            if _type in MOBILE_ASN_TYPES:
                _record["mobile"] = True
                _record["accuracy"] = "approximate"
                _record["location_source"] = "geoip"
            else:
                _record["mobile"] = False
                _record["accuracy"] = "normal"
                _record["location_source"] = "geoip"

        # END GEOIP LOCATION ACCURACY

        # ============================================================
        # APPLY LOCAL ASN CLASSIFICATION
        # ============================================================
        #
        # IP/GeoIP здесь уже не проверяем.
        # Меняем только type/emoji по локальной базе ASN.
        # Это позволяет менять классификацию без нового GeoIP lookup.
        #
        for _record_name, record in geoip_data.items():
            if not isinstance(record, dict):
                continue

            if record.get("protocol") not in ("awg", "xray"):
                continue

            if apply_asn_classification(record, asn_types):
                updated_count += 1

        # END LOCAL ASN CLASSIFICATION
    finally:
        city_db.close()
        asn_db.close()

    atomic_write_json(GEOIP_JSON, geoip_data)

    logger.info(
        "geoip.collect.completed | updated=%s | total=%s | unique_ips=%s",
        updated_count,
        len(geoip_data),
        len(cache),
    )

    print(
        f"GeoIP v2: updated={updated_count}, "
        f"total={len(geoip_data)}, unique_ips={len(cache)}"
    )


if __name__ == "__main__":
    main()
