"""
HTTP-сервер определения внешнего IP пользователя.

Telegram:
    кнопка -> ссылка с token -> HTTP сервер -> поиск chat_id -> отправка IP

Пример:
http://SERVER_IP:8085/ip?token=a8f52d9c
"""

import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from services.ip_tokens import get_chat_id_by_token
from utils.logger import logger


def create_ip_handler(bot, admin_chat_id=None):
    """
    admin_chat_id оставлен для совместимости со старыми тестами.
    """

    class IPCheckHandler(BaseHTTPRequestHandler):
        def handle(self):
            with contextlib.suppress(ConnectionResetError, BrokenPipeError):
                super().handle()

        def do_GET(self):

            parsed = urlparse(self.path)

            if parsed.path != "/ip":
                return

            params = parse_qs(parsed.query)

            token = params.get("token", [None])[0]

            # Новый защищённый режим через токен
            if token:
                chat_id = get_chat_id_by_token(token)

                if not chat_id:
                    logger.warning(
                        "ip_server.request.invalid_token | token_present=true"
                    )

                    self.send_response(403)
                    self.end_headers()
                    self.wfile.write(b"Invalid token")
                    return

            # Совместимость со старыми вызовами и тестами
            else:
                chat_id = admin_chat_id

                if not chat_id:
                    logger.warning("ip_server.request.missing_token")

                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Missing token")
                    return

            user_ip = self.client_address[0]

            try:
                bot.send_message(
                    chat_id, f"🌍 Ваш внешний IP:\n`{user_ip}`", parse_mode="Markdown"
                )

                self.send_response(200)

                self.send_header("Content-type", "text/html; charset=utf-8")

                self.end_headers()

                self.wfile.write("IP отправлен в Telegram".encode())

            except Exception as e:
                logger.error(
                    "ip_server.notify.failed | chat_id=%s | error=%s",
                    chat_id,
                    e,
                )

                self.send_response(200)

                self.send_header("Content-type", "text/html; charset=utf-8")

                self.end_headers()

                self.wfile.write("IP получен, но Telegram недоступен".encode())

        def log_message(self, _format, *args):  # noqa: F841
            pass

    return IPCheckHandler


def start_ip_server_once(bot, admin_chat_id=None, port: int = 8085):
    """
    Запускает временный IP-сервер для одного запроса.
    После первого обращения закрывается.
    """

    import threading

    handler = create_ip_handler(
        bot,
        admin_chat_id,
    )

    server = ThreadingHTTPServer(
        ("0.0.0.0", port),
        handler,
    )

    server.timeout = 20

    def serve_once():
        try:
            logger.info("ip_server.server.started | port=%s", port)
            server.handle_request()
        finally:
            server.server_close()
            logger.info("ip_server.server.closed")

    thread = threading.Thread(
        target=serve_once,
        daemon=True,
    )
    thread.start()

    return port
