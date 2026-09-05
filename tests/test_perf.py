from unittest.mock import patch

from utils.perf import profile


def test_profile_logs_info_at_threshold():
    with (
        patch("utils.perf.time.perf_counter", side_effect=[0.0, 0.050]),
        patch("utils.perf.logger.info") as log_info,
        patch("utils.perf.logger.warning") as log_warning,
    ):

        @profile(threshold=50)
        def work():
            return "ok"

        assert work() == "ok"
        log_info.assert_called_once()
        log_warning.assert_not_called()


def test_profile_logs_warning_at_300ms():
    with (
        patch("utils.perf.time.perf_counter", side_effect=[0.0, 0.300]),
        patch("utils.perf.logger.info") as log_info,
        patch("utils.perf.logger.warning") as log_warning,
    ):

        @profile(threshold=50)
        def work():
            return "ok"

        assert work() == "ok"
        log_warning.assert_called_once()
        assert log_warning.call_args.args[0] == (
            "perf.measure.warning | name=%s | elapsed_ms=%.1f"
        )
        assert log_warning.call_args.args[2] == 300.0
        log_info.assert_not_called()


def test_profile_logs_warning_at_1000ms():
    with (
        patch("utils.perf.time.perf_counter", side_effect=[0.0, 1.000]),
        patch("utils.perf.logger.info") as log_info,
        patch("utils.perf.logger.warning") as log_warning,
    ):

        @profile(threshold=50)
        def work():
            return "ok"

        assert work() == "ok"
        log_warning.assert_called_once()
        assert log_warning.call_args.args[0] == (
            "perf.measure.slow | name=%s | elapsed_ms=%.1f"
        )
        assert log_warning.call_args.args[2] == 1000.0
        log_info.assert_not_called()
