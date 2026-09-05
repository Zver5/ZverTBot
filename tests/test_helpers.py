from telebot.apihelper import ApiTelegramException

from utils.helpers import (
    escape_md,
    fmt_traffic,
    normalize_client_list,
    safe_send_message,
)


def test_escape_md_basic():
    assert escape_md("a_b*c[`") == "a\\_b\\*c\\[\\`"
    assert escape_md("") == ""
    assert escape_md(None) == ""


def test_fmt_traffic_bytes():
    assert fmt_traffic(500) == "500 B"


def test_fmt_traffic_kb():
    assert fmt_traffic(2048) == "2 KB"


def test_fmt_traffic_exact_kb_boundary():
    assert fmt_traffic(1024) == "1 KB"


def test_fmt_traffic_mb():
    assert fmt_traffic(2 * 1048576) == "2.00 MB"


def test_fmt_traffic_exact_mb_boundary():
    assert fmt_traffic(1048576) == "1.00 MB"


def test_fmt_traffic_gb():
    assert fmt_traffic(2 * 1073741824) == "2.00 GB"


def test_fmt_traffic_exact_gb_boundary():
    assert fmt_traffic(1073741824) == "1.00 GB"


def test_normalize_client_list():
    assert normalize_client_list("Boiko") == ["Boiko"]
    assert normalize_client_list(["A", "B"]) == ["A", "B"]
    assert normalize_client_list(None) == []


def test_normalize_client_list_edge():
    assert normalize_client_list("") == []
    assert normalize_client_list(0) == []


def test_telegram_call_with_retry_retries_timeout():
    from requests.exceptions import Timeout

    from utils.helpers import _telegram_call_with_retry

    calls = []

    def operation():
        calls.append(1)
        if len(calls) < 3:
            raise Timeout("temporary timeout")
        return "ok"

    assert _telegram_call_with_retry(operation) == "ok"
    assert len(calls) == 3


def test_telegram_call_with_retry_retries_connection_error():
    from requests.exceptions import ConnectionError

    from utils.helpers import _telegram_call_with_retry

    calls = []

    def operation():
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("temporary connection error")
        return "ok"

    assert _telegram_call_with_retry(operation) == "ok"
    assert len(calls) == 2


def test_telegram_call_with_retry_raises_after_three_attempts():
    from requests.exceptions import Timeout

    from utils.helpers import _telegram_call_with_retry

    calls = []

    def operation():
        calls.append(1)
        raise Timeout("persistent timeout")

    try:
        _telegram_call_with_retry(operation)
    except Timeout:
        pass
    else:
        raise AssertionError("Timeout должен быть выброшен после 3 попыток")

    assert len(calls) == 3


def test_safe_answer_callback_success():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_answer_callback

    bot = Mock()

    with patch("utils.helpers._telegram_call_with_retry") as mock_retry:
        safe_answer_callback(bot, "callback-123")

    mock_retry.assert_called_once_with(
        bot.answer_callback_query,
        "callback-123",
    )


def test_safe_answer_callback_ignores_old_query_error():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_answer_callback

    bot = Mock()

    with (
        patch(
            "utils.helpers._telegram_call_with_retry",
            side_effect=Exception("query is too old"),
        ),
        patch("utils.helpers.logger.warning") as mock_warning,
    ):
        safe_answer_callback(bot, "callback-123")

    mock_warning.assert_not_called()


def test_safe_answer_callback_logs_unexpected_error():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_answer_callback

    bot = Mock()

    with (
        patch(
            "utils.helpers._telegram_call_with_retry",
            side_effect=Exception("Telegram unavailable"),
        ),
        patch("utils.helpers.logger.warning") as mock_warning,
    ):
        safe_answer_callback(bot, "callback-123")

    mock_warning.assert_called_once_with(
        "telegram.callback.answer_failed | error=%s",
        mock_warning.call_args.args[1],
    )


def test_safe_delete_success():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_delete

    bot = Mock()

    with patch("utils.helpers._telegram_call_with_retry") as mock_retry:
        result = safe_delete(bot, 111222, 333444)

    assert result is True
    mock_retry.assert_called_once_with(
        bot.delete_message,
        111222,
        333444,
    )


def test_safe_delete_returns_false_on_error():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_delete

    bot = Mock()

    with patch(
        "utils.helpers._telegram_call_with_retry",
        side_effect=Exception("delete failed"),
    ):
        result = safe_delete(bot, 111222, 333444)

    assert result is False


def test_safe_send_message_success():
    from unittest.mock import Mock

    bot = Mock()

    result = safe_send_message(
        bot,
        111222,
        "Тест",
        parse_mode="Markdown",
    )

    assert result is True
    bot.send_message.assert_called_once_with(
        111222,
        "Тест",
        parse_mode="Markdown",
    )


def test_safe_send_message_error_returns_false():
    from unittest.mock import Mock, patch

    bot = Mock()

    with patch(
        "utils.helpers._telegram_call_with_retry",
        side_effect=Exception("send failed"),
    ):
        result = safe_send_message(bot, 111222, "Тест")

    assert result is False


def test_safe_send_message_logs_error():
    from unittest.mock import Mock, patch

    bot = Mock()

    with (
        patch(
            "utils.helpers._telegram_call_with_retry",
            side_effect=Exception("send failed"),
        ),
        patch("utils.helpers.logger.warning") as mock_warning,
    ):
        result = safe_send_message(bot, 111222, "Тест")

    assert result is False
    mock_warning.assert_called_once_with(
        "telegram.message.send_failed | error=%s",
        mock_warning.call_args.args[1],
    )


def test_safe_send_message_handles_logging_error():
    from unittest.mock import Mock, patch

    bot = Mock()

    with (
        patch(
            "utils.helpers._telegram_call_with_retry",
            side_effect=Exception("send failed"),
        ),
        patch(
            "utils.helpers.logger.warning",
            side_effect=RuntimeError("logger failed"),
        ),
    ):
        result = safe_send_message(bot, 111222, "Тест")

    assert result is False


def test_safe_send_document_success():
    from unittest.mock import Mock

    from utils.helpers import safe_send_document

    bot = Mock()
    document = Mock()

    result = safe_send_document(
        bot,
        111222,
        document,
        caption="Тест",
        parse_mode="Markdown",
    )

    assert result is True
    bot.send_document.assert_called_once_with(
        111222,
        document,
        caption="Тест",
        parse_mode="Markdown",
    )


def test_safe_send_document_error_returns_false():
    from unittest.mock import Mock

    from utils.helpers import safe_send_document

    bot = Mock()
    document = Mock()
    bot.send_document.side_effect = RuntimeError("send failed")

    result = safe_send_document(bot, 111222, document)

    assert result is False


def test_safe_edit_message_success():
    from unittest.mock import Mock

    from utils.helpers import safe_edit_message

    bot = Mock()

    result = safe_edit_message(
        bot,
        "Новый текст",
        111222,
        333444,
        parse_mode="HTML",
    )

    assert result is True
    bot.edit_message_text.assert_called_once_with(
        "Новый текст",
        111222,
        333444,
        parse_mode="HTML",
    )


def test_safe_edit_message_message_not_modified_returns_true():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_edit_message

    bot = Mock()

    error = ApiTelegramException.__new__(ApiTelegramException)
    error.description = "Bad Request: message is not modified"

    with patch(
        "utils.helpers._telegram_call_with_retry",
        side_effect=error,
    ):
        result = safe_edit_message(
            bot,
            "Тот же текст",
            111222,
            333444,
        )

    assert result is True


def test_safe_edit_message_message_not_found_replaces_state_message_id():
    from unittest.mock import Mock, patch

    from core import state
    from utils.helpers import safe_edit_message

    bot = Mock()

    state.LAST_MAIN_MENU_MSGS.clear()
    state.LAST_MAIN_MENU_MSGS[111222] = 333444

    error = ApiTelegramException.__new__(ApiTelegramException)
    error.description = "Bad Request: message to edit not found"

    replacement = Mock()
    replacement.message_id = 555666

    with patch(
        "utils.helpers._telegram_call_with_retry",
        side_effect=[error, replacement],
    ):
        result = safe_edit_message(
            bot,
            "Новый текст",
            111222,
            333444,
        )

    assert result is True
    assert state.LAST_MAIN_MENU_MSGS[111222] == 555666

    state.LAST_MAIN_MENU_MSGS.clear()


def test_safe_edit_message_message_not_found_updates_nested_admin_state():
    from unittest.mock import Mock, patch

    from core import state
    from utils.helpers import safe_edit_message

    bot = Mock()

    state.LAST_MY_ID_ADMIN_MSGS.clear()
    state.LAST_MY_ID_ADMIN_MSGS[111222] = {999888: 333444}

    error = ApiTelegramException.__new__(ApiTelegramException)
    error.description = "Bad Request: message to edit not found"

    replacement = Mock()
    replacement.message_id = 555666

    with patch(
        "utils.helpers._telegram_call_with_retry",
        side_effect=[error, replacement],
    ):
        result = safe_edit_message(
            bot,
            "Новый текст",
            999888,
            333444,
        )

    assert result is True
    assert state.LAST_MY_ID_ADMIN_MSGS[111222] == {999888: 555666}

    state.LAST_MY_ID_ADMIN_MSGS.clear()


def test_safe_edit_message_api_error_returns_false():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_edit_message

    bot = Mock()

    error = ApiTelegramException.__new__(ApiTelegramException)
    error.description = "Bad Request: message to edit not found"

    with (
        patch(
            "utils.helpers._telegram_call_with_retry",
            side_effect=error,
        ),
        patch("utils.helpers.logger.error") as mock_error,
    ):
        result = safe_edit_message(
            bot,
            "Новый текст",
            111222,
            333444,
        )

    assert result is False
    mock_error.assert_called_once_with(
        "telegram.message.edit_fallback_failed | error=%s",
        error,
    )


def test_safe_edit_message_unexpected_error_returns_false():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_edit_message

    bot = Mock()

    with (
        patch(
            "utils.helpers._telegram_call_with_retry",
            side_effect=Exception("edit failed"),
        ),
        patch("utils.helpers.logger.error") as mock_error,
    ):
        result = safe_edit_message(
            bot,
            "Новый текст",
            111222,
            333444,
        )

    assert result is False
    mock_error.assert_called_once()


def test_safe_edit_message_logs_api_error():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_edit_message

    bot = Mock()

    error = ApiTelegramException.__new__(ApiTelegramException)
    error.description = "Bad Request: message to edit not found"

    with (
        patch(
            "utils.helpers._telegram_call_with_retry",
            side_effect=error,
        ),
        patch("utils.helpers.logger.error") as mock_error,
    ):
        result = safe_edit_message(
            bot,
            "Новый текст",
            111222,
            333444,
        )

    assert result is False
    mock_error.assert_called_once()


def test_safe_edit_message_logs_unexpected_error():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_edit_message

    bot = Mock()

    with (
        patch(
            "utils.helpers._telegram_call_with_retry",
            side_effect=Exception("edit failed"),
        ),
        patch("utils.helpers.logger.error") as mock_error,
    ):
        result = safe_edit_message(
            bot,
            "Новый текст",
            111222,
            333444,
        )

    assert result is False
    mock_error.assert_called_once_with(
        "telegram.message.edit_failed | error=%s",
        "edit failed",
    )


def test_telegram_call_with_retry_returns_none_for_unreachable_result():
    from unittest.mock import Mock

    from utils.helpers import _telegram_call_with_retry

    operation = Mock(side_effect=[None])

    assert _telegram_call_with_retry(operation) is None
    operation.assert_called_once()


def test_safe_answer_callback_ignores_empty_callback_id():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_answer_callback

    bot = Mock()

    with patch("utils.helpers._telegram_call_with_retry") as mock_retry:
        assert safe_answer_callback(bot, None) is None

    mock_retry.assert_not_called()


def test_safe_edit_message_handles_error_when_logging_fails_api_error():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_edit_message

    bot = Mock()

    error = ApiTelegramException.__new__(ApiTelegramException)
    error.description = "Bad Request: message to edit not found"

    with (
        patch(
            "utils.helpers._telegram_call_with_retry",
            side_effect=error,
        ),
        patch(
            "utils.helpers.logger.error",
            side_effect=RuntimeError("logger failed"),
        ),
    ):
        result = safe_edit_message(
            bot,
            "Новый текст",
            111222,
            333444,
        )

    assert result is False


def test_safe_edit_message_handles_error_when_logging_fails_unexpected():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_edit_message

    bot = Mock()

    with (
        patch(
            "utils.helpers._telegram_call_with_retry",
            side_effect=Exception("edit failed"),
        ),
        patch(
            "utils.helpers.logger.error",
            side_effect=RuntimeError("logger failed"),
        ),
    ):
        result = safe_edit_message(
            bot,
            "Новый текст",
            111222,
            333444,
        )

    assert result is False


def test_safe_send_message_replaces_state_message_id():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_send_message

    bot = Mock()
    sent_message = Mock(message_id=555666)

    with (
        patch("utils.helpers._telegram_call_with_retry", return_value=sent_message),
        patch("core.state.replace_message_id") as mock_replace,
    ):
        result = safe_send_message(
            bot,
            111222,
            "Тест",
            replace_message_id=333444,
        )

    assert result is True
    mock_replace.assert_called_once_with(111222, 333444, 555666)


def test_safe_edit_message_message_not_found_without_replacement_id_returns_false():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_edit_message

    bot = Mock()

    error = ApiTelegramException.__new__(ApiTelegramException)
    error.description = "Bad Request: message to edit not found"

    with patch(
        "utils.helpers._telegram_call_with_retry",
        side_effect=[error, object()],
    ):
        result = safe_edit_message(
            bot,
            "Новый текст",
            111222,
            333444,
        )

    assert result is False


def test_safe_answer_callback_with_text_and_alert():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_answer_callback

    bot = Mock()

    with patch("utils.helpers._telegram_call_with_retry") as mock_retry:
        safe_answer_callback(
            bot,
            "callback-123",
            text="Готово",
            show_alert=True,
        )

    mock_retry.assert_called_once_with(
        bot.answer_callback_query,
        "callback-123",
        "Готово",
        show_alert=True,
    )


def test_safe_edit_message_reply_markup_success_and_error():
    from unittest.mock import Mock, patch

    from utils.helpers import safe_edit_message_reply_markup

    bot = Mock()

    assert safe_edit_message_reply_markup(
        bot,
        111222,
        333444,
        reply_markup="markup",
    ) is True

    bot.edit_message_reply_markup.assert_called_once_with(
        111222,
        333444,
        reply_markup="markup",
    )

    with patch(
        "utils.helpers._telegram_call_with_retry",
        side_effect=Exception("edit markup failed"),
    ), patch("utils.helpers.logger.warning") as mock_warning:
        assert safe_edit_message_reply_markup(
            bot,
            111222,
            333444,
        ) is False

    mock_warning.assert_called_once()
