from core import callback_router as router


def test_public_routes_are_public():
    public_callbacks = {
        "request_bind",
        "create_ticket",
        "ticket_topic_internet",
        "ticket_topic_vpn",
        "ticket_topic_config",
        "ticket_topic_other",
        "ticket_cancel",
        "ticket_reply:123",
    }

    for callback in public_callbacks:
        route = router.resolve(callback)

        assert route is not None, callback
        assert route.access is router.CallbackAccess.PUBLIC, callback


def test_qr_select_route_is_client_accessible():
    route = router.resolve("qr_select_TestUser*443")

    assert route is not None
    assert route.access is router.CallbackAccess.CLIENT_OR_ADMIN


def test_admin_routes_are_admin_only():
    admin_callbacks = {
        "nav:manage",
        "nav:admin_tickets",
        "restart_xray",
        "log_xray",
        "process_search",
        "fail2ban_menu",
        "ssh_menu",
        "nav:network",
        "bindings_menu",
        "nav:create",
        "nav:clients_search_vless",
        "qr:vless:TestUser",
    }

    for callback in admin_callbacks:
        route = router.resolve(callback)

        assert route is not None, callback
        assert route.access is router.CallbackAccess.ADMIN, callback


def test_public_callback_is_allowed_without_admin():
    assert router.authorize(123456, router.resolve("request_bind"))
    assert router.authorize(123456, router.resolve("ticket_reply:123"))


def test_admin_callback_is_denied_for_non_admin(monkeypatch):
    monkeypatch.setattr(
        "core.access.is_admin",
        lambda chat_id: False,
    )

    assert not router.authorize(123456, router.resolve("nav:manage"))
    assert not router.authorize(123456, router.resolve("restart_xray"))
    assert not router.authorize(123456, router.resolve("process_search"))


def test_admin_callback_is_allowed_for_admin(monkeypatch):
    monkeypatch.setattr(
        "core.access.is_admin",
        lambda chat_id: True,
    )

    assert router.authorize(123456, router.resolve("nav:manage"))
    assert router.authorize(123456, router.resolve("restart_xray"))
    assert router.authorize(123456, router.resolve("process_search"))


def test_unknown_callback_is_denied():
    assert router.resolve("callback_that_does_not_exist") is None


def test_route_access_is_part_of_route():
    route = router.resolve("request_bind")

    assert route is not None
    assert route.handler is not None
    assert route.pattern == "request_bind"
    assert route.access is router.CallbackAccess.PUBLIC
    assert route.prefix is False


def test_client_routes_are_client_only():
    client_callbacks = {
        "nav:client_home",
        "nav:client_back",
        "nav:client_help",
        "client:account:TestUser",
        "client:stats:TestUser",
        "client:conf:TestUser",
        "client:conf_ru:TestUser",
    }

    for callback in client_callbacks:
        route = router.resolve(callback)

        assert route is not None, callback
        assert route.access is router.CallbackAccess.CLIENT, callback
        assert route.handler is not None


def test_client_routes_are_not_public():
    client_callbacks = {
        "nav:client_home",
        "nav:client_back",
        "nav:client_help",
        "client:account:TestUser",
        "client:stats:TestUser",
        "client:conf:TestUser",
        "client:conf_ru:TestUser",
    }

    for callback in client_callbacks:
        route = router.resolve(callback)

        assert route is not None, callback
        assert route.access is not router.CallbackAccess.PUBLIC, callback


def test_old_client_callbacks_are_removed():
    old_callbacks = {
        "client_help",
        "client_rules",
        "client_back_menu",
        "client_acc_TestUser",
        "client_stats_TestUser",
        "client_conf_TestUser",
        "client_conf_ru_TestUser",
    }

    for callback in old_callbacks:
        assert router.resolve(callback) is None, callback
