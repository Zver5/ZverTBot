"""
Утилиты общего назначения для ZverTBot.
Модуль НЕ зависит от VPN-логики, только от telebot (safe_delete).
"""


import requests
from telebot.apihelper import ApiTelegramException

from utils.logger import logger


def escape_md(text):
    """
    Экранирование спецсимволов Markdown для Telegram.
    """
    if not text:
        return ""

    chars = r"_*[]`"

    for ch in chars:
        text = text.replace(ch, "\\" + ch)

    return text


def _telegram_call_with_retry(func, *args, **kwargs):
    """Повторяет Telegram API-вызов при временной сетевой ошибке."""
    for attempt in range(3):
        try:
            return func(*args, **kwargs)
        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        ):
            if attempt == 2:
                raise

    return None


def safe_answer_callback(
    bot,
    callback_id,
    text=None,
    show_alert=False,
):
    """Безопасно подтверждает callback Telegram."""
    if not callback_id:
        return

    try:
        kwargs = {}
        args = [callback_id]

        if text is not None:
            args.append(text)

        if show_alert:
            kwargs["show_alert"] = True

        _telegram_call_with_retry(
            bot.answer_callback_query,
            *args,
            **kwargs,
        )
    except Exception as e:
        err = str(e)
        if (
            "query is too old" not in err
            and "response timeout expired" not in err
            and "query ID is invalid" not in err
        ):
            logger.warning(
                "telegram.callback.answer_failed | error=%s",
                e,
            )


def safe_send_message(
    bot,
    chat_id: int,
    text: str,
    *,
    replace_message_id=None,
    **kwargs,
) -> bool:
    """Безопасно отправляет сообщение Telegram.

    Ошибки отправки не прерывают основной сценарий обработчика.
    Временные сетевые ошибки повторяются через общий retry-механизм.

    Args:
        replace_message_id: Старый message_id, который нужно заменить
            новым ID отправленного сообщения во всех словарях состояния.

    Returns:
        True если сообщение отправлено, False если Telegram/API вернул ошибку.
    """
    try:
        msg = _telegram_call_with_retry(
            bot.send_message,
            chat_id,
            text,
            **kwargs,
        )

        if replace_message_id is not None:
            from core.state import replace_message_id as update_state_message_id

            update_state_message_id(
                chat_id,
                replace_message_id,
                msg.message_id,
            )

        return True
    except Exception as e:
        try:
            logger.warning(
                "telegram.message.send_failed | error=%s",
                e,
            )
        except Exception:
            pass

        return False


def safe_delete(bot, chat_id: int, message_id: int) -> bool:
    """Безопасное удаление сообщения Telegram (игнорирует ошибки).

    Подавляет все исключения (message not found, message too old и т.д.),
    чтобы не засорять логи и не прерывать выполнение обработчиков.

    Args:
        bot: Экземпляр TeleBot
        chat_id: ID чата
        message_id: ID сообщения

    Returns:
        True если удалено, False если ошибка (игнорируется)
    """
    try:
        _telegram_call_with_retry(
            bot.delete_message,
            chat_id,
            message_id,
        )
        return True
    except Exception:
        return False


def safe_edit_message_reply_markup(
    bot,
    chat_id: int,
    message_id: int,
    **kwargs,
) -> bool:
    """Безопасно изменяет inline-клавиатуру сообщения Telegram."""
    try:
        _telegram_call_with_retry(
            bot.edit_message_reply_markup,
            chat_id,
            message_id,
            **kwargs,
        )
        return True
    except Exception as e:
        try:
            logger.warning(
                "telegram.message.reply_markup_edit_failed | error=%s",
                e,
            )
        except Exception:
            pass

        return False


def safe_send_document(bot, chat_id: int, document, **kwargs) -> bool:
    """Безопасно отправляет документ Telegram."""
    try:
        _telegram_call_with_retry(
            bot.send_document,
            chat_id,
            document,
            **kwargs,
        )
        return True
    except Exception as e:
        try:
            logger.warning(
                "telegram.document.send_failed | error=%s",
                e,
            )
        except Exception:
            pass

        return False


def normalize_client_list(client_list) -> list:
    """Нормализует список клиентов из bindings (строка → список).

    Обрабатываетlegacy-формат, где привязка хранилась как строка:
        "5118270802": "Boiko"
    Приводит к единому формату:
        "5118270802": ["Boiko"]

    Args:
        client_list: Список клиентов (может быть str, list, None)

    Returns:
        Всегда list (возможно пустой)
    """
    if not isinstance(client_list, list):
        return [client_list] if client_list else []
    return client_list


def fmt_traffic(bytes_value: int) -> str:
    """Форматирует байты в человекочитаемый вид (B/KB/MB/GB).

    Унифицированная функция форматирования трафика.
    Заменяет внутренние функции fmt() в get_client_stats_text и generate_weekly_report.

    Args:
        bytes_value: Количество байт

    Returns:
        Строка вида "1.23 GB", "456.78 MB", "12 KB", "500 B"
    """
    if bytes_value >= 1073741824:  # 1 GB
        return f"{bytes_value / 1073741824:.2f} GB"
    if bytes_value >= 1048576:  # 1 MB
        return f"{bytes_value / 1048576:.2f} MB"
    if bytes_value >= 1024:  # 1 KB
        return f"{bytes_value / 1024:.0f} KB"
    return f"{bytes_value} B"


def safe_edit_message(bot, text, cid, message_id, **kwargs):
    """
    Безопасное редактирование сообщения Telegram.
    Не ломает фоновые потоки при ошибках API.
    """
    try:
        _telegram_call_with_retry(
            bot.edit_message_text,
            text,
            cid,
            message_id,
            **kwargs,
        )
        return True

    except ApiTelegramException as e:
        description = (getattr(e, "description", "") or "").lower()

        if description == "bad request: message is not modified":
            return True

        if description == "bad request: message to edit not found":
            try:
                replacement = _telegram_call_with_retry(
                    bot.send_message,
                    cid,
                    text,
                    **kwargs,
                )
                new_message_id = getattr(replacement, "message_id", None)

                if new_message_id is None:
                    return False

                from core.state import replace_message_id

                replace_message_id(message_id, new_message_id)
                return True
            except Exception as fallback_error:
                try:
                    logger.error(
                        "telegram.message.edit_fallback_failed | error=%s",
                        fallback_error,
                    )
                except Exception:
                    pass

                return False

        try:
            logger.error(
                "telegram.message.edit_failed | error=%s",
                e,
            )
        except Exception:
            pass

        return False

    except Exception as e:
        try:
            logger.error(
                "telegram.message.edit_failed | error=%s",
                str(e)[:300],
            )
        except Exception:
            pass

        return False
