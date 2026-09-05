"""
Модуль проверки репутации IP-адреса через AbuseIPDB API.
"""

from typing import Any

import requests

from config import SERVER_IP
from config.secrets import ABUSEIPDB_API_KEY
from utils.logger import logger


def check_ip_reputation(ip: str = None) -> dict[str, Any]:
    """
    Проверяет репутацию IP-адреса через AbuseIPDB.
    Возвращает словарь с результатами или ошибку.
    """
    target_ip = ip or SERVER_IP

    if not ABUSEIPDB_API_KEY:
        logger.error("ip_reputation.config.api_key_missing")
        return {"error": "API ключ не настроен"}

    url = "https://api.abuseipdb.com/api/v2/check"
    headers = {"Accept": "application/json", "Key": ABUSEIPDB_API_KEY}
    querystring = {"ipAddress": target_ip, "maxAgeInDays": "90"}

    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=10)
        response.raise_for_status()
        data = response.json().get("data", {})

        # Извлекаем ключевые метрики
        result = {
            "ip": data.get("ipAddress"),
            "country": data.get("countryCode"),
            "isp": data.get("isp"),
            "usageType": data.get("usageType"),
            "abuseConfidenceScore": data.get("abuseConfidenceScore", 0),
            "totalReports": data.get("totalReports", 0),
            "isWhitelisted": data.get("isWhitelisted", False),
            "lastReportedAt": data.get("lastReportedAt"),
        }

        logger.info(
            "ip_reputation.check.completed | ip=%s | score=%s | reports=%s",
            target_ip,
            result["abuseConfidenceScore"],
            result["totalReports"],
        )
        return result

    except requests.exceptions.RequestException as e:
        logger.error(
            "ip_reputation.check.failed | ip=%s | error=%s",
            target_ip,
            e,
        )
        return {"error": str(e)}
