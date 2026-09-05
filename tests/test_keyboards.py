from ui import keyboards


def get_buttons(kb):
    """
    Возвращает список кнопок из InlineKeyboardMarkup
    """
    result = []

    for row in kb.keyboard:
        for button in row:
            result.append(button)

    return result


def test_manage_menu_has_no_duplicates():
    kb = keyboards.manage_menu_kb()

    buttons = get_buttons(kb)

    texts = [b.text for b in buttons]
    callbacks = [getattr(b, "callback_data", None) for b in buttons]

    assert len(texts) == len(set(texts)), f"Duplicate button text found: {texts}"

    assert len(callbacks) == len(set(callbacks)), (
        f"Duplicate callback_data found: {callbacks}"
    )


def test_system_menu_has_no_duplicates():
    kb = keyboards.system_menu_kb()

    buttons = get_buttons(kb)

    texts = [b.text for b in buttons]
    callbacks = [getattr(b, "callback_data", None) for b in buttons]

    assert len(texts) == len(set(texts)), f"Duplicate button text found: {texts}"

    assert len(callbacks) == len(set(callbacks)), (
        f"Duplicate callback_data found: {callbacks}"
    )


def test_manage_menu_required_buttons():
    kb = keyboards.manage_menu_kb()

    buttons = get_buttons(kb)

    callbacks = {b.callback_data for b in buttons}

    required = {
        "ssh_menu",
        "fail2ban_menu",
        "nav:network",
        "nav:home",
    }

    missing = required - callbacks

    assert not missing, f"Missing manage menu callbacks: {missing}"


def test_system_menu_required_buttons():
    kb = keyboards.system_menu_kb()

    buttons = get_buttons(kb)

    callbacks = {b.callback_data for b in buttons}

    required = {
        "restart_bot",
        "restart_awg",
        "restart_xray",
        "log_bot",
        "log_awg",
        "log_xray",
        "processes_menu",
        "confirm_cleanup",
        "nav:home",
    }

    missing = required - callbacks

    assert not missing, f"Missing system menu callbacks: {missing}"


def test_clients_manage_menu_kb():
    from core.navigation import NAV_BACK_CALLBACK
    from ui.keyboards import clients_manage_menu_kb

    kb = clients_manage_menu_kb()

    buttons = [button for row in kb.keyboard for button in row]

    assert [(b.text, b.callback_data) for b in buttons] == [
        ("⚡ VLESS", "nav:clients_vless"),
        ("🛡 AWG", "nav:clients_awg"),
        ("↩️ Назад", NAV_BACK_CALLBACK),
    ]


def test_client_accounts_kb_with_accounts():
    from ui.keyboards import client_accounts_kb

    kb = client_accounts_kb(
        ["alice", "bob", "carol"],
        users_vless=["alice"],
        users_awg=["bob"],
    )

    buttons = [button for row in kb.keyboard for button in row]

    assert [(b.text, b.callback_data) for b in buttons] == [
        ("🚀 alice", "client:account:alice"),
        ("🛡️ bob", "client:account:bob"),
        ("🛡️ carol", "client:account:carol"),
        ("🆘 Создать тикет", "create_ticket"),
        ("📖 Инструкция", "nav:client_help"),
    ]


def test_client_accounts_kb_empty():
    from ui.keyboards import client_accounts_kb

    kb = client_accounts_kb([])

    buttons = [button for row in kb.keyboard for button in row]

    assert [(b.text, b.callback_data) for b in buttons] == [
        ("🆘 Создать тикет", "create_ticket"),
        ("📖 Инструкция", "nav:client_help"),
    ]


def test_client_account_kb_vless():
    from ui.keyboards import client_account_kb

    kb = client_account_kb("alice", "vless")

    buttons = [button for row in kb.keyboard for button in row]

    assert [(b.text, b.callback_data) for b in buttons] == [
        ("📊 Статистика", "client:stats:alice"),
        ("📱 QR-код", "client:conf:alice"),
        ("🆘 Создать тикет", "create_ticket"),
        ("📦 Конфигурация + RU", "client:conf_ru:alice"),
        ("📖 Инструкция", "nav:client_help"),
    ]


def test_client_account_kb_awg():
    from ui.keyboards import client_account_kb

    kb = client_account_kb("bob", "awg")

    buttons = [button for row in kb.keyboard for button in row]

    assert [(b.text, b.callback_data) for b in buttons] == [
        ("📊 Статистика", "client:stats:bob"),
        ("📱 QR-код", "client:conf:bob"),
        ("🆘 Создать тикет", "create_ticket"),
        ("📖 Инструкция", "nav:client_help"),
    ]
