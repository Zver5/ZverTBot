"""
Тесты utils/notifications.py.
Проверяют логирование действий, обновление статистики
и обработку ошибок.
"""

from unittest.mock import patch

from utils.notifications import log_action


class TestLogAction:
    """Тесты log_action."""

    def test_adds_entry_and_saves_history(self):
        history = []

        with (
            patch(
                "utils.notifications.load_history",
                return_value=history,
            ),
            patch(
                "utils.notifications.save_history",
            ) as mock_save,
        ):
            log_action(
                "СОЗДАНИЕ",
                "client_01",
                "SUCCESS",
                "Protocol: vless",
            )

        mock_save.assert_called_once()

        saved_history = mock_save.call_args.args[0]

        assert len(saved_history) == 1

        entry = saved_history[0]
        assert entry["action"] == "СОЗДАНИЕ"
        assert entry["target"] == "client_01"
        assert entry["status"] == "SUCCESS"
        assert entry["details"] == "Protocol: vless"

        assert entry["time"]

    def test_keeps_only_last_100_entries(self):
        history = [
            {
                "time": "01.01 00:00",
                "action": "OLD",
                "target": str(index),
                "status": "SUCCESS",
                "details": "",
            }
            for index in range(100)
        ]

        with (
            patch(
                "utils.notifications.load_history",
                return_value=history,
            ),
            patch(
                "utils.notifications.save_history",
            ) as mock_save,
        ):
            log_action(
                "NEW",
                "new_target",
                "SUCCESS",
            )

        saved_history = mock_save.call_args.args[0]

        assert len(saved_history) == 100
        assert saved_history[-1]["action"] == "NEW"
        assert saved_history[-1]["target"] == "new_target"
        assert saved_history[0]["target"] == "1"

    def test_logs_error_when_load_history_fails(self):
        with (
            patch(
                "utils.notifications.load_history",
                side_effect=RuntimeError("load failed"),
            ),
            patch(
                "utils.notifications.logger.error",
            ) as mock_error,
        ):
            log_action(
                "TEST",
                "target",
                "ERROR",
            )

        mock_error.assert_called_once()
        assert mock_error.call_args.args[0] == (
            "notifications.action_log.failed | error=%s"
        )
        assert isinstance(mock_error.call_args.args[1], RuntimeError)
        assert str(mock_error.call_args.args[1]) == "load failed"

    def test_logs_error_when_save_history_fails(self):
        with (
            patch(
                "utils.notifications.load_history",
                return_value=[],
            ),
            patch(
                "utils.notifications.save_history",
                side_effect=RuntimeError("save failed"),
            ),
            patch(
                "utils.notifications.logger.error",
            ) as mock_error,
        ):
            log_action(
                "TEST",
                "target",
                "ERROR",
            )

        mock_error.assert_called_once()
        assert mock_error.call_args.args[0] == (
            "notifications.action_log.failed | error=%s"
        )
        assert isinstance(mock_error.call_args.args[1], RuntimeError)
        assert str(mock_error.call_args.args[1]) == "save failed"
