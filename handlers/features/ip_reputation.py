"""
Обработчик проверки репутации IP-адреса.
"""

from telebot import types

from config import SERVER_IP
from core.callback_response import CallbackResponse
from core.navigation import NAV_BACK_CALLBACK, navigation
from services.network.ip_reputation import check_ip_reputation
from ui.screens import IP_REPUTATION
from utils.error_handler import handle_errors


def render_ip_reputation(bot, cid, message_id):
    """Отрисовать репутацию IP-адреса."""
    result = check_ip_reputation()

    if "error" in result:
        return bot.edit_message_text(
            f"❌ Ошибка проверки репутации:\n{result['error']}",
            cid,
            message_id,
        )

    score = result.get("abuseConfidenceScore", 0)
    reports = result.get("totalReports", 0)
    is_whitelisted = result.get("isWhitelisted", False)

    if score == 0:
        status = "✅ Чистый"
        status_emoji = "🟢"
    elif score < 25:
        status = "⚠️ Низкий риск"
        status_emoji = "🟡"
    elif score < 50:
        status = "⚠️ Средний риск"
        status_emoji = "🟠"
    else:
        status = "🚨 Высокий риск"
        status_emoji = "🔴"

    if is_whitelisted:
        status = "✅ В белом списке"
        status_emoji = "🟢"

    message = f"""🌐 РЕПУТАЦИЯ IP-АДРЕСА

{status_emoji} **Статус:** {status}

🔹 **IP:** `{result.get("ip", SERVER_IP)}`
🔹 **Страна:** {result.get("country", "N/A")}
🔹 **Провайдер:** {result.get("isp", "N/A")}
🔹 **Тип использования:** {result.get("usageType", "N/A")}

📊 **Метрики:**
• Abuse Score: {score}%
• Всего жалоб: {reports}
• В белом списке: {"Да" if is_whitelisted else "Нет"}

🕐 Последняя жалоба: {result.get("lastReportedAt", "Нет данных")}"""

    if score >= 50:
        message += (
            "\n\n💡 **Рекомендация:** Высокий риск блокировки. "
            "Рассмотрите смену IP или усиление обфускации."
        )
    elif score >= 25:
        message += (
            "\n\n💡 **Рекомендация:** Умеренный риск. Мониторьте жалобы клиентов."
        )

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            "↩️ Назад",
            callback_data=NAV_BACK_CALLBACK,
        )
    )

    return bot.edit_message_text(
        message,
        cid,
        message_id,
        reply_markup=kb,
        parse_mode="Markdown",
    )


@handle_errors("Ошибка в handle_ip_reputation_callback")
def handle_ip_reputation_callback(bot, cid, call, data):
    """Обрабатывает навигацию проверки репутации IP."""
    if data != "ip_reputation":
        return False

    screen_id = IP_REPUTATION
    if navigation.current(cid) != screen_id:
        navigation.go(cid, screen_id)

    navigation.render(screen_id, bot, cid, call.message.message_id)
    return CallbackResponse("Проверяю репутацию IP...")
