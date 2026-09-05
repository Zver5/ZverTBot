"""
Единый обработчик исключений ZverTBot.
"""

import functools

from telebot.apihelper import ApiTelegramException

from utils.logger import logger

# Ошибки Telegram, которые являются штатными последствиями
# гонок callback/message lifecycle и не требуют ERROR traceback.
EXPECTED_TELEGRAM_ERRORS = {
    "bad request: message is not modified",
    "bad request: message to edit not found",
    "bad request: query is too old and response timeout expired or query id is invalid",
}


def _get_error_context(args, kwargs):
    """Собирает диагностический контекст вызова."""

    context = []

    cid = None
    if len(args) >= 2:
        cid = args[1]
    if cid is None:
        cid = kwargs.get("cid")

    if cid is not None:
        context.append(f"chat_id={cid}")

    call = args[2] if len(args) >= 3 else kwargs.get("call")

    if call is not None:
        callback_id = getattr(call, "id", None)
        if callback_id:
            context.append(f"callback_id={callback_id}")

        callback_data = getattr(call, "data", None)
        if callback_data is not None:
            context.append(f"callback_data={callback_data!r}")

        from_user = getattr(call, "from_user", None)
        if from_user is not None:
            user_id = getattr(from_user, "id", None)
            username = getattr(from_user, "username", None)

            if user_id is not None:
                context.append(f"user_id={user_id}")

            if username:
                context.append(f"username=@{username}")

        message = getattr(call, "message", None)
        if message is not None:
            message_id = getattr(message, "message_id", None)
            if message_id is not None:
                context.append(f"message_id={message_id}")

    return " ".join(context)


def _telegram_description(exception):
    """Возвращает нормализованное описание Telegram API ошибки."""

    return (getattr(exception, "description", "") or "").strip().lower()


def handle_errors(
    error_msg: str = "Произошла ошибка",
    log_level: str = "error",
    default_return=None,
):
    """
    Декоратор единой обработки ошибок.

    Ожидаемые Telegram API ошибки подавляются.
    Неожиданные ошибки логируются с контекстом и traceback,
    после чего пробрасываются дальше.
    """

    def decorator(func):

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)

            except ApiTelegramException as exception:
                description = _telegram_description(exception)

                if description in EXPECTED_TELEGRAM_ERRORS:
                    context = _get_error_context(args, kwargs)
                    context_suffix = f" | {context}" if context else ""

                    logger.debug(
                        "error_handler.telegram.expected_error | "
                        "description=%s | context=%s",
                        description,
                        context,
                    )
                    return default_return

                context = _get_error_context(args, kwargs)
                context_suffix = f" | {context}" if context else ""

                log_func = getattr(
                    logger,
                    log_level,
                    logger.error,
                )

                log_func(
                    "%s в %s: %s | exception=%s%s",
                    error_msg,
                    func.__name__,
                    description or str(exception),
                    type(exception).__name__,
                    context_suffix,
                    exc_info=True,
                )

                raise

            except Exception as exception:
                context = _get_error_context(args, kwargs)
                context_suffix = f" | {context}" if context else ""

                log_func = getattr(
                    logger,
                    log_level,
                    logger.error,
                )

                log_func(
                    "%s в %s: %s | exception=%s%s",
                    error_msg,
                    func.__name__,
                    str(exception),
                    type(exception).__name__,
                    context_suffix,
                    exc_info=True,
                )

                raise

        return wrapper

    return decorator
