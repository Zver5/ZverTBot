from unittest.mock import patch

from services.vps_monitor import (
    MonitorCategory,
    MonitorFailure,
    MonitorResult,
    MonitorState,
)
from services.vps_monitor_runner import (
    _admin_chats,
    _format_update,
    notify_updates,
    run_once,
)
from services.vps_monitor_state import StateUpdate


def update(
    name: str,
    previous: MonitorState,
    current: MonitorState,
    notify: bool = True,
    failure: MonitorFailure | None = None,
    details: str = "",
) -> StateUpdate:
    return StateUpdate(
        name=name,
        previous=previous,
        current=current,
        notify=notify,
        failure=failure,
        details=details,
    )


def test_admin_chat_supports_single_chat(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT", "12345")
    monkeypatch.delenv("ADMIN_CHATS", raising=False)

    assert _admin_chats() == ["12345"]


def test_admin_chats_support_multiple_chats(monkeypatch):
    monkeypatch.setenv("ADMIN_CHATS", "123, 456,789")

    assert _admin_chats() == ["123", "456", "789"]


def test_admin_chats_prefer_admin_chats(monkeypatch):
    monkeypatch.setenv("ADMIN_CHATS", "123,456")
    monkeypatch.setenv("ADMIN_CHAT", "999")

    assert _admin_chats() == ["123", "456"]


def test_down_message_mentions_only_affected_item():
    text = _format_update(
        update("xray", MonitorState.UP, MonitorState.DOWN),
        MonitorCategory.OPTIONAL,
    )

    assert "🚀 <b>Сервис: Xray</b>" in text
    assert "Сервис недоступен" in text
    assert "zvertbot" not in text
    assert "stats-http" not in text


def test_recovery_message_mentions_only_affected_item():
    text = _format_update(
        update("stats-http", MonitorState.DOWN, MonitorState.UP),
        MonitorCategory.CRITICAL,
    )

    assert "📊 <b>Сервис: Stats HTTP HASS</b>" in text
    assert "Работа восстановлена" in text
    assert "zvertbot" not in text


def test_systemd_inactive_message():
    text = _format_update(
        update(
            "zvertbot",
            MonitorState.UP,
            MonitorState.DOWN,
            failure=MonitorFailure.SYSTEMD_INACTIVE,
            details="systemd state: inactive",
        ),
        MonitorCategory.CRITICAL,
    )

    assert "🤖 <b>Сервис: ZverTBot</b>" in text
    assert "🔴 Сервис остановлен" in text
    assert "systemd: inactive" in text


def test_systemd_failed_message():
    text = _format_update(
        update(
            "zvertbot",
            MonitorState.UP,
            MonitorState.DOWN,
            failure=MonitorFailure.SYSTEMD_FAILED,
            details="systemd state: failed",
        ),
        MonitorCategory.CRITICAL,
    )

    assert "🤖 <b>Сервис: ZverTBot</b>" in text
    assert "🔴 Сервис завершился с ошибкой" in text
    assert "systemd: failed" in text


def test_http_failed_message():
    text = _format_update(
        update(
            "stats-http",
            MonitorState.UP,
            MonitorState.DOWN,
            failure=MonitorFailure.HTTP_FAILED,
            details="HTTP request failed",
        ),
        MonitorCategory.CRITICAL,
    )

    assert "📊 <b>Сервис: Stats HTTP HASS</b>" in text
    assert "🔴 Сервис запущен, но не отвечает" in text
    assert "systemd: active · HTTP: failed" in text


def test_tcp_failed_message():
    text = _format_update(
        update(
            "ssh",
            MonitorState.UP,
            MonitorState.DOWN,
            failure=MonitorFailure.TCP_FAILED,
            details="active; TCP 22 unreachable",
        ),
        MonitorCategory.OPTIONAL,
    )

    assert "🔑 <b>Сервис: SSH</b>" in text
    assert "🔴 Сервис запущен, но порт недоступен" in text
    assert "systemd: active · TCP: failed" in text


def test_udp_failed_message():
    text = _format_update(
        update(
            "awg",
            MonitorState.UP,
            MonitorState.DOWN,
            failure=MonitorFailure.UDP_FAILED,
            details="AWG listening port unavailable",
        ),
        MonitorCategory.OPTIONAL,
    )

    assert "🛡️ <b>Сервис: AWG</b>" in text
    assert "🔴 Сервис запущен, но порт недоступен" in text
    assert "systemd: active · UDP: failed" in text

def test_backup_failed_message():
    text = _format_update(
        update(
            "backup",
            MonitorState.UP,
            MonitorState.DOWN,
            failure=MonitorFailure.BACKUP_FAILED,
            details="backup status: failed",
        ),
        MonitorCategory.OPTIONAL,
    )

    assert "💾 <b>Сервис: Backup</b>" in text
    assert "🔴 Последний бэкап завершился с ошибкой" in text


def test_backup_stale_message():
    text = _format_update(
        update(
            "backup",
            MonitorState.UP,
            MonitorState.DOWN,
            failure=MonitorFailure.BACKUP_STALE,
            details="last backup is 36000 seconds old",
        ),
        MonitorCategory.OPTIONAL,
    )

    assert "💾 <b>Сервис: Backup</b>" in text
    assert "🔴 Бэкап просрочен" in text
    assert "последний: 10 ч 0 мин назад" in text

def test_details_are_html_escaped():
    text = _format_update(
        update(
            "zvertbot",
            MonitorState.UP,
            MonitorState.DOWN,
            details="<danger> & broken",
        ),
        MonitorCategory.CRITICAL,
    )

    assert "&lt;danger&gt; &amp; broken" in text
    assert "<danger>" not in text

def test_non_transition_is_not_sent(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT", "123")

    with patch(
        "services.vps_monitor_runner._telegram_send"
    ) as send:
        notify_updates(
            [
                update(
                    "zvertbot",
                    MonitorState.UP,
                    MonitorState.UP,
                    notify=False,
                )
            ],
            {"zvertbot": MonitorCategory.CRITICAL},
        )

    send.assert_not_called()


def test_down_transition_is_sent(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT", "123")

    with patch(
        "services.vps_monitor_runner._telegram_send"
    ) as send:
        notify_updates(
            [
                update(
                    "zvertbot",
                    MonitorState.UP,
                    MonitorState.DOWN,
                )
            ],
            {"zvertbot": MonitorCategory.CRITICAL},
        )

    send.assert_called_once()
    assert send.call_args.args[0] == "123"
    assert "🤖 <b>Сервис: ZverTBot</b>" in send.call_args.args[1]


def test_recovery_transition_is_sent(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT", "123")

    with patch(
        "services.vps_monitor_runner._telegram_send"
    ) as send:
        notify_updates(
            [
                update(
                    "backup",
                    MonitorState.DOWN,
                    MonitorState.UP,
                )
            ],
            {"backup": MonitorCategory.OPTIONAL},
        )

    send.assert_called_once()
    assert "💾 <b>Сервис: Backup</b>" in send.call_args.args[1]
    assert "🟢 Бэкап снова выполняется успешно" in send.call_args.args[1]


def test_multiple_admin_chats_receive_same_event(monkeypatch):
    monkeypatch.setenv("ADMIN_CHATS", "111,222")

    with patch(
        "services.vps_monitor_runner._telegram_send"
    ) as send:
        notify_updates(
            [
                update(
                    "xray",
                    MonitorState.UP,
                    MonitorState.DOWN,
                )
            ],
            {"xray": MonitorCategory.OPTIONAL},
        )

    assert send.call_count == 2
    assert {call.args[0] for call in send.call_args_list} == {
        "111",
        "222",
    }


def test_data_collectors_are_not_alarm_sources(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT", "123")

    with patch(
        "services.vps_monitor_runner._telegram_send"
    ) as send:
        notify_updates(
            [
                update(
                    "xray-traffic-collect",
                    MonitorState.UP,
                    MonitorState.DOWN,
                )
            ],
            {
                "xray-traffic-collect":
                    MonitorCategory.DATA_COLLECTOR
            },
        )

    send.assert_not_called()


def test_run_once_logs_state_transition():
    results = [
        MonitorResult(
            name="stats-http",
            category=MonitorCategory.CRITICAL,
            healthy=False,
        )
    ]

    updates = [
        update(
            "stats-http",
            MonitorState.UP,
            MonitorState.DOWN,
            failure=MonitorFailure.HTTP_FAILED,
            details="HTTP request failed",
        )
    ]

    with patch(
        "services.vps_monitor_runner.check_all",
        return_value=results,
    ):
        with patch(
            "services.vps_monitor_runner.prepare_results",
            return_value=(updates, {"stats-http": MonitorState.DOWN}),
        ):
            with patch("services.vps_monitor_runner.notify_updates"):
                with patch("services.vps_monitor_runner.save_states"):
                    with patch(
                        "services.vps_monitor_runner.logger.info"
                    ) as log_info:
                        run_once()

    log_info.assert_called_once_with(
        "vps_monitor.state_changed | service=%s | %s -> %s | details=%s",
        "stats-http",
        "up",
        "down",
        "HTTP request failed",
    )


def test_run_once_checks_processes_and_notifies(monkeypatch):
    results = [
        MonitorResult(
            name="zvertbot",
            category=MonitorCategory.CRITICAL,
            healthy=False,
        )
    ]

    updates = [
        update(
            "zvertbot",
            MonitorState.UP,
            MonitorState.DOWN,
        )
    ]

    with patch(
        "services.vps_monitor_runner.check_all",
        return_value=results,
    ) as check:
        with patch(
            "services.vps_monitor_runner.prepare_results",
            return_value=(updates, {"zvertbot": MonitorState.DOWN}),
        ) as process:
            with patch(
                "services.vps_monitor_runner.notify_updates"
            ) as notify:
                with patch(
                    "services.vps_monitor_runner.save_states"
                ) as save:
                    run_once()

    check.assert_called_once()
    process.assert_called_once_with(results)
    notify.assert_called_once_with(
        updates,
        {"zvertbot": MonitorCategory.CRITICAL},
    )
    save.assert_called_once_with({"zvertbot": MonitorState.DOWN})


def test_run_once_does_not_save_state_when_notification_fails():
    results = [
        MonitorResult(
            name="zvertbot",
            category=MonitorCategory.CRITICAL,
            healthy=False,
        )
    ]

    updates = [
        update(
            "zvertbot",
            MonitorState.UP,
            MonitorState.DOWN,
        )
    ]

    with patch(
        "services.vps_monitor_runner.check_all",
        return_value=results,
    ):
        with patch(
            "services.vps_monitor_runner.prepare_results",
            return_value=(updates, {"zvertbot": MonitorState.DOWN}),
        ):
            with patch(
                "services.vps_monitor_runner.notify_updates",
                side_effect=RuntimeError("Telegram unavailable"),
            ):
                with patch(
                    "services.vps_monitor_runner.save_states"
                ) as save:
                    try:
                        run_once()
                    except RuntimeError:
                        pass

    save.assert_not_called()


def test_telegram_failure_does_not_change_state_logic():
    assert MonitorState.DOWN.value == "down"
    assert MonitorState.UP.value == "up"
