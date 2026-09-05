from unittest.mock import MagicMock

from handlers.features.ssh_keys import handle_ssh_callback


def make_call(data):
    call = MagicMock()
    call.id = "1"
    call.data = data
    call.message.message_id = 100
    return call


def test_delete_menu_when_no_keys(monkeypatch):
    import handlers.features.ssh_keys as h

    monkeypatch.setattr(
        h,
        "get_ssh_keys_list",
        lambda: "🔐 *SSH-ключи доступа*\n\n🔑 SSH-ключи не найдены.",
    )

    monkeypatch.setattr(
        h.subprocess,
        "run",
        lambda *a, **k: type(
            "R",
            (),
            {
                "stdout": "",
                "returncode": 0,
            },
        )(),
    )

    bot = MagicMock()

    ok = handle_ssh_callback(
        bot,
        123,
        make_call("ssh_delete"),
        "ssh_delete",
    )

    assert ok.show_alert is False

    args = bot.edit_message_text.call_args.args

    assert "не найдены" in args[0]
