"""
Тесты базовой архитектуры логирования.
"""

import logging

from utils.logger import EnvironmentFilter, ZverTBotFormatter


def test_environment_filter_sets_environment(monkeypatch):
    monkeypatch.setenv("ZVERTBOT_ENV", "BOT")

    record = logging.LogRecord(
        name="test.module",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="test message",
        args=(),
        exc_info=None,
    )

    EnvironmentFilter().filter(record)

    assert record.environment == "BOT"


def test_environment_filter_does_not_modify_message(monkeypatch):
    monkeypatch.setenv("ZVERTBOT_ENV", "TEST")

    record = logging.LogRecord(
        name="test.module",
        level=logging.INFO,
        pathname=__file__,
        lineno=20,
        msg="обычное сообщение",
        args=(),
        exc_info=None,
    )

    EnvironmentFilter().filter(record)

    assert record.msg == "обычное сообщение"
    assert record.environment == "TEST"


def test_formatter_contains_environment_module_function_and_line():
    record = logging.LogRecord(
        name="handlers.features.processes",
        level=logging.ERROR,
        pathname="/tmp/processes.py",
        lineno=42,
        msg="Ошибка обработки",
        args=(),
        exc_info=None,
        func="handle_processes_callback",
    )
    record.environment = "BOT"

    formatter = ZverTBotFormatter()

    output = formatter.format(record)

    assert "ERROR    | BOT  | " in output
    assert "handlers.features.processes:handle_processes_callback:42" in output
    assert "Ошибка обработки" in output


def test_formatter_uses_milliseconds_and_fixed_fields():
    record = logging.LogRecord(
        name="services.backup",
        level=logging.INFO,
        pathname="/tmp/backup.py",
        lineno=12,
        msg="backup.completed",
        args=(),
        exc_info=None,
        func="run_backup",
    )
    record.environment = "BOT"
    record.created = 1_700_000_000
    record.msecs = 123

    output = ZverTBotFormatter().format(record)

    assert ".123 | INFO     | BOT  | " in output
    assert "services.backup:run_backup:12 | backup.completed" in output
