from unittest.mock import patch

from core import callback_router as router


def test_registered_callback_resolves_to_its_route():
    route = router.resolve("nav:clients_vless")

    assert route is not None
    assert route.pattern == "nav:clients_vless"
    assert route.handler.__name__ == "handle_navigation_callback"
    assert route.access is router.CallbackAccess.ADMIN
    assert route.prefix is False


def test_callback_registry_contains_exact_routes():
    callbacks = router.all_callbacks()

    assert isinstance(callbacks, dict)
    assert "nav:clients_vless" in callbacks
    assert callbacks["nav:clients_vless"] is router.EXACT_ROUTES["nav:clients_vless"]


def test_exact_callback_has_priority_over_prefix():
    assert router.resolve("nav:clients_vless").handler.__name__ == (
        "handle_navigation_callback"
    )
    assert router.resolve("log_xray").handler.__name__ == (
        "handle_management_part1_callback"
    )
    assert router.resolve("restart_xray").handler.__name__ == (
        "handle_management_part1_callback"
    )
    assert router.resolve("nav:clients_search_vless").handler.__name__ == (
        "handle_search_callback"
    )


def test_denied_callback_logs_warning_and_answers_user(monkeypatch):
    class FakeCall:
        id = "callback-123"
        data = "nav:clients_vless"

        class Message:
            chat = type("Chat", (), {"id": 12345})()

        message = Message()

    class FakeBot:
        def __init__(self):
            self.answers = []

        def callback_query_handler(self, **kwargs):
            def decorator(handler):
                self.callback_handler = handler
                return handler

            return decorator

        def answer_callback_query(self, callback_id, text):
            self.answers.append((callback_id, text))

    bot = FakeBot()

    monkeypatch.setattr(
        router,
        "authorize",
        lambda cid, route, data: False,
    )

    warnings = []
    monkeypatch.setattr(
        router.logger,
        "warning",
        lambda message, *args: warnings.append((message, args)),
    )

    router.register_callback_router(bot)

    bot.callback_handler(FakeCall())

    assert warnings == [
        (
            "callback.denied | chat_id=%s | data=%s | pattern=%s | access=%s",
            (12345, "nav:clients_vless", "nav:clients_vless", "admin"),
        )
    ]
    assert bot.answers == [
        ("callback-123", "❌ Недостаточно прав."),
    ]


def test_callback_router_answers_callback_response_text(monkeypatch):
    class FakeCall:
        id = "callback-response"
        data = "test:response"

        class Message:
            class Chat:
                id = 123

            chat = Chat()

        message = Message()

    class FakeBot:
        def __init__(self):
            self.answers = []

        def callback_query_handler(self, **kwargs):
            def decorator(handler):
                self.callback_handler = handler
                return handler

            return decorator

        def answer_callback_query(
            self,
            callback_id,
            text=None,
            show_alert=False,
        ):
            self.answers.append((callback_id, text, show_alert))

    bot = FakeBot()

    route = router.CallbackRoute(
        "test:",
        lambda bot, cid, call, data: router.CallbackResponse(
            "Тестовый ответ",
            show_alert=True,
        ),
        router.CallbackAccess.ADMIN,
        prefix=True,
    )

    monkeypatch.setattr(router, "resolve", lambda data: route)
    monkeypatch.setattr(
        router,
        "authorize",
        lambda cid, route, data: True,
    )

    router.register_callback_router(bot)
    bot.callback_handler(FakeCall())

    assert bot.answers == [
        ("callback-response", "Тестовый ответ", True),
    ]


def test_callback_router_keeps_boolean_handler_contract(monkeypatch):
    class FakeCall:
        id = "callback-bool"
        data = "test:bool"

        class Message:
            class Chat:
                id = 123

            chat = Chat()

        message = Message()

    class FakeBot:
        def __init__(self):
            self.answers = []

        def callback_query_handler(self, **kwargs):
            def decorator(handler):
                self.callback_handler = handler
                return handler

            return decorator

        def answer_callback_query(
            self,
            callback_id,
            text=None,
            show_alert=False,
        ):
            self.answers.append((callback_id, text, show_alert))

    bot = FakeBot()
    calls = []

    route = router.CallbackRoute(
        "test:",
        lambda bot, cid, call, data: calls.append(data) or True,
        router.CallbackAccess.ADMIN,
        prefix=True,
    )

    monkeypatch.setattr(router, "resolve", lambda data: route)
    monkeypatch.setattr(
        router,
        "authorize",
        lambda cid, route, data: True,
    )

    router.register_callback_router(bot)
    bot.callback_handler(FakeCall())

    assert calls == ["test:bool"]
    assert bot.answers == [
        ("callback-bool", None, False),
    ]


def test_authorize_qr_select_allows_admin_without_binding():
    route = router.CallbackRoute(
        "qr_select_",
        lambda: None,
        router.CallbackAccess.CLIENT_OR_ADMIN,
        prefix=True,
    )

    with (
        patch("core.access.is_admin", return_value=True),
        patch("core.access.is_client", return_value=False),
    ):
        assert router.authorize(123, route, "qr_select_alice_both") is True


def test_authorize_qr_select_allows_owned_client():
    route = router.CallbackRoute(
        "qr_select_",
        lambda: None,
        router.CallbackAccess.CLIENT_OR_ADMIN,
        prefix=True,
    )

    with (
        patch("core.access.is_admin", return_value=False),
        patch("core.access.is_client", return_value=True),
        patch(
            "ui.client_menu.get_client_list",
            return_value=["alice"],
        ),
    ):
        assert router.authorize(123, route, "qr_select_alice_both") is True


def test_authorize_qr_select_denies_unowned_client():
    route = router.CallbackRoute(
        "qr_select_",
        lambda: None,
        router.CallbackAccess.CLIENT_OR_ADMIN,
        prefix=True,
    )

    with (
        patch("core.access.is_admin", return_value=False),
        patch("core.access.is_client", return_value=True),
        patch(
            "ui.client_menu.get_client_list",
            return_value=["bob"],
        ),
    ):
        assert router.authorize(123, route, "qr_select_alice_both") is False


def test_authorize_client_denies_non_client():
    route = router.CallbackRoute(
        "client:account:",
        lambda: None,
        router.CallbackAccess.CLIENT,
        prefix=True,
    )

    with patch("core.access.is_client", return_value=False):
        assert router.authorize(123, route, "client:account:alice") is False


def test_authorize_client_denies_empty_username():
    route = router.CallbackRoute(
        "client:account:",
        lambda: None,
        router.CallbackAccess.CLIENT,
        prefix=True,
    )

    with (
        patch("core.access.is_client", return_value=True),
        patch("ui.client_menu.get_client_list") as get_client_list,
    ):
        assert router.authorize(123, route, "client:account:") is False
        get_client_list.assert_not_called()


def test_authorize_client_denies_unowned_username():
    route = router.CallbackRoute(
        "client:stats:",
        lambda: None,
        router.CallbackAccess.CLIENT,
        prefix=True,
    )

    with (
        patch("core.access.is_client", return_value=True),
        patch(
            "ui.client_menu.get_client_list",
            return_value=["bob"],
        ),
    ):
        assert router.authorize(123, route, "client:stats:alice") is False


def test_authorize_client_allows_owned_username():
    route = router.CallbackRoute(
        "client:conf:",
        lambda: None,
        router.CallbackAccess.CLIENT,
        prefix=True,
    )

    with (
        patch("core.access.is_client", return_value=True),
        patch(
            "ui.client_menu.get_client_list",
            return_value=["alice"],
        ) as get_client_list,
    ):
        assert router.authorize(123, route, "client:conf:alice") is True
        get_client_list.assert_called_once_with(123)


def test_authorize_client_conf_ru_allows_owned_username():
    route = router.CallbackRoute(
        "client:conf_ru:",
        lambda: None,
        router.CallbackAccess.CLIENT,
        prefix=True,
    )

    with (
        patch("core.access.is_client", return_value=True),
        patch(
            "ui.client_menu.get_client_list",
            return_value=["alice"],
        ),
    ):
        assert router.authorize(123, route, "client:conf_ru:alice") is True


def test_authorize_client_allows_non_account_prefix():
    route = router.CallbackRoute(
        "client:help:",
        lambda: None,
        router.CallbackAccess.CLIENT,
        prefix=True,
    )

    with patch("core.access.is_client", return_value=True):
        assert router.authorize(123, route, "client:help:whatever") is True


def test_authorize_denies_unknown_access_level():
    route = router.CallbackRoute(
        "unknown:",
        lambda: None,
        "unknown",
        prefix=False,
    )

    assert router.authorize(123, route, "unknown:value") is False


def test_all_prefixes_returns_pattern_index():
    result = router.all_prefixes()

    assert isinstance(result, dict)
    assert result
    assert all(pattern == route.pattern for pattern, route in result.items())


def test_resolve_returns_matching_prefix_route():
    route = router.CallbackRoute(
        "test:",
        lambda: None,
        router.CallbackAccess.PUBLIC,
        prefix=True,
    )

    with (
        patch.object(router, "EXACT_ROUTES", {}),
        patch.object(
            router,
            "PREFIX_ROUTES",
            (route,),
        ),
    ):
        assert router.resolve("test:value") is route


def test_resolve_returns_none_for_unknown_callback():
    with (
        patch.object(router, "EXACT_ROUTES", {}),
        patch.object(
            router,
            "PREFIX_ROUTES",
            (),
        ),
    ):
        assert router.resolve("unknown") is None


def test_get_returns_handler_for_resolved_route():
    def handler():
        pass

    route = router.CallbackRoute(
        "test:",
        handler,
        router.CallbackAccess.PUBLIC,
        prefix=True,
    )

    with patch.object(router, "resolve", return_value=route):
        assert router.get("test:value") is handler


def test_get_returns_none_for_unknown_callback():
    with patch.object(router, "resolve", return_value=None):
        assert router.get("unknown") is None


def test_authorize_public_callback():
    route = router.CallbackRoute(
        "public",
        lambda: None,
        router.CallbackAccess.PUBLIC,
    )

    assert router.authorize(123, route, "public") is True


def test_authorize_admin_callback():
    route = router.CallbackRoute(
        "admin",
        lambda: None,
        router.CallbackAccess.ADMIN,
    )

    with patch("core.access.is_admin", return_value=True):
        assert router.authorize(123, route, "admin") is True

    with patch("core.access.is_admin", return_value=False):
        assert router.authorize(123, route, "admin") is False


def test_callback_router_ignores_unmatched_callback(monkeypatch):
    class FakeCall:
        id = "callback-unknown"

        class Message:
            class Chat:
                id = 123

            chat = Chat()

        data = "unknown:callback"
        message = Message()

    class FakeBot:
        def callback_query_handler(self, **kwargs):
            def decorator(handler):
                self.callback_handler = handler
                return handler

            return decorator

    bot = FakeBot()

    monkeypatch.setattr(router, "resolve", lambda data: None)

    logs = []
    monkeypatch.setattr(
        router.logger,
        "debug",
        lambda *args: logs.append(args),
    )

    router.register_callback_router(bot)
    bot.callback_handler(FakeCall())

    assert any(
        args[0] == "callback.unmatched | chat_id=%s | data=%s"
        for args in logs
    )


def test_callback_router_calls_authorized_handler(monkeypatch):
    class FakeCall:
        id = "callback-success"

        class Message:
            class Chat:
                id = 123

            chat = Chat()

        data = "test:callback"
        message = Message()

    class FakeBot:
        def callback_query_handler(self, **kwargs):
            def decorator(handler):
                self.callback_handler = handler
                return handler

            return decorator

    calls = []

    def handler(bot, cid, call, data):
        calls.append((bot, cid, call, data))
        return True

    route = router.CallbackRoute(
        "test:",
        handler,
        router.CallbackAccess.PUBLIC,
        prefix=True,
    )

    bot = FakeBot()

    monkeypatch.setattr(router, "resolve", lambda data: route)
    monkeypatch.setattr(router, "authorize", lambda cid, route, data: True)

    router.register_callback_router(bot)
    bot.callback_handler(FakeCall())

    assert len(calls) == 1
    assert calls[0][0] is bot
    assert calls[0][1] == 123
    assert calls[0][2].id == "callback-success"
    assert calls[0][3] == "test:callback"


def test_callback_router_logs_completed_event(monkeypatch):
    class FakeCall:
        id = "callback-completed"

        class Message:
            class Chat:
                id = 456

            chat = Chat()

        data = "test:completed"
        message = Message()

    class FakeBot:
        def callback_query_handler(self, **kwargs):
            def decorator(handler):
                self.callback_handler = handler
                return handler

            return decorator

    route = router.CallbackRoute(
        "test:",
        lambda bot, cid, call, data: router.CallbackResponse("ok"),
        router.CallbackAccess.PUBLIC,
        prefix=True,
    )

    bot = FakeBot()
    logs = []

    monkeypatch.setattr(router, "resolve", lambda data: route)
    monkeypatch.setattr(router, "authorize", lambda cid, route, data: True)
    monkeypatch.setattr(
        router.logger,
        "debug",
        lambda *args: logs.append(args),
    )

    router.register_callback_router(bot)
    bot.callback_handler(FakeCall())

    completed = [
        args
        for args in logs
        if args and args[0] == (
            "callback.completed | chat_id=%s | data=%s | pattern=%s | "
            "result=%r | elapsed_ms=%.1f"
        )
    ]

    assert len(completed) == 1

    _, chat_id, data, pattern, result, elapsed_ms = completed[0]

    assert (chat_id, data, pattern) == (456, "test:completed", "test:")
    assert result.text == "ok"
    assert isinstance(elapsed_ms, float)
    assert elapsed_ms >= 0


def test_callback_router_returns_false_when_handler_returns_false(monkeypatch):
    class FakeCall:
        id = "callback-not-handled"

        class Message:
            class Chat:
                id = 123

            chat = Chat()

        data = "test:callback"
        message = Message()

    class FakeBot:
        def callback_query_handler(self, **kwargs):
            def decorator(handler):
                self.callback_handler = handler
                return handler

            return decorator

    route = router.CallbackRoute(
        "test:",
        lambda bot, cid, call, data: False,
        router.CallbackAccess.PUBLIC,
        prefix=True,
    )

    bot = FakeBot()

    monkeypatch.setattr(router, "resolve", lambda data: route)
    monkeypatch.setattr(router, "authorize", lambda cid, route, data: True)

    router.register_callback_router(bot)

    assert bot.callback_handler(FakeCall()) is False


def test_callback_router_logs_handler_exception_and_closes_callback(
    monkeypatch,
):
    class FakeCall:
        id = "callback-error"

        class Message:
            class Chat:
                id = 123

            chat = Chat()

        data = "test:error"
        message = Message()

    class FakeBot:
        def callback_query_handler(self, **kwargs):
            def decorator(handler):
                self.callback_handler = handler
                return handler

            return decorator

    def failing_handler(bot, cid, call, data):
        raise RuntimeError("handler failed")

    route = router.CallbackRoute(
        "test:error",
        failing_handler,
        router.CallbackAccess.PUBLIC,
    )

    bot = FakeBot()
    answered = []
    errors = []

    monkeypatch.setattr(router, "resolve", lambda data: route)
    monkeypatch.setattr(
        router,
        "authorize",
        lambda cid, route, data: True,
    )
    monkeypatch.setattr(
        router,
        "safe_answer_callback",
        lambda bot, callback_id: answered.append(callback_id),
    )
    monkeypatch.setattr(
        router.logger,
        "exception",
        lambda message, *args: errors.append((message, args)),
    )

    router.register_callback_router(bot)

    assert bot.callback_handler(FakeCall()) is False
    assert answered == ["callback-error"]
    assert len(errors) == 1
    message, args = errors[0]
    assert (
        message
        == "callback.failed | callback_id=%s | data=%r | elapsed_ms=%.1f"
    )
    assert args[0:2] == ("callback-error", "test:error")
    assert isinstance(args[2], float)
    assert args[2] >= 0


def test_authorize_qr_select_star_payload_owned_client():
    route = router.CallbackRoute(
        "qr_select_",
        lambda: None,
        router.CallbackAccess.CLIENT_OR_ADMIN,
        prefix=True,
    )

    with (
        patch("core.access.is_admin", return_value=False),
        patch("core.access.is_client", return_value=True),
        patch(
            "ui.client_menu.get_client_list",
            return_value=["alice"],
        ),
    ):
        assert router.authorize(123, route, "qr_select_alice*awg") is True


def test_authorize_qr_select_plain_payload_owned_client():
    route = router.CallbackRoute(
        "qr_select_",
        lambda: None,
        router.CallbackAccess.CLIENT_OR_ADMIN,
        prefix=True,
    )

    with (
        patch("core.access.is_admin", return_value=False),
        patch("core.access.is_client", return_value=True),
        patch(
            "ui.client_menu.get_client_list",
            return_value=["alice"],
        ),
    ):
        assert router.authorize(123, route, "qr_select_alice") is True


def test_authorize_qr_select_empty_username_denied():
    route = router.CallbackRoute(
        "qr_select_",
        lambda: None,
        router.CallbackAccess.CLIENT_OR_ADMIN,
        prefix=True,
    )

    with (
        patch("core.access.is_admin", return_value=False),
        patch("core.access.is_client", return_value=True),
    ):
        assert router.authorize(123, route, "qr_select_") is False


def test_authorize_client_or_admin_non_qr_returns_true_for_client():
    route = router.CallbackRoute(
        "some:prefix:",
        lambda: None,
        router.CallbackAccess.CLIENT_OR_ADMIN,
        prefix=True,
    )

    with (
        patch("core.access.is_admin", return_value=False),
        patch("core.access.is_client", return_value=True),
    ):
        assert router.authorize(123, route, "some:prefix:value") is True


def test_authorize_client_or_admin_denies_non_client():
    route = router.CallbackRoute(
        "some:prefix:",
        lambda: None,
        router.CallbackAccess.CLIENT_OR_ADMIN,
        prefix=True,
    )

    with (
        patch("core.access.is_admin", return_value=False),
        patch("core.access.is_client", return_value=False),
    ):
        assert router.authorize(123, route, "some:prefix:value") is False
