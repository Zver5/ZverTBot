from pathlib import Path


def test_render_protocol_screen_with_users(monkeypatch):
    from handlers.admin import clients

    bot = type("Bot", (), {})()
    bot.edit_message_text = lambda *args, **kwargs: None

    monkeypatch.setattr(clients, "get_users_list", lambda proto: ["alice", "bob"])
    monkeypatch.setattr(
        clients,
        "protocol_list_kb",
        lambda proto, users: "KB",
    )

    assert clients.render_protocol_screen(bot, 123, 456, "vless") is True


def test_render_protocol_screen_empty_users(monkeypatch):
    from handlers.admin import clients

    calls = []

    bot = type("Bot", (), {})()
    bot.edit_message_text = lambda *args, **kwargs: calls.append((args, kwargs))

    monkeypatch.setattr(clients, "get_users_list", lambda proto: [])
    monkeypatch.setattr(
        clients,
        "protocol_list_kb",
        lambda proto, users: "EMPTY_KB",
    )

    assert clients.render_protocol_screen(bot, 123, 456, "awg") is True

    assert calls
    assert calls[0][0][0] == "📭 AWG список пуст"


def test_render_protocol_screen_get_users_error(monkeypatch):
    from handlers.admin import clients

    bot = type("Bot", (), {})()
    bot.edit_message_text = lambda *args, **kwargs: None

    def fail(proto):
        raise RuntimeError("boom")

    monkeypatch.setattr(clients, "get_users_list", fail)
    monkeypatch.setattr(
        clients,
        "protocol_list_kb",
        lambda proto, users: "KB",
    )

    assert clients.render_protocol_screen(bot, 123, 456, "vless") is True


def test_render_protocol_screen_edit_error_returns_false(monkeypatch):
    from handlers.admin import clients

    bot = type("Bot", (), {})()

    def fail(*args, **kwargs):
        raise RuntimeError("edit failed")

    bot.edit_message_text = fail

    monkeypatch.setattr(clients, "get_users_list", lambda proto: ["alice"])
    monkeypatch.setattr(
        clients,
        "protocol_list_kb",
        lambda proto, users: "KB",
    )

    assert clients.render_protocol_screen(bot, 123, 456, "vless") is False


def test_render_protocol_screen_message_not_modified_is_ignored(monkeypatch):
    from handlers.admin import clients

    bot = type("Bot", (), {})()

    def fail(*args, **kwargs):
        raise RuntimeError("message is not modified")

    bot.edit_message_text = fail

    monkeypatch.setattr(clients, "get_users_list", lambda proto: ["alice"])
    monkeypatch.setattr(
        clients,
        "protocol_list_kb",
        lambda proto, users: "KB",
    )

    assert clients.render_protocol_screen(bot, 123, 456, "vless") is True


def test_handle_add_input_denies_non_admin(monkeypatch):
    from handlers.admin import clients

    message = type("Message", (), {})()
    message.chat = type("Chat", (), {"id": 123})()
    message.text = "alice"

    monkeypatch.setattr(clients, "is_admin", lambda cid: False)

    assert clients.handle_add_input(message, "add_vless") is None


def test_handle_add_input_starts_command(monkeypatch):
    from handlers.admin import clients

    message = type("Message", (), {})()
    message.chat = type("Chat", (), {"id": 123})()
    message.text = "/start"

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)

    calls = []
    monkeypatch.setattr(
        "handlers.commands.cmd_start",
        lambda msg: calls.append(msg),
    )

    clients.handle_add_input(message, "add_vless")

    assert calls == [message]


def test_handle_add_input_rejects_empty_username(monkeypatch):
    from handlers.admin import clients

    message = type("Message", (), {})()
    message.chat = type("Chat", (), {"id": 123})()
    message.text = "   "

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)
    monkeypatch.setattr(clients, "main_menu_kb", lambda: "MAIN_KB")

    clients.bot = type("Bot", (), {})()
    calls = []
    clients.bot.send_message = lambda *args, **kwargs: calls.append((args, kwargs))

    clients.handle_add_input(message, "add_vless")

    assert calls == [
        (
            (123, "❌ Пустое имя"),
            {"reply_markup": "MAIN_KB"},
        )
    ]


def test_handle_add_input_rejects_unknown_protocol(monkeypatch):
    from handlers.admin import clients

    message = type("Message", (), {})()
    message.chat = type("Chat", (), {"id": 123})()
    message.text = "alice"

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)
    monkeypatch.setattr(clients, "main_menu_kb", lambda: "MAIN_KB")
    monkeypatch.setattr(
        clients,
        "safe_delete",
        lambda *args: None,
    )

    progress = type("Message", (), {"message_id": 456})()

    clients.bot = type("Bot", (), {})()
    calls = []

    def send_message(*args, **kwargs):
        calls.append((args, kwargs))
        return progress

    clients.bot.send_message = send_message

    clients.handle_add_input(message, "unknown")

    assert calls[0][0] == (123, "⏳ Создаю клиента alice...")
    assert calls[1] == (
        (123, "❌ Ошибка: неизвестный протокол"),
        {"reply_markup": "MAIN_KB"},
    )


def test_handle_add_input_vless_creation_error_result(monkeypatch):
    from handlers.admin import clients

    message = type("Message", (), {})()
    message.chat = type("Chat", (), {"id": 123})()
    message.text = "alice"

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)
    monkeypatch.setattr(clients, "main_menu_kb", lambda: "MAIN_KB")

    progress = type("Message", (), {"message_id": 456})()

    clients.bot = type("Bot", (), {})()
    calls = []

    def send_message(*args, **kwargs):
        calls.append((args, kwargs))
        return progress

    clients.bot.send_message = send_message

    monkeypatch.setattr(
        "services.xray.client_manager.xray_add_user",
        lambda username: (False, "VLESS error"),
    )
    monkeypatch.setattr(
        clients,
        "safe_delete",
        lambda *args: None,
    )

    clients.handle_add_input(message, "add_vless")

    assert calls[-1] == (
        (123, "VLESS error"),
        {"reply_markup": "MAIN_KB"},
    )


def test_handle_add_input_success_deletes_input_message(monkeypatch):
    from handlers.admin import clients

    message = type("Message", (), {})()
    message.chat = type("Chat", (), {"id": 123})()
    message.text = "alice"

    clients.INPUT_REQUEST_MSGS.clear()
    clients.INPUT_REQUEST_MSGS[123] = 999

    monkeypatch.setattr(
        clients,
        "is_admin",
        lambda cid: True,
    )
    monkeypatch.setattr(
        clients,
        "safe_delete",
        lambda *args: calls.append(args),
    )
    monkeypatch.setattr(
        clients,
        "log_action",
        lambda *args: None,
    )
    monkeypatch.setattr(
        clients,
        "build_client_card",
        lambda username, proto: "CARD",
    )
    monkeypatch.setattr(
        clients,
        "client_card_kb",
        lambda proto, username: "KB",
    )
    monkeypatch.setattr(
        "services.xray.client_manager.xray_add_user",
        lambda username: (True, "OK"),
    )

    calls = []

    class Bot:
        def send_message(self, *args, **kwargs):
            return type("Message", (), {"message_id": 1234})()

        def clear_step_handler_by_chat_id(self, cid):
            pass

    clients.bot = Bot()

    clients.handle_add_input(message, "add_vless")

    assert any(args[:3] == (clients.bot, 123, 999) for args in calls)
    assert 123 not in clients.INPUT_REQUEST_MSGS


def test_handle_add_input_success_vless(monkeypatch):
    from handlers.admin import clients

    message = type("Message", (), {})()
    message.chat = type("Chat", (), {"id": 123})()
    message.text = "alice"

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)

    progress = type("Message", (), {"message_id": 456})()

    clients.bot = type("Bot", (), {})()
    calls = []

    def send_message(*args, **kwargs):
        calls.append((args, kwargs))
        return progress

    clients.bot.send_message = send_message
    clients.bot.clear_step_handler_by_chat_id = lambda cid: None

    monkeypatch.setattr(
        "services.xray.client_manager.xray_add_user",
        lambda username: (True, "created"),
    )
    monkeypatch.setattr(clients, "safe_delete", lambda *args: None)
    monkeypatch.setattr(
        clients,
        "build_client_card",
        lambda username, proto: "CLIENT_CARD",
    )
    monkeypatch.setattr(
        clients,
        "client_card_kb",
        lambda proto, username: "CLIENT_KB",
    )
    monkeypatch.setattr(clients, "log_action", lambda *args: None)

    clients.handle_add_input(message, "add_vless")

    assert calls[-1] == (
        (123, "CLIENT_CARD"),
        {
            "parse_mode": "Markdown",
            "reply_markup": "CLIENT_KB",
        },
    )


def _rename_message(text, cid=123):
    message = type("Message", (), {})()
    message.chat = type("Chat", (), {"id": cid})()
    message.message_id = 456
    message.text = text
    return message


def test_process_rename_menu_rejects_invalid_format(monkeypatch):
    from handlers.admin import clients

    message = _rename_message("only_one_name")

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)
    monkeypatch.setattr(clients, "safe_delete", lambda *args, **kwargs: None)

    calls = []
    monkeypatch.setattr(
        clients,
        "_render_rename_screen",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    clients.INPUT_REQUEST_MSGS[123] = 999

    clients.bot = type("Bot", (), {})()
    clients.bot.register_next_step_handler_by_chat_id = lambda *args: None

    clients.process_rename_menu(message)

    assert calls
    assert "❌ Формат" in calls[0][0][3]


def test_process_rename_menu_rejects_invalid_new_username(monkeypatch):
    from handlers.admin import clients

    message = _rename_message("old_name bad/name")

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)
    monkeypatch.setattr(clients, "safe_delete", lambda *args, **kwargs: None)
    monkeypatch.setattr(clients, "validate_username", lambda name: False)

    calls = []
    monkeypatch.setattr(
        clients,
        "_render_rename_screen",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    clients.INPUT_REQUEST_MSGS[123] = 999
    clients.bot = type("Bot", (), {})()
    clients.bot.register_next_step_handler_by_chat_id = lambda *args: None

    clients.process_rename_menu(message)

    assert calls
    assert "❌ Новое имя" in calls[0][0][3]


def test_process_rename_menu_rejects_missing_client(monkeypatch):
    from handlers.admin import clients

    message = _rename_message("missing new_name")

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)
    monkeypatch.setattr(clients, "safe_delete", lambda *args, **kwargs: None)
    monkeypatch.setattr(clients, "validate_username", lambda name: True)
    monkeypatch.setattr(
        clients,
        "get_users_list",
        lambda proto: ["alice"] if proto == "vless" else [],
    )

    calls = []
    monkeypatch.setattr(
        clients,
        "_render_rename_screen",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    clients.INPUT_REQUEST_MSGS[123] = 999
    clients.bot = type("Bot", (), {})()
    clients.bot.register_next_step_handler_by_chat_id = lambda *args: None

    clients.process_rename_menu(message)

    assert calls
    assert "не найден" in calls[0][0][3]


def test_process_rename_menu_rejects_taken_name_case_insensitive(monkeypatch):
    from handlers.admin import clients

    message = _rename_message("alice BOB")

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)
    monkeypatch.setattr(clients, "safe_delete", lambda *args, **kwargs: None)
    monkeypatch.setattr(clients, "validate_username", lambda name: True)
    monkeypatch.setattr(
        clients,
        "get_users_list",
        lambda proto: ["alice", "Bob"] if proto == "vless" else [],
    )

    calls = []
    monkeypatch.setattr(
        clients,
        "_render_rename_screen",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    clients.INPUT_REQUEST_MSGS[123] = 999
    clients.bot = type("Bot", (), {})()
    clients.bot.register_next_step_handler_by_chat_id = lambda *args: None

    clients.process_rename_menu(message)

    assert calls
    assert "уже занято" in calls[0][0][3]


def test_process_rename_menu_success(monkeypatch):
    from handlers.admin import clients

    message = _rename_message("alice alice_new")

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)
    monkeypatch.setattr(clients, "safe_delete", lambda *args, **kwargs: None)
    monkeypatch.setattr(clients, "validate_username", lambda name: True)
    monkeypatch.setattr(
        clients,
        "get_users_list",
        lambda proto: ["alice"] if proto == "vless" else [],
    )
    monkeypatch.setattr(clients, "rename_client", lambda old, new: [])
    monkeypatch.setattr(clients, "log_action", lambda *args: None)
    monkeypatch.setattr(
        "core.navigation.navigation.back",
        lambda cid: "clients",
    )
    monkeypatch.setattr(clients, "clients_menu_kb", lambda: "CLIENTS_KB")

    calls = []
    edits = []

    progress_msg = type("Message", (), {"message_id": 777})()

    clients.INPUT_REQUEST_MSGS[123] = 999
    clients.bot = type("Bot", (), {})()
    clients.bot.send_message = lambda *args, **kwargs: (
        calls.append((args, kwargs)) or progress_msg
    )
    clients.bot.edit_message_text = lambda *args, **kwargs: edits.append((args, kwargs))

    clients.process_rename_menu(message)

    assert edits
    assert "Успешно переименовано" in edits[0][0][0]
    assert any("👥 *Клиенты*" in args for args, _ in calls)
    assert 123 not in clients.INPUT_REQUEST_MSGS


def test_process_rename_menu_reports_partial_failure(monkeypatch):
    from handlers.admin import clients

    message = _rename_message("alice alice_new")

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)
    monkeypatch.setattr(clients, "safe_delete", lambda *args, **kwargs: None)
    monkeypatch.setattr(clients, "validate_username", lambda name: True)
    monkeypatch.setattr(
        clients,
        "get_users_list",
        lambda proto: ["alice"] if proto == "vless" else [],
    )
    monkeypatch.setattr(
        clients,
        "rename_client",
        lambda old, new: ["VLESS: failed"],
    )

    calls = []

    clients.INPUT_REQUEST_MSGS[123] = 999
    clients.bot = type("Bot", (), {})()
    progress_msg = type("Message", (), {"message_id": 777})()
    clients.bot.send_message = lambda *args, **kwargs: (
        calls.append((args, kwargs)) or progress_msg
    )

    clients.process_rename_menu(message)

    assert any("⚠️ Частично выполнено:" in args[1] for args, _ in calls)
    assert any("VLESS: failed" in args[1] for args, _ in calls)


def test_handle_add_input_success_awg(monkeypatch):
    from handlers.admin import clients

    message = type("Message", (), {})()
    message.chat = type("Chat", (), {"id": 123})()
    message.text = "alice"

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)

    progress = type("Message", (), {"message_id": 456})()

    clients.bot = type("Bot", (), {})()
    calls = []

    def send_message(*args, **kwargs):
        calls.append((args, kwargs))
        return progress

    clients.bot.send_message = send_message
    clients.bot.clear_step_handler_by_chat_id = lambda cid: None

    monkeypatch.setattr(
        "services.awg.client_manager.awg_add_user",
        lambda username: (True, "created"),
    )
    monkeypatch.setattr(clients, "safe_delete", lambda *args: None)
    monkeypatch.setattr(
        clients,
        "build_client_card",
        lambda username, proto: "CLIENT_CARD",
    )
    monkeypatch.setattr(
        clients,
        "client_card_kb",
        lambda proto, username: "CLIENT_KB",
    )
    monkeypatch.setattr(clients, "log_action", lambda *args: None)

    clients.handle_add_input(message, "add_awg")

    assert calls[-1] == (
        (123, "CLIENT_CARD"),
        {
            "parse_mode": "Markdown",
            "reply_markup": "CLIENT_KB",
        },
    )


def test_handle_add_input_clear_step_handler_error(monkeypatch):
    from handlers.admin import clients

    message = type("Message", (), {})()
    message.chat = type("Chat", (), {"id": 123})()
    message.text = "alice"

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)

    progress = type("Message", (), {"message_id": 456})()

    clients.bot = type("Bot", (), {})()
    calls = []

    def send_message(*args, **kwargs):
        calls.append((args, kwargs))
        return progress

    clients.bot.send_message = send_message

    def clear_step_handler_by_chat_id(cid):
        raise RuntimeError("clear failed")

    clients.bot.clear_step_handler_by_chat_id = clear_step_handler_by_chat_id

    monkeypatch.setattr(
        "services.xray.client_manager.xray_add_user",
        lambda username: (True, "created"),
    )
    monkeypatch.setattr(clients, "safe_delete", lambda *args: None)
    monkeypatch.setattr(
        clients,
        "build_client_card",
        lambda username, proto: "CLIENT_CARD",
    )
    monkeypatch.setattr(
        clients,
        "client_card_kb",
        lambda proto, username: "CLIENT_KB",
    )
    monkeypatch.setattr(clients, "log_action", lambda *args: None)

    clients.handle_add_input(message, "add_vless")

    assert calls[-1] == (
        (123, "CLIENT_CARD"),
        {
            "parse_mode": "Markdown",
            "reply_markup": "CLIENT_KB",
        },
    )


def test_render_rename_screen_renders_and_registers_handler(monkeypatch):
    from handlers.admin import clients

    clients.bot = type("Bot", (), {})()
    calls = []
    registered = []

    clients.bot.edit_message_text = lambda *args, **kwargs: calls.append((args, kwargs))
    clients.bot.register_next_step_handler_by_chat_id = lambda *args: registered.append(
        args
    )

    monkeypatch.setattr(
        clients.types.InlineKeyboardMarkup,
        "add",
        lambda self, *args: self,
    )

    clients._render_rename_screen(clients.bot, 123, 456)

    assert clients.INPUT_REQUEST_MSGS[123] == 456
    assert calls
    assert calls[0][1]["text"].startswith("✏️ *Смена имени клиента*")
    assert calls[0][1]["chat_id"] == 123
    assert calls[0][1]["message_id"] == 456
    assert registered == [(123, clients.process_rename_menu)]


def test_process_rename_menu_ignores_non_admin(monkeypatch):
    from handlers.admin import clients

    message = _rename_message("alice bob")

    monkeypatch.setattr(clients, "is_admin", lambda cid: False)

    clients.bot = type("Bot", (), {})()
    clients.bot.send_message = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("send_message не должен вызываться")
    )

    clients.process_rename_menu(message)


def test_render_rename_screen_renders_error(monkeypatch):
    from handlers.admin import clients

    clients.bot = type("Bot", (), {})()
    calls = []

    clients.bot.edit_message_text = lambda *args, **kwargs: calls.append((args, kwargs))
    clients.bot.register_next_step_handler_by_chat_id = lambda *args: None

    monkeypatch.setattr(
        clients.types.InlineKeyboardMarkup,
        "add",
        lambda self, *args: self,
    )

    clients._render_rename_screen(
        clients.bot,
        123,
        456,
        error="❌ Тестовая ошибка",
    )

    assert calls
    assert "❌ Тестовая ошибка" in calls[0][1]["text"]
    assert "✏️ *Смена имени клиента*" in calls[0][1]["text"]


def test_handle_lists_delete_callback_ask_delete(monkeypatch):
    from handlers.admin import clients

    bot = type("Bot", (), {})()
    bot.edit_message_text = lambda *args, **kwargs: setattr(
        bot, "edit_call", (args, kwargs)
    )
    call = type("Call", (), {})()
    call.message = type("Message", (), {"message_id": 456})()

    result = clients.handle_lists_delete_callback(bot, 123, call, "ask_del:vless:alice")

    assert result.text is None
    assert bot.edit_call[0][0].startswith("⚠️ *Вы уверены")
    assert bot.edit_call[0][1:] == (123, 456)


def test_handle_lists_delete_callback_confirm_success(monkeypatch):
    from handlers.admin import clients

    calls = []

    bot = type("Bot", (), {})()
    bot.edit_message_text = lambda *args, **kwargs: calls.append((args, kwargs))

    call = type("Call", (), {})()
    call.message = type("Message", (), {"message_id": 456})()

    monkeypatch.setattr(
        clients,
        "delete_client_service",
        lambda username, proto: None,
    )
    monkeypatch.setattr(
        clients,
        "get_users_list",
        lambda proto: ["bob"],
    )
    monkeypatch.setattr(
        clients,
        "protocol_list_kb",
        lambda proto, users: "KB",
    )
    monkeypatch.setattr(clients, "log_action", lambda *args: None)

    class ImmediateThread:
        def __init__(self, target, daemon=True):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(clients.threading, "Thread", ImmediateThread)

    result = clients.handle_lists_delete_callback(
        bot, 123, call, "confirm_del:vless:alice"
    )

    assert result.text == "⏳ Удаляю..."
    assert len(calls) == 2
    assert "⏳ Удаляю клиента" in calls[0][0][0]
    assert "✅ `alice` успешно удалён" in calls[1][0][0]


def test_handle_lists_delete_callback_confirm_error(monkeypatch):
    from handlers.admin import clients

    calls = []

    bot = type("Bot", (), {})()
    bot.edit_message_text = lambda *args, **kwargs: calls.append((args, kwargs))

    call = type("Call", (), {})()
    call.message = type("Message", (), {"message_id": 456})()

    monkeypatch.setattr(
        clients,
        "delete_client_service",
        lambda username, proto: (_ for _ in ()).throw(RuntimeError("delete failed")),
    )

    class ImmediateThread:
        def __init__(self, target, daemon=True):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(clients.threading, "Thread", ImmediateThread)

    result = clients.handle_lists_delete_callback(
        bot, 123, call, "confirm_del:awg:alice"
    )

    assert result.text == "⏳ Удаляю..."
    assert "❌ delete failed" in calls[-1][0][0]


def test_handle_search_callback_vless(monkeypatch):
    from handlers.admin import clients

    calls = []
    registered = []

    bot = type("Bot", (), {})()
    bot.edit_message_text = lambda *args, **kwargs: calls.append((args, kwargs))
    bot.register_next_step_handler = lambda *args: registered.append(args)

    call = type("Call", (), {})()
    call.message = type("Message", (), {"message_id": 456})()

    result = clients.handle_search_callback(
        bot,
        123,
        call,
        clients.NAV_CLIENTS_SEARCH_VLESS_CALLBACK,
    )

    assert result.text is None
    assert clients.INPUT_REQUEST_MSGS[123] == 456
    assert registered[0][0] is call.message
    assert registered[0][2] == "vless"
    assert "Введите имя клиента" in calls[0][0][0]


def test_handle_search_callback_unknown_returns_false(monkeypatch):
    from handlers.admin import clients

    bot = type("Bot", (), {})()
    call = type("Call", (), {})()

    assert clients.handle_search_callback(bot, 123, call, "unknown_search") is False


def test_process_search_input_non_admin(monkeypatch):
    from handlers.admin import clients

    message = type("Message", (), {})()
    message.chat = type("Chat", (), {"id": 123})()
    message.text = "alice"

    monkeypatch.setattr(clients, "is_admin", lambda cid: False)

    assert clients.process_search_input(message, "vless") is None


def test_process_search_input_found(monkeypatch):
    from handlers.admin import clients

    calls = []

    message = type("Message", (), {})()
    message.chat = type("Chat", (), {"id": 123})()
    message.text = "AL"

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)
    monkeypatch.setattr(clients, "get_users_list", lambda proto: ["alice", "bob"])
    monkeypatch.setattr(clients, "protocol_list_kb", lambda proto, users: "KB")
    monkeypatch.setattr(clients, "safe_delete", lambda *args: None)

    clients.INPUT_REQUEST_MSGS[123] = 999
    clients.bot = type("Bot", (), {})()
    clients.bot.send_message = lambda *args, **kwargs: calls.append((args, kwargs))

    clients.process_search_input(message, "vless")

    assert 123 not in clients.INPUT_REQUEST_MSGS
    assert calls[0][0] == (123, "🔍 Найдено 1 клиентов:")
    assert calls[0][1]["reply_markup"] == "KB"


def test_process_search_input_not_found(monkeypatch):
    from handlers.admin import clients

    calls = []

    message = type("Message", (), {})()
    message.chat = type("Chat", (), {"id": 123})()
    message.text = "zzz"

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)
    monkeypatch.setattr(clients, "get_users_list", lambda proto: ["alice"])
    monkeypatch.setattr(clients, "safe_delete", lambda *args: None)

    clients.bot = type("Bot", (), {})()
    clients.bot.send_message = lambda *args, **kwargs: calls.append((args, kwargs))

    clients.process_search_input(message, "vless")

    assert "❌ Клиенты не найдены" in calls[0][0][1]


def test_handle_create_client_callback(monkeypatch):
    from handlers.admin import clients

    calls = []
    registered = []

    bot = type("Bot", (), {})()
    bot.clear_step_handler_by_chat_id = lambda cid: calls.append(("clear", cid))
    bot.edit_message_text = lambda *args, **kwargs: calls.append(("edit", args, kwargs))
    bot.register_next_step_handler = lambda *args: registered.append(args)

    call = type("Call", (), {})()
    call.message = type("Message", (), {"message_id": 456})()

    result = clients.handle_create_client_callback(bot, 123, call, "add_vless")

    assert result.text is None
    assert calls[0] == ("clear", 123)
    assert "Введите имя пользователя VLESS" in calls[1][1][0]
    assert clients.INPUT_REQUEST_MSGS[123] == 456
    assert registered[0][2] == "add_vless"


def test_handle_create_client_callback_unknown(monkeypatch):
    from handlers.admin import clients

    bot = type("Bot", (), {})()
    call = type("Call", (), {})()

    assert clients.handle_create_client_callback(bot, 123, call, "unknown") is False


def test_process_rename_menu_reply_to_message_branches(monkeypatch):
    from handlers.admin import clients

    message = _rename_message("only_one")

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)
    monkeypatch.setattr(clients, "safe_delete", lambda *args, **kwargs: None)
    monkeypatch.setattr(clients, "validate_username", lambda name: False)

    class Bot:
        def __init__(self):
            self.calls = []

        def reply_to(self, *args, **kwargs):
            self.calls.append((args, kwargs))

        def register_next_step_handler_by_chat_id(self, *args):
            self.registered = args

        def send_message(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return type("Message", (), {"message_id": 777})()

    clients.bot = Bot()
    clients.INPUT_REQUEST_MSGS.pop(123, None)

    clients.process_rename_menu(message)

    assert clients.bot.calls
    assert "❌ Формат" in clients.bot.calls[0][0][1]

    message = _rename_message("old bad/name")
    clients.bot.calls.clear()
    clients.INPUT_REQUEST_MSGS.pop(123, None)

    clients.process_rename_menu(message)

    assert "❌ Новое имя" in clients.bot.calls[0][0][1]


def test_process_rename_menu_reply_to_message_missing_and_taken(monkeypatch):
    from handlers.admin import clients

    class Bot:
        def __init__(self):
            self.calls = []

        def reply_to(self, *args, **kwargs):
            self.calls.append((args, kwargs))

        def register_next_step_handler_by_chat_id(self, *args):
            self.registered = args

        def send_message(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return type("Message", (), {"message_id": 777})()

    clients.bot = Bot()
    monkeypatch.setattr(clients, "is_admin", lambda cid: True)
    monkeypatch.setattr(clients, "safe_delete", lambda *args, **kwargs: None)
    monkeypatch.setattr(clients, "validate_username", lambda name: True)

    monkeypatch.setattr(
        clients,
        "get_users_list",
        lambda proto: ["alice", "bob"] if proto == "vless" else [],
    )

    clients.INPUT_REQUEST_MSGS.pop(123, None)
    clients.process_rename_menu(_rename_message("missing new"))

    assert "не найден" in clients.bot.calls[0][0][1]

    clients.bot.calls.clear()
    clients.process_rename_menu(_rename_message("alice BOB"))

    assert "уже занято" in clients.bot.calls[0][0][1]


def test_handle_qr_config_qr_and_conf_invalid_callbacks(monkeypatch):
    from handlers.admin import clients

    bot = type("Bot", (), {})()
    call = type("Call", (), {"message": type("Message", (), {"message_id": 1})()})()

    assert (
        clients.handle_qr_config_callback(bot, 123, call, "qr:").text
        == "❌ Некорректный QR callback"
    )

    assert (
        clients.handle_qr_config_callback(bot, 123, call, "qr:bad:alice").text
        == "❌ Неизвестный протокол"
    )

    assert (
        clients.handle_qr_config_callback(bot, 123, call, "conf:").text
        == "❌ Некорректный config callback"
    )

    assert (
        clients.handle_qr_config_callback(bot, 123, call, "conf:bad:alice").text
        == "❌ Неизвестный протокол"
    )


def test_handle_qr_config_unified_qr(monkeypatch):
    from handlers.admin import clients

    calls = []

    monkeypatch.setattr(
        clients,
        "send_qr_or_conf",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    bot = type("Bot", (), {})()
    call = type("Call", (), {})()

    result = clients.handle_qr_config_callback(bot, 123, call, "qr:vless:alice")

    assert result.text == "📤 Отправляю для alice"
    assert calls[0][0][1:4] == (123, "alice", "vless")


def test_handle_qr_config_unified_conf_awg(monkeypatch):
    from handlers.admin import clients

    calls = []

    monkeypatch.setattr(
        clients,
        "send_qr_or_conf",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    bot = type("Bot", (), {})()
    call = type("Call", (), {})()

    result = clients.handle_qr_config_callback(bot, 123, call, "conf:awg:alice")

    assert result.text == "📄 Отправляю конфиг для alice"
    assert calls[0][1] == {"config_only": False}


def test_handle_qr_config_unified_conf_vless_with_ru_file(monkeypatch):
    from handlers.admin import clients

    calls = []

    monkeypatch.setattr(
        clients,
        "send_qr_or_conf",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    monkeypatch.setattr(clients.os.path, "isfile", lambda path: True)

    sent = []

    class FileBot:
        def send_document(self, *args, **kwargs):
            sent.append((args, kwargs))

    class FakeFile:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("builtins.open", lambda *args, **kwargs: FakeFile())

    result = clients.handle_qr_config_callback(FileBot(), 123, None, "conf:vless:alice")

    assert result.text == "📄 Отправляю конфиг для alice"
    assert calls[0][1] == {"config_only": True}
    assert len(sent) == 1


def test_render_protocol_screen_helpers_and_unknown_callback(monkeypatch):
    from handlers.admin import clients

    class Bot:
        def edit_message_text(self, *args, **kwargs):
            self.calls = (args, kwargs)

    bot = Bot()
    monkeypatch.setattr(clients, "get_users_list", lambda proto: ["alice"])

    assert clients._render_vless_screen(bot, 123, 10) is True
    assert clients._render_awg_screen(bot, 123, 11) is True

    result = clients.handle_create_client_callback(bot, 123, None, "unknown")
    assert result is False


def test_render_protocol_screen_edit_error(monkeypatch):
    from handlers.admin import clients

    class Bot:
        def edit_message_text(self, *args, **kwargs):
            raise RuntimeError("edit failed")

    monkeypatch.setattr(clients, "get_users_list", lambda proto: ["alice"])

    assert clients.render_protocol_screen(Bot(), 123, 10, "vless") is False


def test_process_search_input_safe_delete_error(monkeypatch):
    from handlers.admin import clients

    sent = []

    class Bot:
        def send_message(self, *args, **kwargs):
            sent.append((args, kwargs))

    clients.bot = Bot()
    clients.INPUT_REQUEST_MSGS[123] = 555

    monkeypatch.setattr(clients, "is_admin", lambda cid: True)

    def broken_delete(*args, **kwargs):
        raise RuntimeError("delete failed")

    monkeypatch.setattr(clients, "safe_delete", broken_delete)
    monkeypatch.setattr(clients, "get_users_list", lambda proto: ["alice"])

    message = type(
        "Message",
        (),
        {
            "chat": type("Chat", (), {"id": 123})(),
            "text": "alice",
        },
    )()

    clients.process_search_input(message, "vless")

    assert sent
    assert "Найдено 1" in sent[0][0][1]


def test_handle_qr_config_qr_select_both(monkeypatch):
    from handlers.admin import clients

    sent = []
    removed = []

    class Bot:
        def send_photo(self, *args, **kwargs):
            sent.append((args, kwargs))

    monkeypatch.setattr(
        clients,
        "load_xray_config",
        lambda: {"inbounds": []},
    )
    monkeypatch.setattr(
        clients,
        "get_vless_inbounds",
        lambda config: [{"port": 443}, {"port": 2096}],
    )
    monkeypatch.setattr(
        clients,
        "xray_get_link_for_port",
        lambda username, port: f"vless://{username}:{port}",
    )

    def fake_qrencode(*args, **kwargs):
        cmd = args[0]
        output = cmd[cmd.index("-o") + 1]
        Path(output).write_bytes(b"fake-png")

    monkeypatch.setattr(clients.subprocess, "run", fake_qrencode)
    monkeypatch.setattr(clients.os.path, "exists", lambda path: True)
    monkeypatch.setattr(clients.os, "remove", lambda path: removed.append(path))

    result = clients.handle_qr_config_callback(Bot(), 123, None, "qr_select_alice_both")

    assert result.text is None
    assert len(sent) == 2
    assert len(removed) == 2


def test_handle_qr_config_qr_select_specific_port(monkeypatch):
    from handlers.admin import clients

    sent = []

    class Bot:
        def send_photo(self, *args, **kwargs):
            sent.append((args, kwargs))

    monkeypatch.setattr(
        clients,
        "load_xray_config",
        lambda: {"inbounds": []},
    )
    monkeypatch.setattr(
        clients,
        "get_vless_inbounds",
        lambda config: [{"port": 443}, {"port": 2096}],
    )
    monkeypatch.setattr(
        clients,
        "xray_get_link_for_port",
        lambda username, port: "vless://test",
    )

    def fake_qrencode(*args, **kwargs):
        cmd = args[0]
        output = cmd[cmd.index("-o") + 1]
        Path(output).write_bytes(b"fake-png")

    monkeypatch.setattr(clients.subprocess, "run", fake_qrencode)
    monkeypatch.setattr(clients.os.path, "exists", lambda path: False)

    result = clients.handle_qr_config_callback(Bot(), 123, None, "qr_select_alice*443")

    assert result.text is None
    assert len(sent) == 1


def test_handle_qr_config_qr_select_username_without_port(monkeypatch):
    from handlers.admin import clients

    sent = []

    class Bot:
        def send_photo(self, *args, **kwargs):
            sent.append((args, kwargs))

    monkeypatch.setattr(clients, "load_xray_config", lambda: {})
    monkeypatch.setattr(
        clients,
        "get_vless_inbounds",
        lambda config: [{"port": 443}],
    )
    monkeypatch.setattr(
        clients,
        "xray_get_link_for_port",
        lambda username, port: None,
    )

    result = clients.handle_qr_config_callback(Bot(), 123, None, "qr_select_alice")

    assert result.text is None
    assert sent == []


def test_handle_qr_config_qr_select_qrencode_failure(monkeypatch):
    from handlers.admin import clients

    class Bot:
        def send_photo(self, *args, **kwargs):
            raise AssertionError("send_photo не должен вызываться")

    monkeypatch.setattr(clients, "load_xray_config", lambda: {})
    monkeypatch.setattr(
        clients,
        "get_vless_inbounds",
        lambda config: [{"port": 443}],
    )
    monkeypatch.setattr(
        clients,
        "xray_get_link_for_port",
        lambda username, port: "vless://test",
    )

    def fail_run(*args, **kwargs):
        raise RuntimeError("qrencode failed")

    monkeypatch.setattr(clients.subprocess, "run", fail_run)
    monkeypatch.setattr(clients.os.path, "exists", lambda path: False)

    try:
        clients.handle_qr_config_callback(Bot(), 123, None, "qr_select_alice*443")
    except RuntimeError as exc:
        assert str(exc) == "qrencode failed"
    else:
        raise AssertionError("Ожидалось исключение qrencode")


def test_handle_qr_config_qr_select_third_port_caption(monkeypatch):
    from handlers.admin import clients

    sent = []

    class Bot:
        def send_photo(self, *args, **kwargs):
            sent.append((args, kwargs))

    monkeypatch.setattr(
        clients,
        "load_xray_config",
        lambda: {"inbounds": []},
    )
    monkeypatch.setattr(
        clients,
        "get_vless_inbounds",
        lambda config: [{"port": 443}, {"port": 2096}, {"port": 8443}],
    )
    monkeypatch.setattr(
        clients,
        "xray_get_link_for_port",
        lambda username, port: f"vless://{username}:{port}",
    )

    def fake_qrencode(*args, **kwargs):
        cmd = args[0]
        output = cmd[cmd.index("-o") + 1]
        Path(output).write_bytes(b"fake-png")

    monkeypatch.setattr(clients.subprocess, "run", fake_qrencode)

    result = clients.handle_qr_config_callback(Bot(), 123, None, "qr_select_alice_both")

    assert result.text is None
    assert len(sent) == 3
    assert "VLESS:8443" in sent[2][1]["caption"]


def test_render_protocol_screen_message_not_modified(monkeypatch):
    from handlers.admin import clients

    class Bot:
        def edit_message_text(self, *args, **kwargs):
            raise RuntimeError("message is not modified")

    monkeypatch.setattr(clients, "get_users_list", lambda proto: ["alice"])

    assert clients.render_protocol_screen(Bot(), 123, 10, "vless") is True


def test_handle_create_client_callback_unknown_returns_false(monkeypatch):
    from handlers.admin import clients

    bot = type("Bot", (), {})()

    assert (
        clients.handle_create_client_callback(
            bot, 123, None, "definitely_unknown_callback"
        )
        is False
    )


def test_handle_create_client_callback_unknown_hits_final_return_false():
    from handlers.admin import clients

    bot = type("Bot", (), {})()

    assert clients.handle_create_client_callback(bot, 123, None, "unknown") is False


def test_handle_qr_config_callback_unknown_hits_final_return_false():
    from handlers.admin import clients

    bot = type("Bot", (), {})()

    assert clients.handle_qr_config_callback(bot, 123, None, "unknown") is False


def test_handle_create_client_callback_final_false_when_not_admin(monkeypatch):
    from handlers.admin import clients

    monkeypatch.setattr(clients, "is_admin", lambda cid: False)

    bot = type("Bot", (), {})()

    assert clients.handle_create_client_callback(bot, 123, None, "unknown") is False


def test_handle_lists_delete_callback_unknown_returns_false():
    from handlers.admin import clients

    bot = type("Bot", (), {})()

    assert clients.handle_lists_delete_callback(bot, 123, None, "unknown") is False
