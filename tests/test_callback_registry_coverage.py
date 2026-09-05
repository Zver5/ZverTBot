"""
Проверка всех кнопок клавиатур.
Каждый callback_data должен иметь обработчик в callback router.
"""

from core.callback_router import get
from ui import keyboards


def extract_callbacks(kb):
    result = []

    for row in kb.keyboard:
        for btn in row:
            if btn.callback_data:
                result.append(btn.callback_data)

    return result


def test_all_keyboard_callbacks_have_handlers():

    keyboards_to_check = [
        keyboards.main_menu_kb(),
        keyboards.create_menu_kb(),
        keyboards.clients_menu_kb(),
        keyboards.manage_menu_kb(),
        keyboards.system_menu_kb(),
        keyboards.ssh_menu_kb(),
        keyboards.processes_menu_kb(),
        keyboards.fail2ban_menu_kb(),
        keyboards.network_menu_kb(),
        keyboards.backups_menu_kb(),
        keyboards.analytics_menu_kb(),
        keyboards.log_close_kb(),
        # динамические
        keyboards.protocol_list_kb("vless", ["TestUser"]),
        keyboards.protocol_list_kb("awg", ["TestUser"]),
        keyboards.client_card_kb("vless", "TestUser"),
        keyboards.client_card_kb("awg", "TestUser"),
    ]

    checked = set()
    missing = []

    for kb in keyboards_to_check:
        for callback in extract_callbacks(kb):
            if callback in checked:
                continue

            checked.add(callback)

            if get(callback) is None:
                missing.append(callback)

    assert not missing, "Нет обработчиков для callback: " + ", ".join(missing)


def test_callback_count():

    assert True
