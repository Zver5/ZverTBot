from multiprocessing import Process, Queue
from pathlib import Path
from unittest.mock import patch

from services.vps_monitor import (
    MonitorCategory,
    MonitorFailure,
    MonitorResult,
    MonitorState,
)
from services.vps_monitor_notifications import load_pending_notifications
from services.vps_monitor_runner import (
    _admin_chats,
    _format_update,
    acquire_monitor_lock,
    notify_updates,
    run_once,
)
from services.vps_monitor_state import StateUpdate


def _try_monitor_lock(lock_path: str, result: Queue) -> None:
    lock_file = acquire_monitor_lock(lock_path)
    result.put(lock_file is not None)
    if lock_file is not None:
        lock_file.close()


def test_monitor_lock_can_be_acquired(tmp_path: Path):
    lock_path = tmp_path / "monitor.lock"

    lock_file = acquire_monitor_lock(str(lock_path))

    assert lock_file is not None
    lock_file.close()


def test_monitor_lock_is_released_for_next_process(tmp_path: Path):
    lock_path = tmp_path / "monitor.lock"
    lock_file = acquire_monitor_lock(str(lock_path))
    assert lock_file is not None
    lock_file.close()

    result = Queue()
    process = Process(
        target=_try_monitor_lock,
        args=(str(lock_path), result),
    )

    process.start()
    process.join(timeout=5)

    assert process.exitcode == 0
    assert result.get(timeout=2) is True


def test_monitor_lock_blocks_second_process(tmp_path: Path):
    lock_path = tmp_path / "monitor.lock"
    lock_file = acquire_monitor_lock(str(lock_path))
    assert lock_file is not None

    result = Queue()
    process = Process(
        target=_try_monitor_lock,
        args=(str(lock_path), result),
    )

    try:
        process.start()
        process.join(timeout=5)

        assert process.exitcode == 0
        assert result.get(timeout=2) is False
    finally:
        lock_file.close()
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)


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


def test_notification_requires_admin_chat(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ADMIN_CHAT", raising=False)
    monkeypatch.delenv("ADMIN_CHATS", raising=False)

    with patch("services.vps_monitor_runner._telegram_send") as send:
        try:
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
        except RuntimeError as exc:
            assert str(exc) == "Neither ADMIN_CHATS nor ADMIN_CHAT is configured"
        else:
            raise AssertionError("notify_updates() must require an admin chat")

    send.assert_not_called()


def test_non_transition_is_not_sent(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ADMIN_CHAT", "123")

    with patch("services.vps_monitor_runner._telegram_send") as send:
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


def test_down_transition_is_sent(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ADMIN_CHAT", "123")

    with patch("services.vps_monitor_runner._telegram_send") as send:
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


def test_recovery_transition_is_sent(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ADMIN_CHAT", "123")

    with patch("services.vps_monitor_runner._telegram_send") as send:
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


def test_multiple_admin_chats_receive_same_event(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ADMIN_CHATS", "111,222")

    with patch("services.vps_monitor_runner._telegram_send") as send:
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


def test_data_collectors_are_not_alarm_sources(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ADMIN_CHAT", "123")

    with patch("services.vps_monitor_runner._telegram_send") as send:
        notify_updates(
            [
                update(
                    "xray-traffic-collect",
                    MonitorState.UP,
                    MonitorState.DOWN,
                )
            ],
            {"xray-traffic-collect": MonitorCategory.DATA_COLLECTOR},
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
            with patch(
                "services.vps_monitor_runner._queue_notifications"
            ):
                with patch(
                    "services.vps_monitor_runner._deliver_pending_notifications"
                ):
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


def test_run_once_checks_processes_and_notifies(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)

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
                "services.vps_monitor_runner._queue_notifications"
            ) as queue:
                with patch(
                    "services.vps_monitor_runner._deliver_pending_notifications"
                ) as deliver:
                    with patch(
                        "services.vps_monitor_runner.save_states"
                    ) as save:
                        run_once()

    check.assert_called_once()
    process.assert_called_once_with(results)
    queue.assert_called_once_with(
        updates,
        {"zvertbot": MonitorCategory.CRITICAL},
    )
    save.assert_called_once_with({"zvertbot": MonitorState.DOWN})
    deliver.assert_called_once()


def test_run_once_queues_before_state_and_delivery(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)

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

    events = []

    def queue_side_effect(updates, categories):
        events.append(("queue", updates, categories))

    def save_states_side_effect(states):
        events.append(("save", states))

    def deliver_side_effect():
        events.append(("deliver",))

    with patch(
        "services.vps_monitor_runner.check_all",
        return_value=results,
    ):
        with patch(
            "services.vps_monitor_runner.prepare_results",
            return_value=(updates, {"zvertbot": MonitorState.DOWN}),
        ):
            with patch(
                "services.vps_monitor_runner._queue_notifications",
                side_effect=queue_side_effect,
            ):
                with patch(
                    "services.vps_monitor_runner.save_states",
                    side_effect=save_states_side_effect,
                ):
                    with patch(
                        "services.vps_monitor_runner._deliver_pending_notifications",
                        side_effect=deliver_side_effect,
                    ):
                        run_once()

    assert [event[0] for event in events] == [
        "queue",
        "save",
        "deliver",
    ]


def test_failed_chat_remains_pending_and_is_retried(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ADMIN_CHATS", "111,222")

    with patch(
        "services.vps_monitor_runner._telegram_send",
        side_effect=[None, RuntimeError("Telegram unavailable")],
    ):
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

    pending = load_pending_notifications()

    assert len(pending) == 1
    assert pending[0].chat_id == "222"
    assert pending[0].service == "zvertbot"
    assert pending[0].state == MonitorState.DOWN

    with patch("services.vps_monitor_runner._telegram_send") as send:
        notify_updates([], {})

    send.assert_called_once_with("222", pending[0].message)
    assert load_pending_notifications() == []


def test_recovery_notification_is_independent_from_down_delivery(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ADMIN_CHAT", "111")

    with patch(
        "services.vps_monitor_runner._telegram_send",
        side_effect=RuntimeError("Telegram unavailable"),
    ):
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

    with patch("services.vps_monitor_runner._telegram_send") as send:
        notify_updates(
            [
                update(
                    "zvertbot",
                    MonitorState.DOWN,
                    MonitorState.UP,
                )
            ],
            {"zvertbot": MonitorCategory.CRITICAL},
        )

    assert send.call_count == 2
    assert [call.args[0] for call in send.call_args_list] == [
        "111",
        "111",
    ]


def test_telegram_failure_does_not_change_state_logic(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

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

    events = []

    def queue_side_effect(updates, categories):
        events.append(("queue", updates, categories))

    def save_states_side_effect(states):
        events.append(("save", states))

    def deliver_side_effect():
        events.append(("deliver",))
        raise RuntimeError("Telegram unavailable")

    with patch(
        "services.vps_monitor_runner.check_all",
        return_value=results,
    ):
        with patch(
            "services.vps_monitor_runner.prepare_results",
            return_value=(updates, {"zvertbot": MonitorState.DOWN}),
        ):
            with patch(
                "services.vps_monitor_runner._queue_notifications",
                side_effect=queue_side_effect,
            ):
                with patch(
                    "services.vps_monitor_runner.save_states",
                    side_effect=save_states_side_effect,
                ):
                    with patch(
                        "services.vps_monitor_runner._deliver_pending_notifications",
                        side_effect=deliver_side_effect,
                    ):
                        try:
                            run_once()
                        except RuntimeError:
                            pass

    assert [event[0] for event in events] == [
        "queue",
        "save",
        "deliver",
    ]
    assert events[1] == (
        "save",
        {"zvertbot": MonitorState.DOWN},
    )
