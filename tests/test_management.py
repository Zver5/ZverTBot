"""
Тесты для handlers/admin/management.py
Проверяет callback'и управления: рестарты, логи, очистка, бэкапы, статистика
"""

from unittest.mock import Mock, patch

import pytest

from handlers.admin.management import (
    handle_management_part1_callback,
    handle_management_part2_callback,
    handle_management_part3_callback,
    handle_management_part4_callback,
    render_backup_history,
)


@pytest.fixture
def mock_bot():
    """Фикстура: мок бота"""
    bot = Mock()
    bot.edit_message_text = Mock()
    bot.send_message = Mock()
    bot.answer_callback_query = Mock()
    return bot


@pytest.fixture
def mock_call():
    """Фикстура: мок callback query"""
    call = Mock()
    call.id = "12345"
    call.message = Mock()
    call.message.message_id = 67890
    call.message.chat.id = 111222
    return call


class TestHandleManagementPart1Callback:
    """Тесты для handle_management_part1_callback (restart_, logs_menu, log_)"""

    def test_restart_xray_returns_true(self, mock_bot, mock_call):
        """Тест: data='restart_xray' возвращает True"""
        with patch("handlers.admin.management._run_service_restart") as mock_restart:
            result = handle_management_part1_callback(
                mock_bot, 111222, mock_call, "restart_xray"
            )

            assert result.text == "Перезапуск Xray..."
            assert result.show_alert is False
            mock_restart.assert_called_once_with(
                "xray",
                "Xray",
                111222,
                mock_call.message.message_id,
            )

    def test_restart_awg_returns_true(self, mock_bot, mock_call):
        """Тест: data='restart_awg' возвращает True"""
        with patch("handlers.admin.management._run_service_restart") as mock_restart:
            result = handle_management_part1_callback(
                mock_bot, 111222, mock_call, "restart_awg"
            )

            assert result.text == "Перезапуск AWG..."
            assert result.show_alert is False
            mock_restart.assert_called_once_with(
                "awg-quick@awg0",
                "AWG",
                111222,
                mock_call.message.message_id,
            )

    def test_restart_bot_returns_true(self, mock_bot, mock_call):
        """Тест: data='restart_bot' возвращает True"""
        with (
            patch("handlers.admin.management.log_action"),
            patch("handlers.admin.management.safe_delete"),
            patch("handlers.admin.management.subprocess.Popen"),
            patch("handlers.admin.management.sys.exit"),
        ):
            result = handle_management_part1_callback(
                mock_bot, 111222, mock_call, "restart_bot"
            )
            assert result.text == "Перезапуск Бот..."
            assert result.show_alert is False

    def test_log_xray_returns_true(self, mock_bot, mock_call):
        """Тест: data='log_xray' возвращает True"""
        with (
            patch("handlers.admin.management.get_service_logs", return_value="logs"),
            patch("handlers.admin.management.log_close_kb", return_value=Mock()),
        ):
            result = handle_management_part1_callback(
                mock_bot, 111222, mock_call, "log_xray"
            )
            assert result.text is None
            assert result.show_alert is False

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        """Тест: неизвестный data возвращает False"""
        result = handle_management_part1_callback(
            mock_bot, 111222, mock_call, "unknown_action"
        )
        assert result is False


class TestHandleManagementPart2Callback:
    """Тесты для handle_management_part2_callback.

    Проверяет close_log, my_external_ip, speedtest.
    """

    def test_close_log_returns_true(self, mock_bot, mock_call):
        """Тест: data='close_log' возвращает True"""
        with patch("handlers.admin.management.safe_delete"):
            result = handle_management_part2_callback(
                mock_bot, 111222, mock_call, "close_log"
            )
            assert result.text is None
            assert result.show_alert is False

    def test_my_external_ip_returns_true(self, mock_bot, mock_call):
        """Тест: data='my_external_ip' возвращает True"""
        with (
            patch("handlers.admin.management.SERVER_IP", "1.2.3.4"),
            patch("handlers.admin.management.threading.Timer"),
            patch("handlers.admin.management.start_ip_server_once"),
        ):
            result = handle_management_part2_callback(
                mock_bot, 111222, mock_call, "my_external_ip"
            )
            assert result.text is None
            assert result.show_alert is False

    def test_speedtest_returns_true(self, mock_bot, mock_call):
        """Тест: data='speedtest' возвращает True"""
        with (
            patch(
                "handlers.admin.management.run_speedtest_and_ip", return_value="result"
            ),
            patch("handlers.admin.management.manage_menu_kb", return_value=Mock()),
        ):
            result = handle_management_part2_callback(
                mock_bot, 111222, mock_call, "speedtest"
            )
            assert result.text == "Запуск speedtest..."
            assert result.show_alert is False

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        """Тест: неизвестный data возвращает False"""
        result = handle_management_part2_callback(
            mock_bot, 111222, mock_call, "unknown_action"
        )
        assert result is False


class TestHandleManagementPart3Callback:
    """Тесты для handle_management_part3_callback.

    Проверяет confirm_cleanup, exec_cleanup, show_history.
    """

    def test_confirm_cleanup_returns_true(self, mock_bot, mock_call):
        """Тест: data='confirm_cleanup' возвращает True"""
        result = handle_management_part3_callback(
            mock_bot, 111222, mock_call, "confirm_cleanup"
        )
        assert result is True

    def test_confirm_cleanup_calls_edit_message(self, mock_bot, mock_call):
        """Тест: confirm_cleanup вызывает edit_message_text"""
        handle_management_part3_callback(mock_bot, 111222, mock_call, "confirm_cleanup")
        mock_bot.edit_message_text.assert_called_once()

    def test_exec_cleanup_returns_true(self, mock_bot, mock_call):
        """Тест: data='exec_cleanup' возвращает True"""
        with (
            patch("handlers.admin.management.run_disk_cleanup", return_value="result"),
            patch("handlers.admin.management.log_action"),
            patch("handlers.admin.management.manage_menu_kb", return_value=Mock()),
        ):
            result = handle_management_part3_callback(
                mock_bot, 111222, mock_call, "exec_cleanup"
            )
            assert result.text == "Запускаю очистку..."
            assert result.show_alert is False

    def test_show_history_returns_true(self, mock_bot, mock_call):
        """Тест: data='show_history' возвращает True"""
        with patch("handlers.admin.management.show_history_action"):
            result = handle_management_part3_callback(
                mock_bot, 111222, mock_call, "show_history"
            )
            assert result.text is None
            assert result.show_alert is False

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        """Тест: неизвестный data возвращает False"""
        result = handle_management_part3_callback(
            mock_bot, 111222, mock_call, "unknown_action"
        )
        assert result is False


class TestHandleManagementPart4Callback:
    """Тесты для handle_management_part4_callback (weekly_report, status, stats_)"""

    def test_weekly_report_returns_true(self, mock_bot, mock_call):
        """Тест: data='weekly_report' возвращает True"""
        result = handle_management_part4_callback(
            mock_bot, 111222, mock_call, "weekly_report"
        )
        assert result.text is None
        assert result.show_alert is False

    def test_bot_stats_returns_true(self, mock_bot, mock_call):
        """Тест: data='bot_stats' возвращает True"""
        with (
            patch("handlers.admin.management.get_bot_stats_text", return_value="stats"),
            patch("handlers.admin.management.manage_menu_kb", return_value=Mock()),
        ):
            result = handle_management_part4_callback(
                mock_bot, 111222, mock_call, "bot_stats"
            )
            assert result.text is None
            assert result.show_alert is False

    def test_create_backup_returns_true(self, mock_bot, mock_call):
        """Тест: data='create_backup' возвращает True"""
        with patch("handlers.admin.management.run_manual_backup"):
            result = handle_management_part4_callback(
                mock_bot, 111222, mock_call, "create_backup"
            )
            assert result.text == "Запускаю бэкап..."
            assert result.show_alert is False

    def test_backup_history_returns_true(self, mock_bot, mock_call):
        """Тест: data='backup_history' открывает navigation screen."""
        from core.navigation import navigation
        from ui.screens import BACKUP_HISTORY

        navigation.clear(111222)

        with patch(
            "handlers.admin.management.render_navigation_screen",
            return_value=True,
        ) as render:
            result = handle_management_part4_callback(
                mock_bot, 111222, mock_call, "backup_history"
            )

        assert result is True
        assert navigation.current(111222) == BACKUP_HISTORY
        render.assert_called_once_with(
            mock_bot,
            111222,
            mock_call.message.message_id,
            BACKUP_HISTORY,
        )

    def test_status_returns_true(self, mock_bot, mock_call):
        """Тест: data='status' возвращает True"""
        with (
            patch("handlers.admin.management.get_status_text", return_value="status"),
            patch("handlers.admin.management.safe_delete"),
            patch("handlers.admin.management.LAST_STATUS_MSGS", {}),
            patch("handlers.admin.management.threading.Timer"),
        ):
            result = handle_management_part4_callback(
                mock_bot, 111222, mock_call, "status"
            )
            assert result.text is None
            assert result.show_alert is False

    def test_stats_vless_returns_true(self, mock_bot, mock_call):
        """Тест: data='stats_vless_client1' возвращает True"""
        with patch(
            "handlers.admin.management.get_client_stats_text", return_value="stats"
        ):
            result = handle_management_part4_callback(
                mock_bot, 111222, mock_call, "stats_vless_client1"
            )
            assert result.text is None
            assert result.show_alert is False

    def test_unknown_data_returns_false(self, mock_bot, mock_call):
        """Тест: неизвестный data возвращает False"""
        result = handle_management_part4_callback(
            mock_bot, 111222, mock_call, "unknown_action"
        )
        assert result is False


def test_run_status_send_message_error_logs_action(monkeypatch):
    from handlers.admin import management

    mock_bot = Mock()
    mock_bot.send_message.side_effect = RuntimeError("send failed")

    monkeypatch.setattr(management, "bot", mock_bot)
    monkeypatch.setattr(management, "LAST_STATUS_MSGS", {})
    monkeypatch.setattr(management, "get_status_text", lambda: "status")
    monkeypatch.setattr(management, "safe_delete", Mock())
    mock_log_action = Mock()
    monkeypatch.setattr(management, "log_action", mock_log_action)

    management._run_status(111222, 67890)

    mock_bot.send_message.assert_called_once_with(
        111222,
        "status",
        parse_mode="Markdown",
    )
    mock_log_action.assert_called_once_with(
        "ОШИБКА ОТПРАВКИ СТАТУСА",
        "111222",
        "ERROR",
        "send failed",
    )
    assert management.LAST_STATUS_MSGS == {}


def test_run_service_restart_service_missing(monkeypatch):
    from handlers.admin import management

    calls = []
    monkeypatch.setattr(management, "service_exists", lambda service: False)
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management._run_service_restart("xray", "Xray", 123, 456)

    assert "⚠️ Xray не установлен." in calls[0]


def test_run_service_restart_success(monkeypatch):
    from handlers.admin import management

    calls = []
    monkeypatch.setattr(management, "service_exists", lambda service: True)
    monkeypatch.setattr(management, "restart_service", lambda service: None)
    monkeypatch.setattr(management, "log_action", lambda *args: None)
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management._run_service_restart("xray", "Xray", 123, 456)

    assert calls[0][1] == "⏳ Перезапуск Xray..."
    assert calls[-1][1] == "✅ Xray перезапущен!"


def test_run_service_restart_timeout(monkeypatch):
    import subprocess

    from handlers.admin import management

    calls = []
    monkeypatch.setattr(management, "service_exists", lambda service: True)

    def fail(service):
        raise subprocess.TimeoutExpired("systemctl", 60)

    monkeypatch.setattr(management, "restart_service", fail)
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management._run_service_restart("xray", "Xray", 123, 456)

    assert calls[-1][1] == "⚠️ Таймаут перезапуска Xray"


def test_run_service_restart_error(monkeypatch):
    from handlers.admin import management

    calls = []
    monkeypatch.setattr(management, "service_exists", lambda service: True)

    def fail(service):
        raise RuntimeError("boom")

    monkeypatch.setattr(management, "restart_service", fail)
    monkeypatch.setattr(management, "log_action", lambda *args: None)
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management._run_service_restart("xray", "Xray", 123, 456)

    assert "❌ Ошибка перезапуска Xray: boom" == calls[-1][1]


def test_run_speedtest_success(monkeypatch):
    from handlers.admin import management

    calls = []
    monkeypatch.setattr(
        management,
        "run_speedtest_and_ip",
        lambda: "Speedtest Result: 100 Mbps",
    )
    monkeypatch.setattr(management, "log_action", lambda *args: None)
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management._run_speedtest(123, 456)

    assert calls[-1][1] == "Speedtest Result: 100 Mbps"


def test_run_speedtest_error(monkeypatch):
    from handlers.admin import management

    calls = []
    monkeypatch.setattr(
        management,
        "run_speedtest_and_ip",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management._run_speedtest(123, 456)

    assert calls[-1][1] == "❌ Ошибка speedtest: boom"


def test_run_status_sends_and_schedules_delete(monkeypatch):
    from handlers.admin import management

    sent = []
    deleted = []
    scheduled = []

    class Message:
        message_id = 777

    management.LAST_STATUS_MSGS.clear()
    management.LAST_STATUS_MSGS[123] = 111

    monkeypatch.setattr(management, "get_status_text", lambda: "STATUS")
    monkeypatch.setattr(
        management.bot,
        "send_message",
        lambda *args, **kwargs: sent.append((args, kwargs)) or Message(),
    )
    monkeypatch.setattr(
        management,
        "safe_delete",
        lambda *args: deleted.append(args),
    )

    class FakeTimer:
        def __init__(self, *args, **kwargs):
            scheduled.append((args, kwargs))

        def start(self):
            pass

    monkeypatch.setattr(management.threading, "Timer", FakeTimer)

    management._run_status(123, 456)

    assert sent[0][0][1] == "STATUS"
    assert deleted[0] == (management.bot, 123, 111)
    assert deleted[-1] == (management.bot, 123, 456)
    assert management.LAST_STATUS_MSGS[123] == 777
    assert scheduled


def test_run_status_send_error(monkeypatch):
    from handlers.admin import management

    actions = []
    monkeypatch.setattr(management, "get_status_text", lambda: "STATUS")
    monkeypatch.setattr(
        management.bot,
        "send_message",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        management,
        "log_action",
        lambda *args: actions.append(args),
    )
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: None,
    )

    management.LAST_STATUS_MSGS.pop(123, None)

    management._run_status(123, 456)

    assert actions


def test_run_bot_stats_success(monkeypatch):
    from handlers.admin import management

    calls = []
    monkeypatch.setattr(management, "get_bot_stats_text", lambda: "STATS")
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management._run_bot_stats(123, 456)

    assert calls[-1][1] == "STATS"


def test_run_bot_stats_error(monkeypatch):
    from handlers.admin import management

    calls = []
    monkeypatch.setattr(
        management,
        "get_bot_stats_text",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management._run_bot_stats(123, 456)

    assert calls[-1][1] == "❌ Ошибка: boom"


def test_run_client_stats_error(monkeypatch):
    from handlers.admin import management

    actions = []
    calls = []
    monkeypatch.setattr(
        management,
        "get_client_stats_text",
        lambda username, proto: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        management,
        "log_action",
        lambda *args: actions.append(args),
    )
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management._run_client_stats(123, 456, "vless", "alice")

    assert actions
    assert calls[-1][1] == "❌ Ошибка получения статистики: boom"


def test_run_show_history_error(monkeypatch):
    from handlers.admin import management

    actions = []
    calls = []
    monkeypatch.setattr(
        management,
        "show_history_action",
        lambda *args: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        management,
        "log_action",
        lambda *args: actions.append(args),
    )
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management._run_show_history(123, 456)

    assert actions
    assert calls[-1][1] == "❌ Ошибка загрузки истории: boom"


def test_run_cleanup_success(monkeypatch):
    from handlers.admin import management

    calls = []
    monkeypatch.setattr(management, "run_disk_cleanup", lambda: "CLEANED")
    monkeypatch.setattr(management, "log_action", lambda *args: None)
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management._run_cleanup(123, 456)

    assert calls[-1][1] == "CLEANED"


def test_run_cleanup_error(monkeypatch):
    from handlers.admin import management

    actions = []
    calls = []
    monkeypatch.setattr(
        management,
        "run_disk_cleanup",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        management,
        "log_action",
        lambda *args: actions.append(args),
    )
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management._run_cleanup(123, 456)

    assert actions
    assert calls[-1][1] == "❌ Ошибка очистки: boom"


def test_ai_diagnosis_success(monkeypatch):
    from handlers.admin import management

    class Message:
        message_id = 456

    class Call:
        id = "call"
        message = Message()

    calls = []

    monkeypatch.setattr(
        management.bot,
        "answer_callback_query",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(management, "get_service_logs", lambda name: "LOGS")
    monkeypatch.setattr(
        management,
        "analyze_logs_with_llm",
        lambda logs, name: "RESULT",
    )
    monkeypatch.setattr(management, "ai_diagnosis_menu_kb", lambda: "KB")
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management.handle_ai_diagnosis_callback(
        management.bot,
        123,
        Call(),
        "ai_log_xray",
    )

    assert calls[-1][1] == "RESULT"


def test_ai_server_health_success(monkeypatch):
    from handlers.admin import management

    class Message:
        message_id = 456

    class Call:
        id = "call"
        message = Message()

    calls = []

    monkeypatch.setattr(
        management,
        "collect_server_health",
        lambda: "HEALTH",
    )
    monkeypatch.setattr(
        management,
        "analyze_logs_with_llm",
        lambda health, name: "SERVER RESULT",
    )
    monkeypatch.setattr(management, "ai_diagnosis_menu_kb", lambda: "KB")
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management.handle_ai_diagnosis_callback(
        management.bot,
        123,
        Call(),
        "ai_server_health",
    )

    assert calls[-1][1] == "SERVER RESULT"


def test_ai_server_health_error(monkeypatch):
    from handlers.admin import management

    class Message:
        message_id = 456

    class Call:
        id = "call"
        message = Message()

    calls = []

    monkeypatch.setattr(
        management,
        "collect_server_health",
        lambda: (_ for _ in ()).throw(RuntimeError("health failed")),
    )
    monkeypatch.setattr(management, "ai_diagnosis_menu_kb", lambda: "KB")
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management.handle_ai_diagnosis_callback(
        management.bot,
        123,
        Call(),
        "ai_server_health",
    )

    assert calls[-1][1] == "❌ Ошибка анализа сервера: health failed"


def test_ai_diagnosis_error(monkeypatch):
    from handlers.admin import management

    class Message:
        message_id = 456

    class Call:
        id = "call"
        message = Message()

    calls = []

    monkeypatch.setattr(
        management.bot,
        "answer_callback_query",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        management,
        "get_service_logs",
        lambda name: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(management, "ai_diagnosis_menu_kb", lambda: "KB")
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management.handle_ai_diagnosis_callback(
        management.bot,
        123,
        Call(),
        "ai_log_xray",
    )

    assert calls[-1][1] == "❌ Ошибка диагностики: boom"


def test_run_manual_backup_success(monkeypatch):
    from handlers.admin import management

    calls = []

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    class Result:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(management.threading, "Thread", FakeThread)
    monkeypatch.setattr(
        management.subprocess,
        "run",
        lambda *args, **kwargs: Result(),
    )

    class FakeFile:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return ""

    import builtins

    def fake_open(*args, **kwargs):
        return FakeFile()

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(
        management.json,
        "load",
        lambda f: {
            "file_name": "backup.tar.gz",
            "size_mb": 12,
            "last_backup": "2026-08-21T18:00:00",
        },
    )
    monkeypatch.setattr(
        management,
        "format_msk_time",
        lambda value: "21.08.2026 21:00",
    )
    monkeypatch.setattr(management, "log_action", lambda *args: None)
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management.run_manual_backup(management.bot, 123, 456)

    assert calls
    assert "Бэкап создан успешно!" in calls[-1][1]
    assert "backup.tar.gz" in calls[-1][1]


def test_run_manual_backup_rclone_missing(monkeypatch):
    from handlers.admin import management

    calls = []
    actions = []

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    class Result:
        returncode = 127
        stderr = "rclone: command not found"

    monkeypatch.setattr(management.threading, "Thread", FakeThread)
    monkeypatch.setattr(
        management.subprocess,
        "run",
        lambda *args, **kwargs: Result(),
    )

    import builtins

    class FakeFile:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(builtins, "open", lambda *args, **kwargs: FakeFile())
    monkeypatch.setattr(
        management.json,
        "load",
        lambda f: {
            "file_name": "backup.tar.gz",
            "size_mb": 12,
            "last_backup": "",
        },
    )
    monkeypatch.setattr(management, "format_msk_time", lambda value: "")
    monkeypatch.setattr(
        management,
        "log_action",
        lambda *args: actions.append(args),
    )
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management.run_manual_backup(management.bot, 123, 456)

    assert "Бэкап создан локально" in calls[-1][1]
    assert "rclone не установлен" in calls[-1][1]
    assert actions[-1][2] == "WARNING"


def test_run_manual_backup_cloud_token_missing(monkeypatch):
    from handlers.admin import management

    calls = []
    actions = []

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    class Result:
        returncode = 2
        stderr = "cloud token missing"

    monkeypatch.setattr(management.threading, "Thread", FakeThread)
    monkeypatch.setattr(
        management.subprocess,
        "run",
        lambda *args, **kwargs: Result(),
    )

    import builtins

    class FakeFile:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(builtins, "open", lambda *args, **kwargs: FakeFile())
    monkeypatch.setattr(
        management.json,
        "load",
        lambda f: {
            "file_name": "backup.tar.gz",
            "size_mb": 12,
            "last_backup": "",
        },
    )
    monkeypatch.setattr(
        management,
        "log_action",
        lambda *args: actions.append(args),
    )
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management.run_manual_backup(management.bot, 123, 456)

    assert "Бэкап создан только локально" in calls[-1][1]
    assert actions[-1][2] == "WARNING"


def test_run_manual_backup_local_only_status_overrides_returncode(monkeypatch):
    from handlers.admin import management

    calls = []
    actions = []

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    class Result:
        returncode = 1
        stderr = "upload failed"

    class FakeFile:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(management.threading, "Thread", FakeThread)
    monkeypatch.setattr(
        management.subprocess,
        "run",
        lambda *args, **kwargs: Result(),
    )
    monkeypatch.setattr(
        __import__("builtins"),
        "open",
        lambda *args, **kwargs: FakeFile(),
    )
    monkeypatch.setattr(
        management.json,
        "load",
        lambda f: {
            "status": "local_only",
            "file_name": "backup.tar.gz",
            "size_mb": 12,
            "last_backup": "",
            "error": "Yandex Disk token is missing",
        },
    )
    monkeypatch.setattr(
        management,
        "log_action",
        lambda *args: actions.append(args),
    )
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management.run_manual_backup(management.bot, 123, 456)

    text = calls[-1][1]

    assert "Бэкап создан локально" in text
    assert "Backup remote не настроен" in text
    assert "Бэкап сохранён только на сервере" in text
    assert "Код возврата: 1" not in text
    assert actions[-1][2] == "WARNING"
    assert actions[-1][3] == "Backup remote не настроен"


def test_run_manual_backup_timeout(monkeypatch):
    import subprocess

    from handlers.admin import management

    calls = []

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("bash", 300)

    monkeypatch.setattr(management.threading, "Thread", FakeThread)
    monkeypatch.setattr(management.subprocess, "run", fail)
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management.run_manual_backup(management.bot, 123, 456)

    assert "Таймаут бэкапа" in calls[-1][1]


def test_run_manual_backup_warning_unknown_error(monkeypatch):
    from handlers.admin import management

    calls = []

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    class Result:
        returncode = 1
        stderr = "unknown error"

    class FakeFile:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(management.threading, "Thread", FakeThread)
    monkeypatch.setattr(
        management.subprocess,
        "run",
        lambda *args, **kwargs: Result(),
    )

    import builtins

    monkeypatch.setattr(
        builtins,
        "open",
        lambda *args, **kwargs: FakeFile(),
    )
    monkeypatch.setattr(
        management.json,
        "load",
        lambda f: {
            "file_name": "backup.tar.gz",
            "size_mb": 12,
            "last_backup": "",
        },
    )
    monkeypatch.setattr(management, "log_action", lambda *args: None)
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management.run_manual_backup(management.bot, 123, 456)

    assert "Бэкап создан с предупреждениями" in calls[-1][1]
    assert "Код возврата: 1" in calls[-1][1]


def test_run_manual_backup_status_read_error_after_failed_backup(monkeypatch):
    from handlers.admin import management

    calls = []

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    class Result:
        returncode = 1
        stderr = "failed backup"

    monkeypatch.setattr(management.threading, "Thread", FakeThread)
    monkeypatch.setattr(
        management.subprocess,
        "run",
        lambda *args, **kwargs: Result(),
    )

    import builtins

    def fail_open(*args, **kwargs):
        raise OSError("status read failed")

    monkeypatch.setattr(builtins, "open", fail_open)
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management.run_manual_backup(management.bot, 123, 456)

    assert "Ошибка бэкапа" in calls[-1][1]
    assert "Код: 1" in calls[-1][1]
    assert "failed backup" in calls[-1][1]


def test_run_manual_backup_outer_error(monkeypatch):
    from handlers.admin import management

    calls = []

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(management.threading, "Thread", FakeThread)
    monkeypatch.setattr(management.subprocess, "run", fail)
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management.run_manual_backup(management.bot, 123, 456)

    assert "Ошибка бэкапа" in calls[-1][1]
    assert "boom" in calls[-1][1]


def test_run_manual_backup_success_status_read_error(monkeypatch):
    from handlers.admin import management

    calls = []

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    class Result:
        returncode = 0
        stderr = ""

    def fail_open(*args, **kwargs):
        raise OSError("status read failed")

    monkeypatch.setattr(management.threading, "Thread", FakeThread)
    monkeypatch.setattr(
        management.subprocess,
        "run",
        lambda *args, **kwargs: Result(),
    )

    import builtins

    monkeypatch.setattr(builtins, "open", fail_open)
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management.run_manual_backup(management.bot, 123, 456)

    assert "Бэкап создан успешно!" in calls[-1][1]
    assert "Не удалось прочитать статус" in calls[-1][1]


def test_run_status_outer_error(monkeypatch):
    from handlers.admin import management

    calls = []

    monkeypatch.setattr(management, "get_status_text", lambda: "STATUS")
    monkeypatch.setattr(
        management.bot,
        "send_message",
        lambda *args, **kwargs: type("Message", (), {"message_id": 777})(),
    )
    monkeypatch.setattr(
        management,
        "safe_delete",
        lambda *args: (_ for _ in ()).throw(RuntimeError("delete failed")),
    )
    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    management._run_status(123, 456)

    assert calls[-1][1] == "❌ Ошибка статуса: delete failed"


def test_run_weekly_report_escapes_client_name(monkeypatch):
    from handlers.admin import management

    calls = []

    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    class ExistingPath:
        def exists(self):
            return True

    monkeypatch.setattr("config.paths.USAGE_JSON", ExistingPath())
    monkeypatch.setattr(
        management,
        "load_usage",
        lambda: {
            "updated": "2026-08-25T12:00:00",
            "clients": {
                "user_test": {
                    "total": 123,
                    "uplink": 45,
                    "downlink": 78,
                }
            },
        },
    )

    management._run_weekly_report(123, 456)

    text = calls[-1][0][1]
    assert "*user\\_test*" in text


def test_run_weekly_report_usage_file_missing(monkeypatch):
    from handlers.admin import management

    calls = []

    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    class MissingPath:
        def exists(self):
            return False

    monkeypatch.setattr("config.paths.USAGE_JSON", MissingPath())

    management._run_weekly_report(123, 456)

    assert calls[-1][1] == "❌ Файл статистики usage.json не найден."


def test_run_weekly_report_without_clients(monkeypatch):
    from handlers.admin import management

    calls = []

    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    class ExistingPath:
        def exists(self):
            return True

    monkeypatch.setattr("config.paths.USAGE_JSON", ExistingPath())
    monkeypatch.setattr(management, "load_usage", lambda: {"clients": {}})

    management._run_weekly_report(123, 456)

    assert calls[-1][1] == "📊 Клиентов для отчёта пока нет."


def test_run_weekly_report_error(monkeypatch):
    from handlers.admin import management

    calls = []

    monkeypatch.setattr(
        management,
        "safe_edit_message",
        lambda *args, **kwargs: calls.append(args),
    )

    class ExistingPath:
        def exists(self):
            return True

    monkeypatch.setattr("config.paths.USAGE_JSON", ExistingPath())
    monkeypatch.setattr(
        management,
        "load_usage",
        lambda: (_ for _ in ()).throw(RuntimeError("usage failed")),
    )

    management._run_weekly_report(123, 456)

    assert calls[-1][1] == "❌ Ошибка формирования отчёта: usage failed"


def test_close_log_delete_error(mock_bot, mock_call):
    from handlers.admin.management import handle_management_part2_callback

    with (
        patch(
            "handlers.admin.management.safe_delete",
            side_effect=RuntimeError("delete failed"),
        ),
        patch("handlers.admin.management.logger.exception") as mock_logger,
    ):
        result = handle_management_part2_callback(
            mock_bot,
            111222,
            mock_call,
            "close_log",
        )

    assert result.text is None
    assert result.show_alert is False
    mock_logger.assert_called_once()


def test_render_backup_history_exception_returns_false(mock_bot):
    with (
        patch(
            "handlers.admin.management.get_backup_history_text",
            side_effect=RuntimeError("history failed"),
        ),
        patch("handlers.admin.management.log_action") as mock_log,
    ):
        result = render_backup_history(mock_bot, 123, 456)

    assert result is False
    mock_log.assert_called_once_with(
        "ОШИБКА ИСТОРИИ БЭКАПОВ",
        "backup_history",
        "ERROR",
        "history failed",
    )


def test_render_backup_history_success(mock_bot):
    with (
        patch(
            "handlers.admin.management.get_backup_history_text",
            return_value="📜 История бэкапов",
        ),
        patch("handlers.admin.management.safe_edit_message") as mock_edit,
    ):
        result = render_backup_history(mock_bot, 123, 456)

    assert result is True
    mock_edit.assert_called_once()

    args, kwargs = mock_edit.call_args
    assert args[:4] == (
        mock_bot,
        "📜 История бэкапов",
        123,
        456,
    )
    assert kwargs["parse_mode"] == "Markdown"
