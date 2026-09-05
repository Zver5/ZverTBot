"""Модуль глобального состояния Telegram-бота.
Содержит словари для отслеживания ID сообщений (удаление дублей, автоочистка).
"""

# Словарь для отслеживания сообщений с запросами ввода имени/данных
# Используется для автоудаления сообщений после успешного ввода
INPUT_REQUEST_MSGS = {}

# Словарь для отслеживания ID последнего главного меню
# Используется для удаления предыдущего меню при повторном /start или "Назад"
LAST_MAIN_MENU_MSGS = {}
LAST_CLIENT_MENU_MSGS = {}

# Словарь для отслеживания ID последнего сообщения "Статус"
# Используется для удаления предыдущего статуса при повторном нажатии кнопки
LAST_STATUS_MSGS = {}

# Словарь для отслеживания последнего сообщения /my_id
# Не создаёт дубли при повторном вызове команды
LAST_MY_ID_MSGS = {}
# admin_chat_id -> message_id для уведомлений /my_id
LAST_MY_ID_ADMIN_MSGS = {}


def replace_message_id(old_message_id, new_message_id):
    """Заменяет устаревший message_id во всех словарях состояния."""
    for state in (
        LAST_MAIN_MENU_MSGS,
        LAST_CLIENT_MENU_MSGS,
        LAST_STATUS_MSGS,
        LAST_MY_ID_MSGS,
    ):
        for chat_id, message_id in state.items():
            if message_id == old_message_id:
                state[chat_id] = new_message_id

    for admin_messages in LAST_MY_ID_ADMIN_MSGS.values():
        if isinstance(admin_messages, dict):
            for admin_chat_id, message_id in admin_messages.items():
                if message_id == old_message_id:
                    admin_messages[admin_chat_id] = new_message_id
