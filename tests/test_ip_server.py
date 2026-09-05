from unittest.mock import Mock, patch

from services.ip_server import (
    create_ip_handler,
    start_ip_server_once,
)


def test_create_ip_handler_returns_class():
    bot = Mock()

    handler = create_ip_handler(bot, "123456")

    assert isinstance(handler, type)
    assert hasattr(handler, "do_GET")
    assert hasattr(handler, "handle")


def test_do_get_wrong_path():
    bot = Mock()

    handler = create_ip_handler(bot, "123456")

    request = handler.__new__(handler)

    request.path = "/wrong"
    request.client_address = ("1.2.3.4", 12345)

    request.send_response = Mock()
    request.send_header = Mock()
    request.end_headers = Mock()

    wfile = Mock()
    wfile.write = Mock()
    request.wfile = wfile

    request.do_GET()

    bot.send_message.assert_not_called()
    request.send_response.assert_not_called()


def test_do_get_send_message_exception():
    bot = Mock()
    bot.send_message.side_effect = Exception("Telegram error")

    handler = create_ip_handler(bot, "123456")

    request = handler.__new__(handler)

    request.path = "/ip"
    request.client_address = ("5.6.7.8", 12345)

    request.send_response = Mock()
    request.send_header = Mock()
    request.end_headers = Mock()

    wfile = Mock()
    wfile.write = Mock()
    request.wfile = wfile

    request.do_GET()

    bot.send_message.assert_called_once()

    request.send_response.assert_called_once_with(200)


def _make_request(handler, path, client_ip="5.6.7.8"):
    request = handler.__new__(handler)
    request.path = path
    request.client_address = (client_ip, 12345)
    request.send_response = Mock()
    request.send_header = Mock()
    request.end_headers = Mock()

    request.wfile = Mock()
    request.wfile.write = Mock()

    return request


def test_do_get_valid_token_sends_ip():
    bot = Mock()
    handler = create_ip_handler(bot)

    request = _make_request(
        handler,
        "/ip?token=abc123",
    )

    with patch(
        "services.ip_server.get_chat_id_by_token",
        return_value=111222,
    ):
        request.do_GET()

    bot.send_message.assert_called_once_with(
        111222,
        "🌍 Ваш внешний IP:\n`5.6.7.8`",
        parse_mode="Markdown",
    )
    request.send_response.assert_called_once_with(200)
    request.send_header.assert_called_once_with(
        "Content-type",
        "text/html; charset=utf-8",
    )
    request.wfile.write.assert_called_once_with("IP отправлен в Telegram".encode())


def test_do_get_invalid_token_returns_403():
    bot = Mock()
    handler = create_ip_handler(bot)

    request = _make_request(
        handler,
        "/ip?token=bad-token",
    )

    with (
        patch(
            "services.ip_server.get_chat_id_by_token",
            return_value=None,
        ),
        patch(
            "services.ip_server.logger.warning",
        ) as mock_warning,
    ):
        request.do_GET()

    mock_warning.assert_called_once_with(
        "ip_server.request.invalid_token | token_present=true"
    )
    request.send_response.assert_called_once_with(403)
    request.end_headers.assert_called_once()
    request.wfile.write.assert_called_once_with(b"Invalid token")
    bot.send_message.assert_not_called()


def test_do_get_without_token_uses_admin_chat_id():
    bot = Mock()
    handler = create_ip_handler(bot, "123456")

    request = _make_request(
        handler,
        "/ip",
        client_ip="9.8.7.6",
    )

    request.do_GET()

    bot.send_message.assert_called_once_with(
        "123456",
        "🌍 Ваш внешний IP:\n`9.8.7.6`",
        parse_mode="Markdown",
    )
    request.send_response.assert_called_once_with(200)
    request.wfile.write.assert_called_once_with("IP отправлен в Telegram".encode())


def test_do_get_without_token_and_admin_chat_id_returns_400():
    bot = Mock()
    handler = create_ip_handler(bot)

    request = _make_request(
        handler,
        "/ip",
    )

    with patch(
        "services.ip_server.logger.warning",
    ) as mock_warning:
        request.do_GET()

    mock_warning.assert_called_once_with(
        "ip_server.request.missing_token"
    )
    request.send_response.assert_called_once_with(400)
    request.end_headers.assert_called_once()
    request.wfile.write.assert_called_once_with(b"Missing token")
    bot.send_message.assert_not_called()


def test_do_get_telegram_error_returns_fallback_response():
    bot = Mock()
    bot.send_message.side_effect = Exception("Telegram error")

    handler = create_ip_handler(bot, "123456")

    request = _make_request(
        handler,
        "/ip",
    )

    with patch(
        "services.ip_server.logger.error",
    ) as mock_error:
        request.do_GET()

    mock_error.assert_called_once()
    request.send_response.assert_called_once_with(200)
    request.send_header.assert_called_once_with(
        "Content-type",
        "text/html; charset=utf-8",
    )
    request.wfile.write.assert_called_once_with(
        "IP получен, но Telegram недоступен".encode()
    )


def test_handle_suppresses_connection_reset():
    bot = Mock()
    handler = create_ip_handler(bot)

    request = handler.__new__(handler)

    with patch.object(
        handler.__bases__[0],
        "handle",
        side_effect=ConnectionResetError,
    ):
        request.handle()


def test_handle_suppresses_broken_pipe():
    bot = Mock()
    handler = create_ip_handler(bot)

    request = handler.__new__(handler)

    with patch.object(
        handler.__bases__[0],
        "handle",
        side_effect=BrokenPipeError,
    ):
        request.handle()


def test_log_message_does_nothing():
    bot = Mock()
    handler = create_ip_handler(bot)

    request = handler.__new__(handler)

    assert request.log_message("test %s", "value") is None


def test_start_ip_server_once_starts_temporary_server(monkeypatch):
    bot = Mock()
    calls = []

    class FakeServer:
        timeout = None

        def __init__(self, address, handler):
            calls.append(("init", address, handler))

        def handle_request(self):
            calls.append(("handle_request",))

        def server_close(self):
            calls.append(("server_close",))

    class FakeThread:
        def __init__(self, target, daemon):
            calls.append(("thread_init", target, daemon))
            self.target = target

        def start(self):
            calls.append(("thread_start",))
            self.target()

    monkeypatch.setattr(
        "services.ip_server.ThreadingHTTPServer",
        FakeServer,
    )
    monkeypatch.setattr(
        "threading.Thread",
        FakeThread,
    )

    result = start_ip_server_once(
        bot,
        "123456",
        port=8099,
    )

    assert result == 8099
    assert calls[0][0] == "init"
    assert calls[0][1] == ("0.0.0.0", 8099)
    assert calls[0][2].__name__ == "IPCheckHandler"

    assert calls[1][0] == "thread_init"
    assert calls[1][2] is True
    assert calls[2] == ("thread_start",)
    assert calls[3:] == [
        ("handle_request",),
        ("server_close",),
    ]
