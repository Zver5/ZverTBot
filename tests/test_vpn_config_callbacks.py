from types import SimpleNamespace

import handlers.admin.vpn_config as handler


class FakeBot:
    def __init__(self):
        self.edits = []
        self.messages = []
        self.answers = []
        self.step_handler = None
        self.cleared = []

    def edit_message_text(self, *args, **kwargs):
        self.edits.append((args, kwargs))

    def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))
        return SimpleNamespace(message_id=10)

    def answer_callback_query(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    def clear_step_handler_by_chat_id(self, chat_id):
        self.cleared.append(chat_id)

    def register_next_step_handler(self, message, callback, *args):
        self.step_handler = (callback, args)


def make_call(chat_id=501, user_id=77):
    return SimpleNamespace(
        id="callback-id",
        from_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(
            chat=SimpleNamespace(id=chat_id),
            message_id=123,
        ),
    )


def setup_admin(monkeypatch, *, exists=False):
    monkeypatch.setattr(handler, "is_admin", lambda _cid: True)
    monkeypatch.setattr(
        handler, "get_configurable_protocols", lambda: ["xray", "awg"]
    )
    monkeypatch.setattr(
        handler, "protocol_config_exists", lambda _protocol: exists
    )


def test_auto_requires_confirmation_before_setup(monkeypatch):
    setup_admin(monkeypatch)
    bot = FakeBot()
    calls = []
    monkeypatch.setattr(
        handler, "setup_xray_server",
        lambda **params: (
            calls.append(params)
            or SimpleNamespace(created=True, message="created")
        ),
    )

    handler.handle_vpn_config_callback(
        bot, 501, make_call(), "vpn_config:auto:xray"
    )

    assert calls == []
    assert len(bot.edits) == 1
    text = bot.edits[-1][0][0]
    assert "\n" in text
    assert "будет создан" in text.lower()

    handler.handle_vpn_config_callback(
        bot, 501, make_call(), "vpn_config:confirm:xray"
    )

    assert len(calls) == 1
    assert calls[0]["port"] == handler.XRAY_DEFAULT_PORT
    assert handler._DRAFTS.get(("501", "77")) is None


def test_existing_config_shows_reconfiguration_warning(monkeypatch):
    setup_admin(monkeypatch, exists=True)
    bot = FakeBot()
    calls = []
    monkeypatch.setattr(
        handler, "setup_xray_server",
        lambda **params: calls.append(params),
    )

    handler.handle_vpn_config_callback(
        bot, 501, make_call(), "vpn_config:auto:xray"
    )

    assert calls == []
    text = bot.edits[-1][0][0]
    assert "конфигурация уже существует" in text
    assert "сохранением ключей" in text
    assert handler._DRAFTS.get(("501", "77"))["config_exists"] is True


def test_confirm_aborts_if_config_state_changed(monkeypatch):
    state = {"exists": False}
    monkeypatch.setattr(handler, "is_admin", lambda _cid: True)
    monkeypatch.setattr(
        handler, "get_configurable_protocols", lambda: ["xray"]
    )
    monkeypatch.setattr(
        handler, "protocol_config_exists",
        lambda _protocol: state["exists"],
    )
    bot = FakeBot()
    calls = []
    monkeypatch.setattr(
        handler, "setup_xray_server", lambda **params: calls.append(params)
    )

    handler.handle_vpn_config_callback(
        bot, 501, make_call(), "vpn_config:auto:xray"
    )
    state["exists"] = True

    handler.handle_vpn_config_callback(
        bot, 501, make_call(), "vpn_config:confirm:xray"
    )

    assert calls == []
    assert "состояние конфигурации изменилось" in bot.edits[-1][0][0].lower()
    assert handler._DRAFTS.get(("501", "77")) is None


def test_cancel_clears_draft_without_setup(monkeypatch):
    setup_admin(monkeypatch)
    bot = FakeBot()
    calls = []
    monkeypatch.setattr(
        handler, "setup_xray_server", lambda **params: calls.append(params)
    )

    handler.handle_vpn_config_callback(
        bot, 501, make_call(), "vpn_config:auto:xray"
    )
    assert handler._DRAFTS.get(("501", "77")) is not None

    handler.handle_vpn_config_callback(
        bot, 501, make_call(), "vpn_config:cancel"
    )

    assert calls == []
    assert handler._DRAFTS.get(("501", "77")) is None
    assert bot.cleared and all(cid == 501 for cid in bot.cleared)


def test_custom_xray_parameters_require_confirmation(monkeypatch):
    setup_admin(monkeypatch)
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

    handler.handle_vpn_config_callback(
        bot, 501, make_call(), "vpn_config:custom:xray"
    )

    assert bot.step_handler is not None
    callback, args = bot.step_handler
    assert callback is handler._handle_custom_input

    message = SimpleNamespace(
        chat=SimpleNamespace(id=501),
        from_user=SimpleNamespace(id=77),
        text="port=8443\nsni=example.org",
    )
    callback(message, *args)

    assert calls == []
    draft = handler._DRAFTS.get(("501", "77"))
    assert draft is not None
    assert draft["params"]["port"] == 8443
    assert draft["params"]["sni"] == "example.org"
    assert draft["params"]["dest"] == handler.XRAY_DEFAULT_DEST

    handler.handle_vpn_config_callback(
        bot, 501, make_call(), "vpn_config:confirm:xray"
    )

    assert len(calls) == 1
    assert calls[0]["port"] == 8443
    assert calls[0]["sni"] == "example.org"
    assert calls[0]["dest"] == handler.XRAY_DEFAULT_DEST
    assert handler._DRAFTS.get(("501", "77")) is None
