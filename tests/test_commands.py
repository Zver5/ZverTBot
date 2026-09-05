from unittest.mock import MagicMock, patch

from handlers import commands


class DummyMessage:
    def __init__(self, chat_id):
        self.chat = MagicMock()
        self.chat.id = chat_id

        self.from_user = MagicMock()
        self.from_user.username = "tester"
        self.from_user.first_name = "Tester"

        self.text = "/start"


@patch("handlers.commands.bot")
def test_start_admin(mock_bot):
    msg = DummyMessage(111)

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.is_client", return_value=False),
        patch("handlers.commands.main_menu_kb", return_value="KB"),
        patch("handlers.commands.get_help_text", return_value="HELP"),
        patch("handlers.commands.navigation.start"),
    ):
        mock_bot.send_message.return_value = MagicMock(message_id=1)

        commands.cmd_start(msg)

        assert mock_bot.send_message.call_count == 1


@patch("handlers.commands.bot")
def test_start_client(mock_bot):
    msg = DummyMessage(222)

    with (
        patch("handlers.commands.is_admin", return_value=False),
        patch("handlers.commands.is_client", return_value=True),
        patch("handlers.commands.get_client_menu") as menu,
    ):
        menu.return_value = ("KB", "CLIENT MENU", False)

        commands.cmd_start(msg)

        assert mock_bot.send_message.call_count == 1


@patch("handlers.commands.bot")
def test_start_guest(mock_bot):
    msg = DummyMessage(333)

    with (
        patch("handlers.commands.is_admin", return_value=False),
        patch("handlers.commands.is_client", return_value=False),
    ):
        commands.cmd_start(msg)

        assert mock_bot.send_message.call_count == 1


def test_get_client_accounts_empty():

    with patch("handlers.commands.get_client_bindings", return_value=[]):
        result = commands.get_client_accounts_by_chat(1)

        assert result == {"xray": [], "awg": []}


def test_get_client_accounts():

    bindings = {"1": ["user1", "user2"]}

    with (
        patch("handlers.commands.get_client_bindings", return_value=bindings["1"]),
        patch(
            "handlers.commands.get_client_protocol",
            side_effect=lambda username: "vless" if username == "user1" else "awg",
        ),
    ):
        result = commands.get_client_accounts_by_chat(1)

        assert result["xray"] == ["user1"]
        assert result["awg"] == ["user2"]


@patch("handlers.commands.bot")
def test_status_admin(mock_bot):

    msg = DummyMessage(1)

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.get_status_text", return_value="STATUS"),
    ):
        commands.cmd_status(msg)

        assert mock_bot.send_message.call_count == 1


@patch("handlers.commands.bot")
def test_status_non_admin(mock_bot):

    msg = DummyMessage(1)

    with patch("handlers.commands.is_admin", return_value=False):
        commands.cmd_status(msg)

        mock_bot.send_message.assert_not_called()


# ==========================================================
# /my_id
# ==========================================================


@patch("handlers.commands.bot")
def test_my_id_client(mock_bot):

    msg = DummyMessage(100)

    with (
        patch("handlers.commands.is_client", return_value=True),
        patch("handlers.commands.get_client_accounts_by_chat") as accounts,
    ):
        accounts.return_value = {"xray": ["User1"], "awg": ["User2"]}

        commands.cmd_my_id(msg)

        assert mock_bot.send_message.call_count == 1


@patch("handlers.commands.bot")
def test_my_id_guest(mock_bot):

    msg = DummyMessage(101)

    with (
        patch("handlers.commands.is_client", return_value=False),
        patch(
            "handlers.commands.get_pending_bindings",
            return_value={
                "101": {
                    "name": "Test",
                    "time": "today",
                }
            },
        ),
        patch("handlers.commands.add_pending_binding"),
    ):
        commands.cmd_my_id(msg)

        assert mock_bot.send_message.call_count == 2


# ==========================================================
# /pending
# ==========================================================


@patch("handlers.commands.bot")
def test_pending_empty(mock_bot):

    msg = DummyMessage(1)

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.get_pending_bindings", return_value={}),
    ):
        commands.cmd_pending(msg)

        mock_bot.reply_to.assert_called_once()


@patch("handlers.commands.bot")
def test_pending_has_requests(mock_bot):

    msg = DummyMessage(1)

    pending = {"123": {"name": "User", "time": "today"}}

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.get_pending_bindings", return_value=pending),
    ):
        commands.cmd_pending(msg)

        mock_bot.reply_to.assert_called_once()


@patch("handlers.commands.bot")
def test_pending_escapes_name_and_time(mock_bot):

    msg = DummyMessage(1)

    pending = {
        "123": {
            "name": "User_name",
            "time": "12_34",
        }
    }

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.get_pending_bindings", return_value=pending),
    ):
        commands.cmd_pending(msg)

    text = mock_bot.reply_to.call_args[0][1]

    assert "User\\_name" in text
    assert "12\\_34" in text
    assert "User_name" not in text
    assert "12_34" not in text


# ==========================================================
# /history
# ==========================================================


@patch("handlers.commands.bot")
def test_history(mock_bot):

    msg = DummyMessage(1)

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.show_history_action") as history,
    ):
        commands.cmd_history(msg)

        history.assert_called_once()


# ==========================================================
# /rename
# ==========================================================


@patch("handlers.commands.bot")
def test_rename_not_admin(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/rename old new"

    with patch("handlers.commands.is_admin", return_value=False):
        commands.cmd_rename(msg)
        mock_bot.reply_to.assert_not_called()


@patch("handlers.commands.bot")
def test_rename_wrong_args(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/rename only_one_arg"

    with patch("handlers.commands.is_admin", return_value=True):
        commands.cmd_rename(msg)
        mock_bot.reply_to.assert_called_once()
        assert "Использование:" in mock_bot.reply_to.call_args[0][1]


@patch("handlers.commands.bot")
def test_rename_invalid_username(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/rename old new@invalid"

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.validate_username", return_value=False),
    ):
        commands.cmd_rename(msg)
        mock_bot.reply_to.assert_called_once()
        assert "только латиницу" in mock_bot.reply_to.call_args[0][1]


@patch("handlers.commands.bot")
def test_rename_old_not_found(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/rename old new"

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.validate_username", return_value=True),
        patch("handlers.commands.get_users_list") as mock_users,
    ):
        mock_users.return_value = []
        commands.cmd_rename(msg)
        mock_bot.reply_to.assert_called_once()
        assert "не найден" in mock_bot.reply_to.call_args[0][1]


@patch("handlers.commands.bot")
def test_rename_new_already_exists(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/rename old new"

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.validate_username", return_value=True),
        patch("handlers.commands.get_users_list") as mock_users,
    ):
        mock_users.side_effect = lambda proto: (
            ["old", "new"] if proto == "vless" else []
        )
        commands.cmd_rename(msg)
        mock_bot.reply_to.assert_called_once()
        assert "уже занято" in mock_bot.reply_to.call_args[0][1]


@patch("handlers.commands.bot")
def test_rename_success(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/rename old new"

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.validate_username", return_value=True),
        patch("handlers.commands.get_users_list") as mock_users,
        patch("handlers.commands.rename_client", return_value=None),
        patch("handlers.commands.log_action") as mock_log,
    ):
        mock_users.side_effect = lambda proto: ["old"] if proto == "vless" else []
        commands.cmd_rename(msg)
        assert mock_bot.reply_to.call_count == 1
        mock_bot.send_message.assert_called_once()
        mock_log.assert_called_once()


@patch("handlers.commands.bot")
def test_rename_with_errors(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/rename old new"

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.validate_username", return_value=True),
        patch("handlers.commands.get_users_list") as mock_users,
        patch("handlers.commands.rename_client", return_value=["Ошибка 1", "Ошибка 2"]),
    ):
        mock_users.side_effect = lambda proto: ["old"] if proto == "vless" else []
        commands.cmd_rename(msg)
        assert mock_bot.reply_to.call_count == 1
        mock_bot.send_message.assert_called_once()
        assert "Ошибки" in mock_bot.send_message.call_args[0][1]


# ==========================================================
# /bind
# ==========================================================


@patch("handlers.commands.bot")
def test_bind_not_admin(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/bind user 123"

    with patch("handlers.commands.is_admin", return_value=False):
        commands.cmd_bind(msg)
        mock_bot.reply_to.assert_not_called()


@patch("handlers.commands.bot")
def test_bind_wrong_args(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/bind only_one"

    with patch("handlers.commands.is_admin", return_value=True):
        commands.cmd_bind(msg)
        mock_bot.reply_to.assert_called_once()
        assert "Использование:" in mock_bot.reply_to.call_args[0][1]


@patch("handlers.commands.bot")
def test_bind_invalid_username(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/bind user@invalid 123"

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.validate_username", return_value=False),
    ):
        commands.cmd_bind(msg)
        mock_bot.reply_to.assert_called_once()
        assert "Некорректное имя" in mock_bot.reply_to.call_args[0][1]


@patch("handlers.commands.bot")
def test_bind_invalid_chat_id(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/bind user abc"

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.validate_username", return_value=True),
        patch("handlers.commands.validate_chat_id", return_value=False),
    ):
        commands.cmd_bind(msg)
        mock_bot.reply_to.assert_called_once()
        assert "только из цифр" in mock_bot.reply_to.call_args[0][1]


@patch("handlers.commands.bot")
def test_bind_user_not_found(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/bind user 123"

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.validate_username", return_value=True),
        patch("handlers.commands.validate_chat_id", return_value=True),
        patch("handlers.commands.get_users_list") as mock_users,
    ):
        mock_users.return_value = []
        commands.cmd_bind(msg)
        mock_bot.reply_to.assert_called_once()
        assert "не найден" in mock_bot.reply_to.call_args[0][1]


@patch("handlers.commands.bot")
def test_bind_limit_exceeded(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/bind user 123"

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.validate_username", return_value=True),
        patch("handlers.commands.validate_chat_id", return_value=True),
        patch("handlers.commands.get_users_list") as mock_users,
        patch(
            "services.bindings.load_client_bindings",
            return_value={"123": ["u1", "u2", "u3", "u4"]},
        ),
    ):
        mock_users.side_effect = lambda proto: ["user"] if proto == "vless" else []
        commands.cmd_bind(msg)
        mock_bot.reply_to.assert_called_once()
        assert "лимит" in mock_bot.reply_to.call_args[0][1].lower()


@patch("handlers.commands.bot")
def test_bind_duplicate(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/bind user 123"

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.validate_username", return_value=True),
        patch("handlers.commands.validate_chat_id", return_value=True),
        patch("handlers.commands.get_users_list") as mock_users,
        patch("services.bindings.load_client_bindings", return_value={"123": ["user"]}),
    ):
        mock_users.side_effect = lambda proto: ["user"] if proto == "vless" else []
        commands.cmd_bind(msg)
        mock_bot.reply_to.assert_called_once()
        assert "уже привязан" in mock_bot.reply_to.call_args[0][1]


@patch("handlers.commands.bot")
def test_bind_success_new_chat(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/bind user 123"

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.validate_username", return_value=True),
        patch("handlers.commands.validate_chat_id", return_value=True),
        patch("handlers.commands.get_users_list") as mock_users,
        patch("services.bindings.load_client_bindings", return_value={}),
        patch("services.bindings.save_client_bindings") as mock_save,
        patch("handlers.commands.log_action") as mock_log,
    ):
        mock_users.side_effect = lambda proto: ["user"] if proto == "vless" else []
        commands.cmd_bind(msg)
        mock_save.assert_called_once()
        mock_log.assert_called_once()
        assert mock_bot.reply_to.call_count == 1
        assert "успешно привязан" in mock_bot.reply_to.call_args[0][1]


@patch("handlers.commands.bot")
def test_bind_success_existing_chat(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/bind user2 123"

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.validate_username", return_value=True),
        patch("handlers.commands.validate_chat_id", return_value=True),
        patch("handlers.commands.get_users_list") as mock_users,
        patch(
            "services.bindings.load_client_bindings", return_value={"123": ["user1"]}
        ),
        patch("services.bindings.save_client_bindings") as mock_save,
    ):
        mock_users.side_effect = lambda proto: (
            ["user1", "user2"] if proto == "vless" else []
        )
        commands.cmd_bind(msg)
        mock_save.assert_called_once()
        saved_bindings = mock_save.call_args[0][0]
        assert len(saved_bindings["123"]) == 2


# ==========================================================
# /start — exception/cleanup branches
# ==========================================================


@patch("handlers.commands.bot")
def test_start_clear_step_handler_exception(mock_bot):
    msg = DummyMessage(111)

    with (
        patch(
            "handlers.commands.bot.clear_step_handler_by_chat_id",
            side_effect=RuntimeError("clear failed"),
        ),
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.is_client", return_value=False),
        patch("handlers.commands.main_menu_kb", return_value="KB"),
        patch("handlers.commands.get_help_text", return_value="HELP"),
        patch("handlers.commands.navigation.start"),
    ):
        mock_bot.send_message.return_value = MagicMock(message_id=1)
        commands.cmd_start(msg)

    mock_bot.send_message.assert_called_once()


@patch("handlers.commands.bot")
def test_start_admin_deletes_previous_menu(mock_bot):
    msg = DummyMessage(111)
    commands.LAST_MAIN_MENU_MSGS[111] = 99

    try:
        with (
            patch("handlers.commands.is_admin", return_value=True),
            patch("handlers.commands.is_client", return_value=False),
            patch("handlers.commands.main_menu_kb", return_value="KB"),
            patch("handlers.commands.get_help_text", return_value="HELP"),
            patch("handlers.commands.navigation.start"),
            patch("handlers.commands.safe_delete") as mock_delete,
        ):
            mock_bot.send_message.return_value = MagicMock(message_id=1)
            commands.cmd_start(msg)

        mock_delete.assert_called_once_with(mock_bot, 111, 99)
    finally:
        commands.LAST_MAIN_MENU_MSGS.pop(111, None)


@patch("handlers.commands.bot")
def test_start_client_deletes_previous_menu(mock_bot):
    msg = DummyMessage(222)
    commands.LAST_CLIENT_MENU_MSGS[222] = 88

    try:
        with (
            patch("handlers.commands.is_admin", return_value=False),
            patch("handlers.commands.is_client", return_value=True),
            patch(
                "handlers.commands.get_client_menu",
                return_value=("KB", "MENU", False),
            ),
            patch("handlers.commands.navigation.start"),
            patch("handlers.commands.safe_delete") as mock_delete,
        ):
            mock_bot.send_message.return_value = MagicMock(message_id=1)
            commands.cmd_start(msg)

        mock_delete.assert_called_once_with(mock_bot, 222, 88)
    finally:
        commands.LAST_CLIENT_MENU_MSGS.pop(222, None)


# ==========================================================
# /pending / /history — non-admin branches
# ==========================================================


@patch("handlers.commands.bot")
def test_pending_non_admin(mock_bot):
    msg = DummyMessage(1)

    with patch("handlers.commands.is_admin", return_value=False):
        commands.cmd_pending(msg)

    mock_bot.reply_to.assert_not_called()


@patch("handlers.commands.bot")
def test_history_non_admin(mock_bot):
    msg = DummyMessage(1)

    with patch("handlers.commands.is_admin", return_value=False):
        commands.cmd_history(msg)

    mock_bot.send_message.assert_not_called()


# ==========================================================
# /my_id — cleanup admin notification
# ==========================================================


@patch("handlers.commands.bot")
def test_my_id_replaces_old_admin_notification(mock_bot):
    msg = DummyMessage(101)

    new_user_message = MagicMock(message_id=88)
    new_admin_message = MagicMock(message_id=99)

    commands.LAST_MY_ID_ADMIN_MSGS[101] = {999: 77}

    try:
        with (
            patch("handlers.commands.is_client", return_value=False),
            patch(
                "handlers.commands.get_pending_bindings",
                return_value={
                    "101": {
                        "name": "Test",
                        "time": "today",
                    }
                },
            ),
            patch("handlers.commands.add_pending_binding"),
            patch("handlers.commands.ADMIN_CHATS", [999]),
            patch("handlers.commands.safe_delete") as safe_delete,
        ):
            mock_bot.send_message.side_effect = [
                new_user_message,
                new_admin_message,
            ]

            commands.cmd_my_id(msg)

        safe_delete.assert_any_call(mock_bot, 999, 77)
        assert commands.LAST_MY_ID_ADMIN_MSGS[101] == {999: 99}
    finally:
        commands.LAST_MY_ID_ADMIN_MSGS.pop(101, None)


# ==========================================================
# /my_id — cleanup exception
# ==========================================================


@patch("handlers.commands.bot")
def test_my_id_existing_message_delete_exception(mock_bot):
    msg = DummyMessage(100)
    commands.LAST_MY_ID_MSGS[100] = 77

    try:
        with (
            patch(
                "handlers.commands.safe_delete",
                side_effect=RuntimeError("delete failed"),
            ),
            patch("handlers.commands.is_client", return_value=True),
            patch(
                "handlers.commands.get_client_accounts_by_chat",
                return_value={"xray": [], "awg": []},
            ),
        ):
            mock_bot.send_message.return_value = MagicMock(message_id=1)
            commands.cmd_my_id(msg)

        mock_bot.send_message.assert_called_once()
    finally:
        commands.LAST_MY_ID_MSGS.pop(100, None)


# ==========================================================
# /my_id — admin notification exception
# ==========================================================


@patch("handlers.commands.bot")
def test_my_id_admin_notification_exception(mock_bot):
    msg = DummyMessage(101)

    with (
        patch("handlers.commands.is_client", return_value=False),
        patch(
            "handlers.commands.get_pending_bindings",
            return_value={
                "101": {
                    "name": "Test",
                    "time": "today",
                }
            },
        ),
        patch("handlers.commands.add_pending_binding"),
        patch("handlers.commands.ADMIN_CHATS", [999]),
        patch(
            "handlers.commands.bot.send_message",
            side_effect=[MagicMock(message_id=1), RuntimeError("admin failed")],
        ),
    ):
        commands.cmd_my_id(msg)

    assert commands.LAST_MY_ID_MSGS[101] == 1
    commands.LAST_MY_ID_MSGS.pop(101, None)


# ==========================================================
# /bind — notification exception
# ==========================================================


@patch("handlers.commands.bot")
def test_bind_success_notification_exception(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/bind user 123"

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch("handlers.commands.validate_username", return_value=True),
        patch("handlers.commands.validate_chat_id", return_value=True),
        patch(
            "handlers.commands.get_users_list",
            side_effect=lambda proto: ["user"] if proto == "vless" else [],
        ),
        patch("handlers.commands.add_client_binding", return_value="success"),
        patch("handlers.commands.log_action"),
        patch(
            "handlers.commands.bot.send_message",
            side_effect=RuntimeError("client notification failed"),
        ),
    ):
        commands.cmd_bind(msg)

    mock_bot.reply_to.assert_called_once()


# ==========================================================
# /unbind
# ==========================================================


@patch("handlers.commands.bot")
def test_unbind_not_admin(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/unbind 123"

    with patch("handlers.commands.is_admin", return_value=False):
        commands.cmd_unbind(msg)
        mock_bot.reply_to.assert_not_called()


@patch("handlers.commands.bot")
def test_unbind_wrong_args(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/unbind"

    with patch("handlers.commands.is_admin", return_value=True):
        commands.cmd_unbind(msg)
        mock_bot.reply_to.assert_called_once()
        assert (
            mock_bot.reply_to.call_args[0][1]
            == "Использование: /unbind <chat_id> <username>"
        )


@patch("handlers.commands.bot")
def test_unbind_success(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/unbind 123 user"

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch(
            "handlers.commands.remove_client_binding", return_value=True
        ) as mock_remove,
        patch("handlers.commands.log_action") as mock_log,
    ):
        commands.cmd_unbind(msg)
        mock_remove.assert_called_once_with("123", "user")
        mock_log.assert_called_once()
        mock_bot.reply_to.assert_called_once()
        assert "удалена" in mock_bot.reply_to.call_args[0][1]


@patch("handlers.commands.bot")
def test_unbind_not_found(mock_bot):
    msg = DummyMessage(1)
    msg.text = "/unbind 999 user"

    with (
        patch("handlers.commands.is_admin", return_value=True),
        patch(
            "handlers.commands.remove_client_binding", return_value=False
        ) as mock_remove,
    ):
        commands.cmd_unbind(msg)
        mock_remove.assert_called_once_with("999", "user")
        mock_bot.reply_to.assert_called_once()
        assert "не найдена" in mock_bot.reply_to.call_args[0][1]


@patch("handlers.commands.bot")
def test_my_id_admin_old_notification_delete_exception_is_logged(mock_bot):
    msg = DummyMessage(101)

    commands.LAST_MY_ID_ADMIN_MSGS[101] = {999: 77}

    try:
        with (
            patch("handlers.commands.is_client", return_value=False),
            patch(
                "handlers.commands.get_pending_bindings",
                return_value={
                    "101": {
                        "name": "Test",
                        "time": "today",
                    }
                },
            ),
            patch("handlers.commands.add_pending_binding"),
            patch("handlers.commands.ADMIN_CHATS", [999]),
            patch(
                "handlers.commands.safe_delete",
                side_effect=RuntimeError("delete failed"),
            ),
            patch("handlers.commands.logger.exception") as mock_exception,
        ):
            mock_bot.send_message.side_effect = [
                MagicMock(message_id=88),
                MagicMock(message_id=99),
            ]

            commands.cmd_my_id(msg)

        mock_exception.assert_called_once()
        assert commands.LAST_MY_ID_ADMIN_MSGS[101] == {999: 99}
    finally:
        commands.LAST_MY_ID_ADMIN_MSGS.pop(101, None)
