from services import client_service as cs


class FakeBot:
    def __init__(self):
        self.photos = []
        self.documents = []
        self.messages = []

    def send_photo(self, chat_id, photo, **kwargs):
        self.photos.append({"chat_id": chat_id, "caption": kwargs.get("caption")})

    def send_document(self, chat_id, f, **kwargs):
        self.documents.append({"chat_id": chat_id, "caption": kwargs.get("caption")})

    def send_message(self, chat_id, text, **kwargs):
        self.messages.append(text)


def test_send_awg_qr_success(monkeypatch, tmp_path):
    bot = FakeBot()

    monkeypatch.setattr(cs, "awg_get_config", lambda username: "AWG TEST CONFIG")

    monkeypatch.setattr(cs, "load_awg_registry", lambda: {"test": {"ip": "10.66.66.8"}})

    # подменяем qrencode
    def fake_run(*args, **kwargs):
        qr_path = args[0][args[0].index("-o") + 1]
        with open(qr_path, "wb") as qr_file:
            qr_file.write(b"fake qr")

    monkeypatch.setattr(cs.subprocess, "run", fake_run)

    monkeypatch.setattr(cs.os.path, "exists", lambda p: False)

    cs.send_qr_or_conf(bot, 123, "test", "awg")

    assert len(bot.photos) == 1
    assert "AWG QR + Конфиг" in bot.photos[0]["caption"]


def test_send_awg_qrencode_uses_size_option(monkeypatch):
    bot = FakeBot()
    calls = []

    monkeypatch.setattr(
        cs,
        "awg_get_config",
        lambda username: "AWG TEST CONFIG",
    )

    monkeypatch.setattr(
        cs,
        "load_awg_registry",
        lambda: {
            "test": {
                "ip": "10.66.66.8",
            }
        },
    )

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        command = args[0]
        qr_path = command[command.index("-o") + 1]
        with open(qr_path, "wb") as qr_file:
            qr_file.write(b"fake qr")

    monkeypatch.setattr(
        cs.subprocess,
        "run",
        fake_run,
    )

    monkeypatch.setattr(
        cs.os.path,
        "exists",
        lambda p: False,
    )

    cs.send_qr_or_conf(
        bot,
        123,
        "test",
        "awg",
    )

    assert len(calls) == 1

    command = calls[0][0][0]

    assert command[command.index("-s") + 1] == "3"
    assert "-r" not in command
    assert "AWG TEST CONFIG" in command


def test_send_awg_config_not_found(monkeypatch):
    bot = FakeBot()

    monkeypatch.setattr(cs, "awg_get_config", lambda username: None)

    import pytest

    with pytest.raises(ValueError, match="Config not found"):
        cs.send_qr_or_conf(bot, 123, "unknown", "awg")
