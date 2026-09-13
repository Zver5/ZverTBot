"""Модуль форматирования сообщений Telegram-бота.
Функции построения текстовых карточек клиентов вынесены из zvertbot.py.
"""

from config import SERVER_IP
from data.storage import load_awg_registry
from services.awg.config_generator import get_awg_port
from services.xray.link_generator import xray_get_sni_by_port


def build_client_card(username: str, proto: str) -> str:
    """
    Формирует текстовую карточку клиента после создания.

    Args:
        username: Имя клиента
        proto: Протокол ('vless' или 'awg')

    Returns:
        Отформатированный текст карточки (Markdown)
    """
    if proto == "vless":
        header = (
            f"✅ *Клиент успешно создан*\n"
            f"⚡ *Протокол:* VLESS (Reality)\n"
            f"👤 *Имя:* `{username}`\n"
        )

        try:
            sni_by_port = xray_get_sni_by_port()

            if not sni_by_port:
                return header

            servers = "".join(
                f"🌐 *Сервер {index}:* `{SERVER_IP}:{port}`\n🔹 SNI: `{sni}`\n"
                for index, (port, sni) in enumerate(sorted(sni_by_port.items()), 1)
            )

            return header + servers
        except Exception:
            return header
    else:
        ip = load_awg_registry().get(username, {}).get("ip", "N/A")
        return (
            f"✅ *Клиент успешно создан*\n"
            f"🛡 *Протокол:* AmneziaWG\n"
            f"👤 *Имя:* `{username}`\n"
            f"🌐 *Сервер:* `{SERVER_IP}:{get_awg_port()}`\n"
            f"📍 *Ваш IP:* `{ip}`\n"
            f"📥 *Выберите действие:*\n"
        )
