"""
Тесты для services/client_service.py — работа с VPN-клиентами.
"""

from unittest.mock import Mock, mock_open, patch

import pytest

import services.client_service as cs

# ==========================================================
# get_users_list
# ==========================================================


def test_get_users_list_vless(monkeypatch, tmp_path):
    """Список VLESS клиентов из конфига"""
    monkeypatch.setattr(cs, "load_xray_config", lambda: {"inbounds": []})
    monkeypatch.setattr(cs, "get_all_vless_clients", lambda cfg: ["user1", "user2"])

    result = cs.get_users_list("vless")

    # Порядок не гарантирован из-за set(), сравниваем как множества
    assert sorted(result) == ["user1", "user2"]


def test_get_users_list_awg(monkeypatch):
    """Список AWG клиентов из реестра"""
    monkeypatch.setattr(
        cs,
        "load_awg_registry",
        lambda: {"awg_user1": {}, "awg_user2": {}},
    )

    result = cs.get_users_list("awg")

    assert sorted(result) == ["awg_user1", "awg_user2"]


def test_get_users_list_awg_uses_storage_loader(monkeypatch):
    monkeypatch.setattr(
        cs,
        "load_awg_registry",
        lambda: {"awg_user1": {}, "awg_user2": {}},
    )

    result = cs.get_users_list("awg")

    assert sorted(result) == ["awg_user1", "awg_user2"]


def test_get_users_list_unknown_proto(monkeypatch):
    """Неизвестный протокол — пустой список"""
    result = cs.get_users_list("unknown")

    assert result == []


# ==========================================================
# rename_client
# ==========================================================


def test_rename_client_success(monkeypatch, tmp_path):
    """Успешное переименование — все шаги пройдены"""
    # Мокаем все зависимости
    monkeypatch.setattr(cs, "rename_client_in_usage", lambda old, new: True)
    monkeypatch.setattr(cs, "load_xray_config", lambda: {"inbounds": []})
    monkeypatch.setattr(cs, "rename_client_in_config", lambda cfg, old, new: False)
    monkeypatch.setattr(cs, "save_xray_config", lambda cfg: None)
    monkeypatch.setattr(cs, "reload_xray", lambda: None)
    monkeypatch.setattr(
        cs, "load_awg_registry", lambda: {"old_name": {"ip": "10.0.0.1"}}
    )
    monkeypatch.setattr(cs, "save_awg_registry", lambda reg: None)
    monkeypatch.setattr(cs, "rename_peer_in_config", lambda old, new: True)
    monkeypatch.setattr(cs, "load_client_bindings", dict)
    monkeypatch.setattr(cs, "save_client_bindings", lambda bindings: None)

    # Мокаем subprocess.run чтобы не вызывать реальный systemctl
    monkeypatch.setattr(
        cs.subprocess, "run", lambda *args, **kwargs: Mock(returncode=0)
    )

    # Пользовательские AWG-конфиги физически на сервере не хранятся.
    errors = cs.rename_client("old_name", "new_name")

    assert errors == []


def test_rename_client_not_in_usage(monkeypatch, tmp_path):
    """Клиент не найден в usage.json — предупреждение"""
    monkeypatch.setattr(cs, "rename_client_in_usage", lambda old, new: False)
    monkeypatch.setattr(cs, "load_xray_config", lambda: {"inbounds": []})
    monkeypatch.setattr(cs, "rename_client_in_config", lambda cfg, old, new: False)
    monkeypatch.setattr(cs, "save_xray_config", lambda cfg: None)
    monkeypatch.setattr(cs, "reload_xray", lambda: None)
    monkeypatch.setattr(cs, "load_awg_registry", dict)
    monkeypatch.setattr(cs, "save_awg_registry", lambda reg: None)
    monkeypatch.setattr(cs, "load_client_bindings", dict)
    monkeypatch.setattr(cs, "save_client_bindings", lambda bindings: None)
    monkeypatch.setattr(
        cs.subprocess, "run", lambda *args, **kwargs: Mock(returncode=0)
    )

    errors = cs.rename_client("old_name", "new_name")

    assert "Клиент не найден ни в одном хранилище" in errors


def test_rename_client_updates_bindings(monkeypatch, tmp_path):
    """Переименование обновляет привязки клиентов"""
    monkeypatch.setattr(cs, "rename_client_in_usage", lambda old, new: True)
    monkeypatch.setattr(cs, "load_xray_config", lambda: {"inbounds": []})
    monkeypatch.setattr(cs, "rename_client_in_config", lambda cfg, old, new: False)
    monkeypatch.setattr(cs, "save_xray_config", lambda cfg: None)
    monkeypatch.setattr(cs, "reload_xray", lambda: None)
    monkeypatch.setattr(cs, "load_awg_registry", dict)
    monkeypatch.setattr(cs, "save_awg_registry", lambda reg: None)
    monkeypatch.setattr(cs, "rename_peer_in_config", lambda old, new: None)
    monkeypatch.setattr(
        cs.subprocess, "run", lambda *args, **kwargs: Mock(returncode=0)
    )

    test_bindings = {"123456": ["old_name", "other_user"]}
    saved_bindings = {}
    monkeypatch.setattr(cs, "load_client_bindings", lambda: test_bindings)
    monkeypatch.setattr(
        cs,
        "save_client_bindings",
        lambda bindings: saved_bindings.update({"data": bindings}),
    )

    cs.rename_client("old_name", "new_name")

    assert "new_name" in saved_bindings["data"]["123456"]
    assert "old_name" not in saved_bindings["data"]["123456"]


@pytest.mark.parametrize(
    ("loader_name", "error_text"),
    [
        ("load_xray_config", "xray load failed"),
        ("load_awg_registry", "awg load failed"),
        ("load_client_bindings", "bindings load failed"),
    ],
)
def test_rename_client_aborts_when_critical_storage_load_fails(
    monkeypatch,
    loader_name,
    error_text,
):
    def broken_loader():
        raise RuntimeError(error_text)

    monkeypatch.setattr(cs, "load_xray_config", lambda: {"inbounds": []})
    monkeypatch.setattr(cs, "load_awg_registry", lambda: {})
    monkeypatch.setattr(cs, "load_client_bindings", lambda: {})
    monkeypatch.setattr(cs, loader_name, broken_loader)

    errors = cs.rename_client("old", "new")

    expected_prefix = {
        "load_xray_config": "Xray",
        "load_awg_registry": "AWG",
        "load_client_bindings": "bindings",
    }[loader_name]

    assert errors == [f"{expected_prefix}: {error_text}"]




# ==========================================================
def test_show_history_action_edits_existing_screen(monkeypatch):
    """При mid история редактирует текущий экран, а не создаёт дубликат."""
    from unittest.mock import Mock

    import services.client_service as cs

    monkeypatch.setattr(cs, "load_history", lambda: [])

    mock_bot = Mock()

    cs.show_history_action(mock_bot, 123, mid=456)

    mock_bot.edit_message_text.assert_called_once()
    mock_bot.send_message.assert_not_called()

    call_args = mock_bot.edit_message_text.call_args
    assert call_args.args[0] == "📜 История пуста. Совершите любое действие."
    assert call_args.args[1] == 123
    assert call_args.args[2] == 456


def test_show_history_action_empty(monkeypatch):
    """Пустая история — сообщение 'История пуста'."""
    import services.client_service as cs

    monkeypatch.setattr(cs, "load_history", lambda: [])

    mock_bot = Mock()
    cs.show_history_action(mock_bot, 123)

    mock_bot.send_message.assert_called_once()
    call_args = mock_bot.send_message.call_args
    assert "История пуста" in call_args[0][1]


def test_show_history_action_with_entries(monkeypatch):
    """История с записями — форматированный вывод."""
    import services.client_service as cs

    history = [
        {
            "time": "2026-07-07 10:00",
            "action": "СОЗДАНИЕ",
            "target": "user1",
            "status": "SUCCESS",
            "details": "VLESS",
        },
        {
            "time": "2026-07-07 11:00",
            "action": "УДАЛЕНИЕ",
            "target": "user2",
            "status": "SUCCESS",
            "details": "",
        },
    ]

    monkeypatch.setattr(cs, "load_history", lambda: history)

    mock_bot = Mock()
    cs.show_history_action(mock_bot, 123)

    mock_bot.send_message.assert_called_once()
    call_args = mock_bot.send_message.call_args
    text = call_args[0][1]
    assert "user1" in text
    assert "user2" in text
    assert "СОЗДАН" in text
    assert "УДАЛЁН" in text


def test_rename_client_usage_exception():
    """
    Ошибка usage.json добавляется в errors
    """
    with (
        patch("services.client_service.get_all_vless_clients", return_value=[]),
        patch("services.client_service.load_xray_config", return_value={}),
        patch("services.client_service.load_awg_registry", return_value={}),
        patch(
            "services.client_service.rename_client_in_usage",
            side_effect=Exception("usage fail"),
        ),
    ):
        result = cs.rename_client("old", "new")

        assert any("usage" in x for x in result)


def test_rename_client_updates_binding_string():
    """
    Проверка если binding хранится строкой, а не списком
    """
    with (
        patch("services.client_service.get_all_vless_clients", return_value=[]),
        patch("services.client_service.load_xray_config", return_value={}),
        patch("services.client_service.load_awg_registry", return_value={}),
        patch("services.client_service.rename_client_in_usage", return_value=False),
        patch(
            "services.client_service.load_client_bindings", return_value={"100": "old"}
        ),
        patch("services.client_service.save_client_bindings") as save,
    ):
        cs.rename_client("old", "new")

        save.assert_called_once()

        saved = save.call_args.args[0]

        assert saved["100"] == ["new"]


def test_send_qr_or_conf_vless_success():
    bot = Mock()

    with (
        patch("services.client_service.xray_get_link", return_value="vless://test"),
        patch("services.client_service.subprocess.run"),
        patch("services.client_service.open", mock_open(read_data=b"qr")),
        patch("services.client_service.os.path.exists", return_value=False),
    ):
        cs.send_qr_or_conf(bot, 100, "client1", "vless")

        bot.send_photo.assert_called_once()


def test_send_qr_or_conf_vless_no_link():
    bot = Mock()

    with patch("services.client_service.xray_get_link", return_value=None):
        import pytest

        with pytest.raises(ValueError, match="Link not found"):
            cs.send_qr_or_conf(bot, 100, "client1", "vless")


def test_send_qr_or_conf_awg_no_config():
    bot = Mock()

    with patch("services.client_service.awg_get_config", return_value=None):
        import pytest

        with pytest.raises(ValueError, match="Config not found"):
            cs.send_qr_or_conf(bot, 100, "client1", "awg")


def test_show_history_action_missing_file(monkeypatch):
    """
    История отсутствует -> пустая история.
    Проверяем поведение через публичную зависимость load_history().
    """
    bot = Mock()

    monkeypatch.setattr(cs, "load_history", lambda: [])

    cs.show_history_action(bot, 100)

    bot.send_message.assert_called_once()
    assert "История пуста" in bot.send_message.call_args.args[1]


def test_show_history_action_bad_json():
    """
    Битый JSON истории
    """
    bot = Mock()

    with (
        patch("services.client_service.Path.exists", return_value=True),
        patch("builtins.open", mock_open(read_data="broken json")),
        patch("json.load", side_effect=Exception("json error")),
    ):
        cs.show_history_action(bot, 100)

    bot.send_message.assert_called_once()


def test_show_history_action_send_error():
    """
    Ошибка отправки сообщения
    """
    bot = Mock()

    bot.send_message.side_effect = [Exception("telegram fail"), None]

    with patch("services.client_service.Path.exists", return_value=False):
        cs.show_history_action(bot, 100)

    assert bot.send_message.call_count == 2


def test_send_qr_or_conf_vless_multiple_links():
    bot = Mock()

    with patch("services.client_service.xray_get_link", return_value="link1\nlink2"):
        cs.send_qr_or_conf(bot, 100, "client1", "vless")

    bot.send_message.assert_called_once()


def test_send_qr_or_conf_awg_success():
    bot = Mock()

    def fake_open(path, mode="r", *args, **kwargs):
        if path == cs.AWG_CONF:
            return mock_open(
                read_data="[Interface]\\nListenPort = 58352\\n"
            ).return_value
        return mock_open(read_data=b"qr").return_value

    with (
        patch("services.client_service.awg_get_config", return_value="awg-config"),
        patch(
            "services.client_service.load_awg_registry",
            return_value={"client1": {"ip": "10.66.66.10"}},
        ),
        patch("services.client_service.subprocess.run"),
        patch("services.client_service.open", side_effect=fake_open),
        patch("services.client_service.os.path.exists", return_value=False),
    ):
        cs.send_qr_or_conf(bot, 100, "client1", "awg")

    bot.send_photo.assert_called_once()
    bot.send_document.assert_called_once()


def test_send_qr_or_conf_send_vless_links():
    bot = Mock()

    def fake_qrencode(*args, **kwargs):
        with open("/tmp/qr_client1.png", "wb") as f:
            f.write(b"qr")

    with (
        patch("services.client_service.xray_get_link", return_value="vless://test"),
        patch(
            "services.client_service.subprocess.run",
            side_effect=fake_qrencode,
        ),
    ):
        cs.send_qr_or_conf(bot, 100, "client1", "vless")

    # Отправляется только QR-код.
    bot.send_photo.assert_called_once()
    bot.send_message.assert_not_called()


def test_rename_client_xray_exception():
    """
    Ошибка Xray добавляется в errors
    """
    with (
        patch("services.client_service.get_all_vless_clients", return_value=[]),
        patch("services.client_service.load_xray_config", return_value={}),
        patch("services.client_service.rename_client_in_config", return_value=True),
        patch("services.client_service.save_xray_config"),
        patch(
            "services.client_service.reload_xray", side_effect=Exception("xray fail")
        ),
    ):
        result = cs.rename_client("old", "new")
        print("DEBUG RESULT:", result)

    assert any("Xray" in x for x in result)


def test_rename_client_xray_reload_exception_path():
    """
    Реальный проход Xray ветки до reload_xray()
    """
    with (
        patch("services.client_service.get_all_vless_clients", return_value=["old"]),
        patch("services.client_service.load_xray_config", return_value={}),
        patch("services.client_service.rename_client_in_config", return_value=True),
        patch("services.client_service.save_xray_config"),
        patch(
            "services.client_service.reload_xray", side_effect=Exception("reload fail")
        ),
        patch("services.client_service.load_awg_registry", return_value={}),
        patch("services.client_service.rename_client_in_usage", return_value=False),
    ):
        result = cs.rename_client("old", "new")
        print("DEBUG RESULT:", result)

    assert any("Xray" in x for x in result)


def test_rename_client_xray_reload_success():
    """
    Успешное переименование через Xray + reload
    """
    with (
        patch("services.client_service.get_all_vless_clients", return_value=["old"]),
        patch("services.client_service.load_xray_config", return_value={}),
        patch("services.client_service.rename_client_in_config", return_value=True),
        patch("services.client_service.save_xray_config"),
        patch("services.client_service.reload_xray") as reload_mock,
        patch("services.client_service.load_awg_registry", return_value={}),
        patch("services.client_service.rename_client_in_usage", return_value=False),
    ):
        cs.rename_client("old", "new")

    reload_mock.assert_called_once()


def test_rename_client_awg_config_returns_false_rolls_back_registry():
    """
    Если AWG registry уже изменён, но awg0.conf не удалось переименовать,
    операция должна завершиться ошибкой и registry должен быть восстановлен.
    """
    registry = {"old": {"public_key": "key"}}

    with (
        patch("services.client_service.get_all_vless_clients", return_value=[]),
        patch("services.client_service.load_xray_config", return_value={}),
        patch(
            "services.client_service.load_awg_registry",
            return_value=registry.copy(),
        ),
        patch("services.client_service.save_awg_registry") as save_registry,
        patch("services.client_service.rename_client_in_usage", return_value=False),
        patch("services.client_service.rename_peer_in_config", return_value=False),
    ):
        result = cs.rename_client("old", "new")

    assert result
    assert any("AWG" in error for error in result)

    # Первый save — новое состояние, второй — rollback исходного.
    assert save_registry.call_count == 2
    assert save_registry.call_args_list[0].args[0] == {"new": {"public_key": "key"}}
    assert save_registry.call_args_list[1].args[0] == {"old": {"public_key": "key"}}


def test_rename_client_awg_config_rolls_back_after_bindings_failure():
    """
    Если AWG registry и awg0.conf уже изменены, а следующий этап падает,
    оба изменения должны быть откатаны.
    """
    registry = {"old": {"public_key": "key"}}

    with (
        patch("services.client_service.get_all_vless_clients", return_value=[]),
        patch("services.client_service.load_xray_config", return_value={}),
        patch(
            "services.client_service.load_awg_registry",
            return_value=registry.copy(),
        ),
        patch("services.client_service.save_awg_registry") as save_registry,
        patch("services.client_service.rename_client_in_usage", return_value=False),
        patch(
            "services.client_service.rename_peer_in_config",
            side_effect=[True, True],
        ) as rename_peer,
        patch(
            "services.client_service.load_client_bindings",
            return_value={"100": ["old"]},
        ),
        patch(
            "services.client_service.save_client_bindings",
            side_effect=Exception("bindings fail"),
        ),
    ):
        result = cs.rename_client("old", "new")

    assert any("bindings" in error for error in result)

    # AWG registry: новое состояние + rollback.
    assert save_registry.call_count == 2
    assert save_registry.call_args_list[0].args[0] == {"new": {"public_key": "key"}}
    assert save_registry.call_args_list[1].args[0] == {"old": {"public_key": "key"}}

    # awg0.conf: rename old -> new + rollback new -> old.
    assert rename_peer.call_args_list[0].args == ("old", "new")
    assert rename_peer.call_args_list[1].args == ("new", "old")


def test_rename_client_awg_rollback_config_failure_is_reported():
    """
    Если основной AWG rename прошёл, но rollback awg0.conf не удался,
    ошибка rollback должна попасть в результат.
    """
    registry = {"old": {"public_key": "key"}}

    with (
        patch("services.client_service.get_all_vless_clients", return_value=[]),
        patch("services.client_service.load_xray_config", return_value={}),
        patch(
            "services.client_service.load_awg_registry",
            return_value=registry.copy(),
        ),
        patch("services.client_service.save_awg_registry"),
        patch("services.client_service.rename_client_in_usage", return_value=False),
        patch(
            "services.client_service.rename_peer_in_config",
            side_effect=[
                True,
                False,
            ],
        ) as rename_peer,
        patch(
            "services.client_service.load_client_bindings",
            return_value={"100": ["old"]},
        ),
        patch(
            "services.client_service.save_client_bindings",
            side_effect=Exception("bindings fail"),
        ),
    ):
        result = cs.rename_client("old", "new")

    assert any("bindings" in error for error in result)
    assert any("rollback AWG" in error for error in result)
    assert rename_peer.call_args_list[0].args == ("old", "new")
    assert rename_peer.call_args_list[1].args == ("new", "old")


def test_rename_client_awg_exception():
    """
    Ошибка AWG ветки добавляется в errors
    """
    with (
        patch("services.client_service.get_all_vless_clients", return_value=[]),
        patch("services.client_service.load_xray_config", return_value={}),
        patch("services.client_service.rename_client_in_usage", return_value=False),
        patch("services.client_service.load_awg_registry", return_value={"old": {}}),
        patch("services.client_service.save_awg_registry"),
        patch(
            "services.client_service.rename_peer_in_config",
            side_effect=Exception("awg fail"),
        ),
    ):
        result = cs.rename_client("old", "new")

    assert any("AWG" in x for x in result)


def test_rename_client_bindings_exception():
    """
    Ошибка обновления bindings добавляется в errors
    """
    with (
        patch("services.client_service.get_all_vless_clients", return_value=[]),
        patch("services.client_service.load_xray_config", return_value={}),
        patch("services.client_service.load_awg_registry", return_value={}),
        patch("services.client_service.rename_client_in_usage", return_value=False),
        patch(
            "services.client_service.load_client_bindings",
            return_value={"100": ["old"]},
        ),
        patch(
            "services.client_service.save_client_bindings",
            side_effect=Exception("bindings fail"),
        ),
    ):
        result = cs.rename_client("old", "new")

    assert any("bindings" in x for x in result)


def test_rename_client_vless_validator_duplicate():
    """
    Валидатор Xray запрещает новое имя
    """
    with (
        patch("services.client_service.get_all_vless_clients", return_value=[]),
        patch("services.client_service.load_xray_config", return_value={}),
        patch("services.client_service.load_awg_registry", return_value={}),
        patch("utils.validators.is_username_unique_vless", return_value=False),
    ):
        result = cs.rename_client("old", "new")

    assert any("Xray" in x for x in result)


def test_rename_client_awg_validator_duplicate():
    """
    Валидатор AWG запрещает новое имя
    """
    with (
        patch("services.client_service.get_all_vless_clients", return_value=[]),
        patch("services.client_service.load_xray_config", return_value={}),
        patch("services.client_service.load_awg_registry", return_value={}),
        patch("utils.validators.is_username_unique_vless", return_value=True),
        patch("utils.validators.is_username_unique_awg", return_value=False),
    ):
        result = cs.rename_client("old", "new")

    assert any("AWG" in x for x in result)


def test_rename_client_name_validation_exception():
    """
    Ошибка проверки уникальности имени
    """
    with (
        patch("services.client_service.get_all_vless_clients", return_value=[]),
        patch("services.client_service.load_xray_config", return_value={}),
        patch("services.client_service.load_awg_registry", return_value={}),
        patch(
            "utils.validators.is_username_unique_vless",
            side_effect=Exception("validator fail"),
        ),
    ):
        result = cs.rename_client("old", "new")

    assert any("Ошибка проверки имени" in x for x in result)


def test_rename_client_xray_check_exception():
    """
    Ошибка проверки Xray не ломает переименование
    """
    with (
        patch("services.client_service.get_all_vless_clients", return_value=[]),
        patch("services.client_service.load_xray_config", return_value={}),
        patch(
            "services.client_service.rename_client_in_config",
            side_effect=Exception("xray check fail"),
        ),
        patch("services.client_service.load_awg_registry", return_value={}),
        patch("services.client_service.rename_client_in_usage", return_value=False),
    ):
        result = cs.rename_client("old", "new")

    assert any("не найден" in x or "Xray" in x for x in result)


def test_delete_client_vless_cleans_usage_and_bindings(monkeypatch):
    calls = []

    monkeypatch.setattr(cs, "load_xray_config", lambda: {"inbounds": []})
    monkeypatch.setattr(
        cs,
        "remove_client_from_all_inbounds",
        lambda config, username: calls.append(("xray", username)),
    )
    monkeypatch.setattr(cs, "save_xray_config", lambda config: None)
    monkeypatch.setattr(cs, "reload_xray", lambda: None)
    monkeypatch.setattr(
        cs,
        "remove_client_from_usage",
        lambda username: calls.append(("usage", username)),
    )
    monkeypatch.setattr(
        cs,
        "remove_client_from_all_bindings",
        lambda username: calls.append(("bindings", username)),
    )

    cs.delete_client("client1", "vless")

    assert calls == [
        ("xray", "client1"),
        ("usage", "client1"),
        ("bindings", "client1"),
    ]


def test_delete_client_awg_cleans_usage_and_bindings(monkeypatch):
    calls = []

    monkeypatch.setattr(
        cs,
        "awg_del_user",
        lambda username: calls.append(("awg", username)) or (True, "Удалён"),
    )
    monkeypatch.setattr(
        cs,
        "remove_client_from_usage",
        lambda username: calls.append(("usage", username)),
    )
    monkeypatch.setattr(
        cs,
        "remove_client_from_all_bindings",
        lambda username: calls.append(("bindings", username)),
    )

    cs.delete_client("client1", "awg")

    assert calls == [
        ("awg", "client1"),
        ("usage", "client1"),
        ("bindings", "client1"),
    ]


def test_get_client_protocol_in_both(monkeypatch):
    monkeypatch.setattr(
        cs,
        "get_users_list",
        lambda proto: ["user1"] if proto in ("vless", "awg") else [],
    )
    import pytest

    with pytest.raises(ValueError, match="одновременно присутствует"):
        cs.get_client_protocol("user1")


def test_get_client_protocol_in_neither(monkeypatch):
    monkeypatch.setattr(cs, "get_users_list", lambda proto: [])
    assert cs.get_client_protocol("user1") is None


def test_delete_client_awg_failure_does_not_clean_related_data(monkeypatch):
    calls = []

    monkeypatch.setattr(
        cs,
        "awg_del_user",
        lambda username: (False, "❌ Ошибка AWG runtime: delete failed"),
    )
    monkeypatch.setattr(
        cs,
        "remove_client_from_usage",
        lambda username: calls.append(("usage", username)),
    )
    monkeypatch.setattr(
        cs,
        "remove_client_from_all_bindings",
        lambda username: calls.append(("bindings", username)),
    )

    try:
        cs.delete_client("client1", "awg")
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "Ошибка AWG runtime" in str(exc)

    assert calls == []


def test_delete_client_unknown_proto():
    import pytest

    with pytest.raises(ValueError, match="Unknown protocol"):
        cs.delete_client("user1", "unknown")


def test_send_qr_or_conf_vless_config_only_empty():
    bot = Mock()
    with patch("services.client_service.xray_get_link", return_value="\n  \n"):
        import pytest

        with pytest.raises(ValueError, match="VLESS links not found"):
            cs.send_qr_or_conf(bot, 100, "client1", "vless", config_only=True)


def test_send_qr_or_conf_vless_config_only_urlsplit_exception(monkeypatch):
    bot = Mock()

    def fake_urlsplit(*args, **kwargs):
        raise ValueError("bad url")

    monkeypatch.setattr(cs, "urlsplit", fake_urlsplit)

    with patch("services.client_service.xray_get_link", return_value="bad_link"):
        cs.send_qr_or_conf(bot, 100, "client1", "vless", config_only=True)

    call_args = bot.send_message.call_args
    assert "🔗 VLESS" in call_args[0][1]


def test_send_qr_or_conf_awg_oserror(monkeypatch):
    bot = Mock()

    def fake_open(path, mode="r", *args, **kwargs):
        if path == cs.AWG_CONF:
            raise OSError("No such file")
        return mock_open(read_data=b"qr").return_value

    monkeypatch.setattr(cs, "awg_get_config", lambda u: "awg-config")
    monkeypatch.setattr(
        cs, "load_awg_registry", lambda: {"client1": {"ip": "10.66.66.10"}}
    )
    monkeypatch.setattr(cs.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr(cs.os.path, "exists", lambda p: False)

    with patch("builtins.open", side_effect=fake_open):
        cs.send_qr_or_conf(bot, 100, "client1", "awg")

    bot.send_photo.assert_called_once()
    bot.send_document.assert_called_once()
    call_args = bot.send_photo.call_args
    assert "N/A" in call_args[1]["caption"]


def test_send_qr_or_conf_unknown_proto():
    bot = Mock()
    import pytest

    with pytest.raises(ValueError, match="Unknown protocol"):
        cs.send_qr_or_conf(bot, 100, "client1", "unknown")


def test_show_history_action_send_exception(monkeypatch):
    monkeypatch.setattr(cs, "load_history", lambda: 1 / 0)
    bot = Mock()
    bot.send_message.side_effect = Exception("send fail")

    # Должно перехватить внешнее исключение, попытаться отправить ошибку,
    # перехватить внутреннее исключение и залогировать его, не упав.
    cs.show_history_action(bot, 123)


def test_show_history_action_all_action_types(monkeypatch):
    history = [
        {
            "time": "1",
            "action": "ПЕРЕИМЕНОВАНИЕ",
            "target": "t",
            "status": "SUCCESS",
            "details": "",
        },
        {
            "time": "2",
            "action": "СОЗДАНИЕ БЭКАПА",
            "target": "t",
            "status": "SUCCESS",
            "details": "",
        },
        {
            "time": "3",
            "action": "УДАЛЕНИЕ SSH-КЛЮЧА",
            "target": "t",
            "status": "SUCCESS",
            "details": "",
        },
        {
            "time": "4",
            "action": "ЗАВЕРШЕНИЕ ПРОЦЕССА",
            "target": "t",
            "status": "SUCCESS",
            "details": "",
        },
        {
            "time": "5",
            "action": "РАЗБАН IP",
            "target": "t",
            "status": "SUCCESS",
            "details": "",
        },
    ]
    monkeypatch.setattr(cs, "load_history", lambda: history)
    bot = Mock()
    cs.show_history_action(bot, 123)
    text = bot.send_message.call_args[0][1]
    assert "ПЕРЕИМЕНОВАН" in text
    assert "СОЗДАН БЭКАП" in text
    assert "УДАЛЁН SSH" in text
    assert "ЗАВЕРШЁН ПРОЦЕСС" in text
    assert "РАЗБАНЕН IP" in text


def test_show_history_action_remaining_action_types(monkeypatch):
    history = [
        {
            "time": "1",
            "action": "ПРИВЯЗКА",
            "target": "t",
            "status": "SUCCESS",
            "details": "",
        },
        {
            "time": "2",
            "action": "ОТВЯЗКА",
            "target": "t",
            "status": "SUCCESS",
            "details": "",
        },
    ]
    monkeypatch.setattr(cs, "load_history", lambda: history)
    bot = Mock()
    cs.show_history_action(bot, 123)
    text = bot.send_message.call_args[0][1]
    assert "ПРИВЯЗАН" in text
    assert "ОТВЯЗАН" in text


def test_get_client_protocol_vless_success(monkeypatch):
    monkeypatch.setattr(
        cs, "get_users_list", lambda proto: ["user1"] if proto == "vless" else []
    )
    assert cs.get_client_protocol("user1") == "vless"


def test_get_client_protocol_awg_success(monkeypatch):
    monkeypatch.setattr(
        cs, "get_users_list", lambda proto: ["user1"] if proto == "awg" else []
    )
    assert cs.get_client_protocol("user1") == "awg"


def test_send_qr_or_conf_vless_config_only_ports(monkeypatch):
    bot = Mock()
    links = (
        "vless://test@1.2.3.4:443\nvless://test@1.2.3.4:2096\nvless://test@1.2.3.4:8443"
    )
    monkeypatch.setattr(cs, "xray_get_link", lambda u: links)

    cs.send_qr_or_conf(bot, 100, "client1", "vless", config_only=True)

    text = bot.send_message.call_args[0][1]
    assert "VLESS 443" in text
    assert "VLESS 2096" in text
    assert "VLESS 8443" in text


def test_send_qr_or_conf_awg_listen_port_success(monkeypatch):
    bot = Mock()

    def fake_open(path, mode="r", *args, **kwargs):
        if path == cs.AWG_CONF:
            return mock_open(read_data="ListenPort=12345\n").return_value
        return mock_open(read_data=b"qr").return_value

    monkeypatch.setattr(cs, "awg_get_config", lambda u: "awg-config")
    monkeypatch.setattr(
        cs, "load_awg_registry", lambda: {"client1": {"ip": "10.66.66.10"}}
    )
    monkeypatch.setattr(cs.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr(cs.os.path, "exists", lambda p: False)

    with patch("builtins.open", side_effect=fake_open):
        cs.send_qr_or_conf(bot, 100, "client1", "awg")

    call_args = bot.send_photo.call_args
    assert "12345" in call_args[1]["caption"]


def test_show_history_action_send_exception_with_mid(monkeypatch):
    monkeypatch.setattr(cs, "load_history", lambda: 1 / 0)
    bot = Mock()
    bot.edit_message_text.side_effect = Exception("send fail")

    cs.show_history_action(bot, 123, mid=456)

    bot.edit_message_text.assert_called()


def test_send_qr_or_conf_vless_qr_third_port(monkeypatch):
    bot = Mock()
    cfg = {
        "inbounds": [
            {"protocol": "vless", "port": 443},
            {"protocol": "vless", "port": 2096},
            {"protocol": "vless", "port": 8443},
        ]
    }
    monkeypatch.setattr(cs, "xray_get_link", lambda u: "link1\nlink2\nlink3")
    monkeypatch.setattr(cs, "load_xray_config", lambda: cfg)
    monkeypatch.setattr(cs, "get_vless_inbounds", lambda c: c["inbounds"])

    cs.send_qr_or_conf(bot, 100, "client1", "vless")

    reply_markup = bot.send_message.call_args[1]["reply_markup"]
    button_texts = [btn.text for row in reply_markup.keyboard for btn in row]
    assert "📱 VLESS:8443" in button_texts


def test_send_qr_or_conf_awg_document_not_found(monkeypatch):
    bot = Mock()

    monkeypatch.setattr(cs, "awg_get_config", Mock(side_effect=["awg-config", None]))
    monkeypatch.setattr(
        cs, "load_awg_registry", lambda: {"client1": {"ip": "10.66.66.10"}}
    )
    monkeypatch.setattr(cs.subprocess, "run", lambda *a, **kw: None)

    original_open = open

    def fake_open(path, *args, **kwargs):
        if path == cs.AWG_CONF:
            raise OSError("No such file")
        if "qr_" in path and "rb" in args:
            from io import BytesIO

            return BytesIO(b"fake_image")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)

    import pytest

    with pytest.raises(ValueError, match="AWG config not found"):
        cs.send_qr_or_conf(bot, 100, "client1", "awg")


def test_rename_client_rolls_back_previous_changes_on_failure(monkeypatch):
    """При сбое одного из этапов уже выполненные изменения откатываются."""
    usage = []
    xray = {"inbounds": [{"clients": [{"email": "old"}]}]}
    awg = {}
    bindings = {"100": ["old"]}

    monkeypatch.setattr(
        cs,
        "rename_client_in_usage",
        lambda old, new: usage.append((old, new)) or True,
    )

    monkeypatch.setattr(cs, "load_xray_config", lambda: xray)
    monkeypatch.setattr(
        cs,
        "rename_client_in_config",
        lambda config, old, new: True,
    )
    monkeypatch.setattr(cs, "save_xray_config", lambda config: None)
    monkeypatch.setattr(
        cs,
        "reload_xray",
        lambda: (_ for _ in ()).throw(RuntimeError("xray reload failed")),
    )

    monkeypatch.setattr(cs, "load_awg_registry", lambda: awg)
    monkeypatch.setattr(cs, "load_client_bindings", lambda: bindings)

    result = cs.rename_client("old", "new")

    assert any("xray reload failed" in error for error in result)
    assert usage == [("old", "new"), ("new", "old")]


def test_rename_client_reports_usage_rollback_failure():
    with (
        patch("services.client_service.get_all_vless_clients", return_value=[]),
        patch("services.client_service.load_xray_config", return_value={}),
        patch("services.client_service.load_awg_registry", return_value={}),
        patch("services.client_service.load_client_bindings", return_value={}),
        patch(
            "services.client_service.rename_client_in_usage",
            side_effect=[True, Exception("usage rollback failed")],
        ),
        patch(
            "services.client_service.rename_client_in_config",
            side_effect=Exception("xray failed"),
        ),
    ):
        result = cs.rename_client("old", "new")

    assert any("Xray: xray failed" in error for error in result)
    assert any("rollback usage: usage rollback failed" in error for error in result)


def test_rename_client_logs_started_event(monkeypatch):
    monkeypatch.setattr(cs, "load_xray_config", lambda: {"inbounds": []})
    monkeypatch.setattr(cs, "load_awg_registry", lambda: {})
    monkeypatch.setattr(cs, "load_client_bindings", lambda: {})
    monkeypatch.setattr(cs, "rename_client_in_usage", lambda old, new: False)
    monkeypatch.setattr(cs, "rename_client_in_config", lambda cfg, old, new: False)

    with patch("services.client_service.logger.info") as mock_info:
        cs.rename_client("old", "new")

    first_call = mock_info.call_args_list[0]
    assert first_call.args == (
        "client.rename.started | old_name=%s | new_name=%s",
        "old",
        "new",
    )


def test_rename_client_logs_completed_event(monkeypatch):
    monkeypatch.setattr(cs, "load_xray_config", lambda: {"inbounds": []})
    monkeypatch.setattr(cs, "load_awg_registry", lambda: {})
    monkeypatch.setattr(cs, "load_client_bindings", lambda: {})
    monkeypatch.setattr(cs, "rename_client_in_usage", lambda old, new: True)
    monkeypatch.setattr(cs, "rename_client_in_config", lambda cfg, old, new: False)

    with patch("services.client_service.logger.info") as mock_info:
        cs.rename_client("old", "new")

    completed_calls = [
        call
        for call in mock_info.call_args_list
        if call.args
        and call.args[0] == (
            "client.rename.completed | old_name=%s | new_name=%s | "
            "success=%s | errors=%s"
        )
    ]

    assert len(completed_calls) == 1
    assert completed_calls[0].args == (
        "client.rename.completed | old_name=%s | new_name=%s | "
        "success=%s | errors=%s",
        "old",
        "new",
        True,
        0,
    )


def test_rename_client_logs_completed_failure_event(monkeypatch):
    def broken_loader():
        raise RuntimeError("load failed")

    monkeypatch.setattr(cs, "load_xray_config", broken_loader)
    monkeypatch.setattr(cs, "load_awg_registry", lambda: {})
    monkeypatch.setattr(cs, "load_client_bindings", lambda: {})

    with patch("services.client_service.logger.info") as mock_info:
        result = cs.rename_client("old", "new")

    assert result == ["Xray: load failed"]

    completed_calls = [
        call
        for call in mock_info.call_args_list
        if call.args
        and call.args[0] == (
            "client.rename.completed | old_name=%s | new_name=%s | "
            "success=%s | errors=%s"
        )
    ]

    assert len(completed_calls) == 1
    assert completed_calls[0].args == (
        "client.rename.completed | old_name=%s | new_name=%s | "
        "success=%s | errors=%s",
        "old",
        "new",
        False,
        1,
    )


def test_show_history_action_logs_history_failure(monkeypatch):
    error = RuntimeError("history failed")
    monkeypatch.setattr(cs, "load_history", Mock(side_effect=error))
    bot = Mock()

    with patch("services.client_service.logger.exception") as mock_exception:
        cs.show_history_action(bot, 123)

    mock_exception.assert_called_once()
    args = mock_exception.call_args.args
    assert args[0] == "client.history.failed | error=%s"
    assert args[1] is error


def test_show_history_action_logs_send_failure(monkeypatch):
    history_error = RuntimeError("history failed")
    send_error = RuntimeError("send failed")

    monkeypatch.setattr(cs, "load_history", Mock(side_effect=history_error))
    bot = Mock()
    bot.send_message.side_effect = send_error

    with patch("services.client_service.logger.exception") as mock_exception:
        cs.show_history_action(bot, 123)

    assert mock_exception.call_count == 2

    first_args = mock_exception.call_args_list[0].args
    second_args = mock_exception.call_args_list[1].args

    assert first_args[0] == "client.history.failed | error=%s"
    assert first_args[1] is history_error

    assert second_args[0] == "client.history.send_failed | error=%s"
    assert second_args[1] is send_error
