"""
Тесты handlers/features/passport_check.py.
Проверяют все основные callback-ветки и обработку ошибок.
"""

from unittest.mock import Mock, patch

import pytest

from handlers.features.passport_check import (
    handle_passport_check,
    strip_ansi,
)


@pytest.fixture
def mock_bot():
    bot = Mock()
    bot.answer_callback_query = Mock()
    bot.edit_message_text = Mock()
    bot.send_document = Mock()
    return bot


@pytest.fixture
def mock_call():
    call = Mock()
    call.id = "callback-123"
    call.message = Mock()
    call.message.message_id = 67890
    return call


class TestStripAnsi:
    def test_removes_ansi_escape_codes(self):
        text = "\x1b[31mERROR\x1b[0m\n\x1b[32mOK\x1b[0m"

        assert strip_ansi(text) == "ERROR\nOK"

    def test_returns_plain_text_unchanged(self):
        text = "Обычный текст без ANSI"

        assert strip_ansi(text) == text


class TestPassportCheck:
    def test_success_creates_report_and_summary(
        self,
        mock_bot,
        mock_call,
        tmp_path,
    ):
        output = (
            "\x1b[32mВсего проверок: 10\x1b[0m\n"
            "Успешно: 8\n"
            "Предупреждений: 1\n"
            "Ошибок: 1\n"
            "лишняя техническая строка\n"
            "❌ СЕРВЕР НЕ ГОТОВ\n"
        )

        mock_result = Mock()
        mock_result.stdout = output
        mock_result.stderr = ""

        with (
            patch(
                "handlers.features.passport_check.subprocess.run",
                return_value=mock_result,
            ) as mock_run,
            patch(
                "handlers.features.passport_check.REPORT_DIR",
                str(tmp_path),
            ),
            patch(
                "handlers.features.passport_check.time.time",
                return_value=1234567890,
            ),
        ):
            result = handle_passport_check(
                mock_bot,
                111222,
                mock_call,
                "passport_check",
            )

        assert result.show_alert is False
        assert result.text == "Проверяю паспорт сервера..."

        mock_run.assert_called_once_with(
            [
                str(
                    __import__("config.paths", fromlist=["PROJECT_ROOT"]).PROJECT_ROOT
                    / ".venv"
                    / "bin"
                    / "python"
                ),
                str(
                    __import__("config.paths", fromlist=["PROJECT_ROOT"]).PROJECT_ROOT
                    / "scripts"
                    / "check_passport.py"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(
                __import__("config.paths", fromlist=["PROJECT_ROOT"]).PROJECT_ROOT
                / "scripts"
            ),
        )

        mock_bot.edit_message_text.assert_called_once()

        text = mock_bot.edit_message_text.call_args.args[0]

        assert "🛡 ПАСПОРТ СЕРВЕРА" in text
        assert "Всего проверок: 10" in text
        assert "Успешно: 8" in text
        assert "Предупреждений: 1" in text
        assert "Ошибок: 1" in text
        assert "❌ СЕРВЕР НЕ ГОТОВ" in text
        assert "лишняя техническая строка" not in text

        report = tmp_path / "passport_111222_1234567890.txt"

        assert report.exists()
        assert report.read_text(encoding="utf-8") == (
            "Всего проверок: 10\n"
            "Успешно: 8\n"
            "Предупреждений: 1\n"
            "Ошибок: 1\n"
            "лишняя техническая строка\n"
            "❌ СЕРВЕР НЕ ГОТОВ\n"
        )

        keyboard = mock_bot.edit_message_text.call_args.kwargs["reply_markup"]
        assert keyboard is not None

    def test_success_without_key_lines_uses_fallback_summary(
        self,
        mock_bot,
        mock_call,
        tmp_path,
    ):
        mock_result = Mock()
        mock_result.stdout = "nothing useful here"
        mock_result.stderr = ""

        with (
            patch(
                "handlers.features.passport_check.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                "handlers.features.passport_check.REPORT_DIR",
                str(tmp_path),
            ),
            patch(
                "handlers.features.passport_check.time.time",
                return_value=123,
            ),
        ):
            result = handle_passport_check(
                mock_bot,
                111222,
                mock_call,
                "passport_check",
            )

        assert result.show_alert is False
        assert result.text == "Проверяю паспорт сервера..."

        text = mock_bot.edit_message_text.call_args.args[0]

        assert "Не удалось сформировать краткий итог." in text

    def test_timeout(
        self,
        mock_bot,
        mock_call,
    ):
        with patch(
            "handlers.features.passport_check.subprocess.run",
            side_effect=__import__("subprocess").TimeoutExpired(
                cmd=["python3"],
                timeout=30,
            ),
        ):
            result = handle_passport_check(
                mock_bot,
                111222,
                mock_call,
                "passport_check",
            )

        assert result.show_alert is False
        assert result.text == "Проверяю паспорт сервера..."

        mock_bot.edit_message_text.assert_called_once_with(
            "⏱ Превышено время ожидания проверки (30с).",
            111222,
            67890,
        )

    def test_generic_error(
        self,
        mock_bot,
        mock_call,
    ):
        with patch(
            "handlers.features.passport_check.subprocess.run",
            side_effect=RuntimeError("boom"),
        ):
            result = handle_passport_check(
                mock_bot,
                111222,
                mock_call,
                "passport_check",
            )

        assert result.show_alert is False
        assert result.text == "Проверяю паспорт сервера..."

        text = mock_bot.edit_message_text.call_args.args[0]

        assert "❌ Ошибка при проверке: boom" in text

    def test_send_existing_report(
        self,
        mock_bot,
        mock_call,
        tmp_path,
    ):
        report = tmp_path / "passport_111222_123.txt"
        report.write_text("full report", encoding="utf-8")

        with patch(
            "handlers.features.passport_check.REPORT_DIR",
            str(tmp_path),
        ):
            result = handle_passport_check(
                mock_bot,
                111222,
                mock_call,
                "get_passport_file:passport_111222_123.txt",
            )

        assert result.show_alert is False
        assert result.text == "Отчёт отправлен в чат!"

        mock_bot.send_document.assert_called_once()

        sent_cid, file_object = mock_bot.send_document.call_args.args

        assert sent_cid == 111222
        assert file_object.name == str(report)
        assert file_object.closed is True

        mock_bot.answer_callback_query.assert_not_called()

    def test_send_report_error(
        self,
        mock_bot,
        mock_call,
        tmp_path,
    ):
        report = tmp_path / "passport_111222_123.txt"
        report.write_text("full report", encoding="utf-8")

        mock_bot.send_document.side_effect = RuntimeError("telegram error")

        with patch(
            "handlers.features.passport_check.REPORT_DIR",
            str(tmp_path),
        ):
            result = handle_passport_check(
                mock_bot,
                111222,
                mock_call,
                "get_passport_file:passport_111222_123.txt",
            )

        assert result.show_alert is True
        assert result.text == "Ошибка отправки файла"

    def test_missing_report(
        self,
        mock_bot,
        mock_call,
        tmp_path,
    ):
        with patch(
            "handlers.features.passport_check.REPORT_DIR",
            str(tmp_path),
        ):
            result = handle_passport_check(
                mock_bot,
                111222,
                mock_call,
                "get_passport_file:missing.txt",
            )

        assert result.show_alert is True
        assert result.text == "Файл не найден или устарел"

        mock_bot.send_document.assert_not_called()

    def test_unknown_callback_returns_false(
        self,
        mock_bot,
        mock_call,
    ):
        result = handle_passport_check(
            mock_bot,
            111222,
            mock_call,
            "something_else",
        )

        assert result is False
