from types import SimpleNamespace

import pytest

import handlers.admin.vpn_config as handler


class FakeBot:
    def __init__(self):
        self.edits = []
        self.answers = []
        self.step_handler = None
        self.cleared = []

    def edit_message_text(self, *args, **kwargs):
        self.edits.append((args, kwargs))

    def answer_callback_query(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    def clear_step_handler_by_chat_id(self, chat_id):
        self.cleared.append(chat_id)
        self.step_handler = None

    def register_next_step_handler_by_chat_id(self, chat_id, callback):
        self.step_handler = (chat_id, callback)


class FakeNavigation:
    def __init__(self):
        self.calls = []

    def go(self, cid, screen):
        self.calls.append(("go", cid, screen))

    def render(self, screen, bot, cid, message_id):
        self.calls.append(("render", screen, cid, message_id))

    def start(self, cid, screen):
        self.calls.append(("start", cid, screen))

    def replace(self, cid, screen):
        self.calls.append(("replace", cid, screen))

    def back(self, cid):
        self.calls.append(("back", cid))
        return handler.ADMIN_VPN_CONFIG


@pytest.fixture(autouse=True)
def clean_state():
    for store in (
        handler._DRAFTS,
        handler._ACTIVE_USERS,
        handler._SCREEN_ERRORS,
        handler._SCREEN_MESSAGES,
        handler._RESULTS,
    ):
        store.clear()


def make_call(chat_id=501, user_id=77):
    return SimpleNamespace(
        id="callback-id",
        from_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(
            chat=SimpleNamespace(id=chat_id),
            message_id=123,
        ),
    )


def setup_admin(monkeypatch, *, exists=False, protocols=None):
    monkeypatch.setattr(handler, "is_admin", lambda _cid: True)
    monkeypatch.setattr(
        handler,
        "get_configurable_protocols",
        lambda: protocols or ["xray", "awg"],
    )
    monkeypatch.setattr(
        handler, "protocol_config_exists", lambda _protocol: exists
    )

    nav = FakeNavigation()
    monkeypatch.setattr(handler, "navigation", nav)
    return nav


def select_protocol(bot, protocol="xray"):
    handler.handle_vpn_config_callback(
        bot, 501, make_call(), f"vpn_config:protocol:{protocol}"
    )


def test_protocol_selection_creates_default_draft(monkeypatch):
    nav = setup_admin(monkeypatch)
    bot = FakeBot()

    calls = []
    monkeypatch.setattr(
        handler, "setup_xray_server", lambda **params: calls.append(params)
    )

    select_protocol(bot)

    draft = handler._DRAFTS.get(("501", "77"))
    assert draft is not None
    assert draft["protocol"] == "xray"
    assert draft["params"]["port"] == handler.XRAY_DEFAULT_PORT
    assert draft["params"]["sni"] == handler.XRAY_DEFAULT_SNI
    assert draft["params"]["dest"] == handler.XRAY_DEFAULT_DEST
    assert draft["config_exists"] is False
    assert handler._ACTIVE_USERS.get("501") == 77
    assert calls == []
    assert ("go", 501, handler.ADMIN_VPN_CONFIG_PARAMS) in nav.calls


def test_xray_selection_loads_existing_inbound_parameters(monkeypatch):
    setup_admin(monkeypatch, exists=True)

    config = {
        "inbounds": [{
            "protocol": "vless",
            "port": 8443,
            "settings": {
                "clients": [
                    {"id": "one", "email": "one", "flow": "xtls-rprx-vision"},
                    {"id": "two", "email": "two", "flow": "xtls-rprx-vision"},
                ],
            },
            "streamSettings": {
                "network": "tcp",
                "security": "reality",
                "realitySettings": {
                    "dest": "example.org:443",
                    "serverNames": ["example.org"],
                },
            },
        }],
    }
    monkeypatch.setattr(handler, "load_xray_config", lambda: config)

    params = handler._initial_protocol_params("xray", True)

    assert params == {
        "port": 8443,
        "sni": "example.org",
        "dest": "example.org:443",
        "flow": "xtls-rprx-vision",
    }


def test_xray_selection_loads_none_flow(monkeypatch):
    setup_admin(monkeypatch, exists=True)
    config = {
        "inbounds": [{
            "protocol": "vless",
            "port": 443,
            "settings": {"clients": [{"id": "one", "email": "one"}]},
            "streamSettings": {
                "network": "tcp",
                "security": "reality",
                "realitySettings": {
                    "dest": "example.org:443",
                    "serverNames": ["example.org"],
                },
            },
        }],
    }
    monkeypatch.setattr(handler, "load_xray_config", lambda: config)

    params = handler._initial_protocol_params("xray", True)

    assert params["flow"] == ""


def test_xray_selection_rejects_multiple_vless_inbounds(monkeypatch):
    setup_admin(monkeypatch, exists=True)
    inbound = {
        "protocol": "vless",
        "port": 443,
        "settings": {"clients": [{"id": "one", "email": "one"}]},
        "streamSettings": {
            "network": "tcp",
            "security": "reality",
            "realitySettings": {
                "dest": "example.org:443",
                "serverNames": ["example.org"],
            },
        },
    }
    monkeypatch.setattr(
        handler, "load_xray_config",
        lambda: {"inbounds": [inbound, dict(inbound)]},
    )

    with pytest.raises(ValueError, match="ровно один VLESS inbound"):
        handler._initial_protocol_params("xray", True)


def test_xray_selection_rejects_mixed_client_flows(monkeypatch):
    setup_admin(monkeypatch, exists=True)
    config = {
        "inbounds": [{
            "protocol": "vless",
            "port": 443,
            "settings": {
                "clients": [
                    {"id": "one", "email": "one", "flow": "xtls-rprx-vision"},
                    {"id": "two", "email": "two", "flow": ""},
                ],
            },
            "streamSettings": {
                "network": "tcp",
                "security": "reality",
                "realitySettings": {
                    "dest": "example.org:443",
                    "serverNames": ["example.org"],
                },
            },
        }],
    }
    monkeypatch.setattr(handler, "load_xray_config", lambda: config)

    with pytest.raises(ValueError, match="разные Flow"):
        handler._initial_protocol_params("xray", True)


def test_awg_selection_loads_existing_interface_parameters(monkeypatch):
    setup_admin(monkeypatch, exists=True)
    bot = FakeBot()

    monkeypatch.setattr(
        handler,
        "get_awg_interface_params",
        lambda: {
            "listenport": "49152",
            "jc": "7",
            "jmin": "25",
            "jmax": "85",
            "s1": "111",
            "s2": "222",
            "s3": "333",
            "s4": "444",
            "h1": "11",
            "h2": "22",
            "h3": "33",
            "h4": "44",
        },
    )

    select_protocol(bot, "awg")

    draft = handler._DRAFTS.get(("501", "77"))
    assert draft["config_exists"] is True
    assert draft["params"] == {
        "port": 49152,
        "jc": 7,
        "jmin": 25,
        "jmax": 85,
        "s1": 111,
        "s2": 222,
        "s3": 333,
        "s4": 444,
        "h1": 11,
        "h2": 22,
        "h3": 33,
        "h4": 44,
    }


def test_awg_selection_uses_defaults_without_existing_config(monkeypatch):
    setup_admin(monkeypatch, exists=False)
    bot = FakeBot()

    def unexpected_read():
        raise AssertionError("Конфиг не должен читаться")

    monkeypatch.setattr(handler, "get_awg_interface_params", unexpected_read)

    select_protocol(bot, "awg")

    draft = handler._DRAFTS.get(("501", "77"))
    assert draft["params"]["port"] == handler.AWG_DEFAULT_PORT
    assert draft["params"]["jc"] == handler.AWG_DEFAULT_PARAMS["jc"]


def test_existing_config_shows_reconfiguration_warning(monkeypatch):
    setup_admin(monkeypatch, exists=True)
    bot = FakeBot()

    select_protocol(bot)
    handler._render_confirm_screen(bot, 501, 123)

    assert bot.edits
    args, kwargs = bot.edits[-1]
    text = args[0] if args else kwargs["text"]
    assert "конфигурация уже существует" in text.lower()
    assert "сохранением ключей" in text.lower()


def test_review_moves_to_confirmation_without_setup(monkeypatch):
    nav = setup_admin(monkeypatch)
    bot = FakeBot()
    calls = []

    monkeypatch.setattr(
        handler, "setup_xray_server", lambda **params: calls.append(params)
    )

    select_protocol(bot)
    handler.handle_vpn_config_callback(
        bot, 501, make_call(), "vpn_config:review:xray"
    )

    assert calls == []
    assert ("go", 501, handler.ADMIN_VPN_CONFIG_CONFIRM) in nav.calls
    assert any(call[0] == "render" for call in nav.calls)


def test_custom_parameters_update_draft_without_setup(monkeypatch):
    setup_admin(monkeypatch)
    bot = FakeBot()

    monkeypatch.setattr(handler, "telegram_bot", bot)
    monkeypatch.setattr(handler, "safe_delete", lambda *_args: None)

    calls = []
    monkeypatch.setattr(
        handler, "setup_xray_server", lambda **params: calls.append(params)
    )

    select_protocol(bot)
    handler._render_params_screen(bot, 501, 123)

    assert bot.step_handler == (501, handler._handle_custom_input)

    callback = bot.step_handler[1]
    message = SimpleNamespace(
        chat=SimpleNamespace(id=501),
        from_user=SimpleNamespace(id=77),
        message_id=456,
        text="port=8443\nsni=example.org",
    )
    callback(message)

    draft = handler._DRAFTS.get(("501", "77"))
    assert draft["params"]["port"] == 8443
    assert draft["params"]["sni"] == "example.org"
    assert draft["params"]["dest"] == handler.XRAY_DEFAULT_DEST
    assert calls == []
    assert bot.step_handler == (501, handler._handle_custom_input)


def test_confirm_aborts_if_config_state_changed(monkeypatch):
    nav = setup_admin(monkeypatch)
    state = {"exists": False}

    monkeypatch.setattr(
        handler,
        "protocol_config_exists",
        lambda _protocol: state["exists"],
    )

    bot = FakeBot()
    calls = []
    monkeypatch.setattr(
        handler, "setup_xray_server", lambda **params: calls.append(params)
    )

    select_protocol(bot)
    state["exists"] = True

    handler.handle_vpn_config_callback(
        bot, 501, make_call(), "vpn_config:confirm:xray"
    )

    assert calls == []
    assert handler._DRAFTS.get(("501", "77")) is None
    assert any(call[0] == "start" for call in nav.calls)
    assert any(
        "состояние конфигурации изменилось" in str(args).lower()
        for args, _kwargs in bot.answers
    )


def test_confirm_runs_setup_with_edited_parameters(monkeypatch):
    nav = setup_admin(monkeypatch)
    bot = FakeBot()
    calls = []

    monkeypatch.setattr(
        handler,
        "setup_xray_server",
        lambda **params: (
            calls.append(params)
            or SimpleNamespace(created=True, message="configured")
        ),
    )

    select_protocol(bot)
    draft = handler._DRAFTS[("501", "77")]
    draft["params"]["port"] = 8443
    draft["params"]["sni"] = "example.org"
    handler._DRAFTS[("501", "77")] = draft

    handler.handle_vpn_config_callback(
        bot, 501, make_call(), "vpn_config:confirm:xray"
    )

    assert len(calls) == 1
    assert calls[0]["port"] == 8443
    assert calls[0]["sni"] == "example.org"
    assert handler._DRAFTS.get(("501", "77")) is None
    assert ("replace", 501, handler.ADMIN_VPN_CONFIG_RESULT) in nav.calls


def test_unavailable_protocol_is_rejected(monkeypatch):
    setup_admin(monkeypatch, protocols=["awg"])
    bot = FakeBot()

    handler.handle_vpn_config_callback(
        bot, 501, make_call(), "vpn_config:protocol:xray"
    )

    assert handler._DRAFTS.get(("501", "77")) is None
    assert bot.answers
    assert bot.answers[-1][1].get("show_alert") is True


def test_non_admin_cannot_start_configuration(monkeypatch):
    monkeypatch.setattr(handler, "is_admin", lambda _cid: False)
    bot = FakeBot()

    handler.handle_vpn_config_callback(
        bot, 501, make_call(), "vpn_config:protocol:xray"
    )

    assert handler._DRAFTS.get(("501", "77")) is None
    assert bot.answers
    assert bot.answers[-1][1].get("show_alert") is True
