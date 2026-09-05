from pathlib import Path
from unittest.mock import patch

import core.callback_checker as checker
from core.callback_router import CallbackAccess, CallbackRoute


class TestNormalizeDynamicCallback:
    def test_dynamic_callback_returns_prefix(self):
        assert checker.normalize_dynamic_callback("qr_{proto}_{username}") == "qr_"

    def test_static_callback_unchanged(self):
        assert checker.normalize_dynamic_callback("nav:back") == "nav:back"


class TestHasPrefixHandler:
    def test_registered_prefix_matches_callback_prefix(self):
        route = CallbackRoute(
            "qr_",
            lambda: None,
            CallbackAccess.ADMIN,
            prefix=True,
        )

        with patch.object(checker, "CALLBACK_ROUTES", (route,)):
            assert checker.has_prefix_handler("qr_") is True

    def test_callback_prefix_does_not_match_registered_longer_prefix(self):
        route = CallbackRoute(
            "stats_client_",
            lambda: None,
            CallbackAccess.ADMIN,
            prefix=True,
        )

        with patch.object(checker, "CALLBACK_ROUTES", (route,)):
            assert checker.has_prefix_handler("stats_") is False

    def test_unknown_prefix_returns_false(self):
        route = CallbackRoute(
            "qr_",
            lambda: None,
            CallbackAccess.ADMIN,
            prefix=True,
        )

        with patch.object(checker, "CALLBACK_ROUTES", (route,)):
            assert checker.has_prefix_handler("unknown_") is False


class TestExtractCallbacks:
    def test_extracts_static_and_dynamic_callbacks(self, tmp_path):
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()

        (ui_dir / "test_ui.py").write_text(
            """
button1 = InlineKeyboardButton(
    text="Back",
    callback_data="nav:back",
)

button2 = InlineKeyboardButton(
    text="QR",
    callback_data=f"qr_{proto}_{username}",
)

button3 = InlineKeyboardButton(
    text="Stats",
    callback_data=f"stats_{proto}_{username}",
)
""",
            encoding="utf-8",
        )

        with patch.object(checker, "BASE_DIR", tmp_path):
            callbacks = checker.extract_callbacks()

        assert callbacks == {
            "nav:back",
            "qr_{proto}_{username}",
            "stats_{proto}_{username}",
        }

    def test_extracts_callback_prefix_constants_from_fstrings(self, tmp_path):
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()

        (ui_dir / "test_ui.py").write_text(
            """
from core.navigation import (
    CLIENT_CONF_CALLBACK_PREFIX,
    CLIENT_CONF_RU_CALLBACK_PREFIX,
)

button1 = InlineKeyboardButton(
    text="CONF",
    callback_data=f"{CLIENT_CONF_CALLBACK_PREFIX}{username}",
)

button2 = InlineKeyboardButton(
    text="CONF RU",
    callback_data=f"{CLIENT_CONF_RU_CALLBACK_PREFIX}{username}",
)
""",
            encoding="utf-8",
        )

        with patch.object(checker, "BASE_DIR", tmp_path):
            callbacks = checker.extract_callbacks()

        assert callbacks == {
            "client:conf:{username}",
            "client:conf_ru:{username}",
        }

    def test_read_error_does_not_abort_scan(self, tmp_path):
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()

        bad_file = ui_dir / "bad.py"
        good_file = ui_dir / "good.py"

        bad_file.write_text(
            'callback_data="back_bad"',
            encoding="utf-8",
        )
        good_file.write_text(
            'callback_data="back_good"',
            encoding="utf-8",
        )

        original_read_text = Path.read_text

        def fake_read_text(path, *args, **kwargs):
            if path == bad_file:
                raise OSError("read failed")
            return original_read_text(path, *args, **kwargs)

        with (
            patch.object(Path, "read_text", fake_read_text),
            patch.object(checker, "BASE_DIR", tmp_path),
        ):
            callbacks = checker.extract_callbacks()

        assert callbacks == {"back_good"}


class TestCheckCallbacks:
    def test_all_callbacks_valid(self):
        callbacks = {
            "nav:back",
            "qr_{proto}_{username}",
        }

        with (
            patch.object(checker, "extract_callbacks", return_value=callbacks),
            patch.object(checker, "resolve", return_value=object()),
            patch.object(checker, "has_prefix_handler", return_value=True),
        ):
            assert checker.check_callbacks() is True

    def test_unknown_static_callback_returns_false(self):
        with (
            patch.object(
                checker,
                "extract_callbacks",
                return_value={"unknown_callback"},
            ),
            patch.object(checker, "resolve", return_value=None),
        ):
            assert checker.check_callbacks() is False

    def test_unknown_dynamic_callback_returns_false(self):
        with (
            patch.object(
                checker,
                "extract_callbacks",
                return_value={"unknown_{value}"},
            ),
            patch.object(checker, "has_prefix_handler", return_value=False),
        ):
            assert checker.check_callbacks() is False

    def test_mixed_valid_and_invalid_callbacks_returns_false(self):
        callbacks = {
            "unknown_callback",
            "qr_{proto}_{username}",
        }

        def fake_get_handler(value):
            if value == "nav:back":
                return object()
            return None

        with (
            patch.object(checker, "extract_callbacks", return_value=callbacks),
            patch.object(checker, "resolve", side_effect=fake_get_handler),
            patch.object(checker, "has_prefix_handler", return_value=True),
        ):
            assert checker.check_callbacks() is False

    def test_empty_callbacks_are_valid(self):
        with patch.object(checker, "extract_callbacks", return_value=set()):
            assert checker.check_callbacks() is True


def test_colon_dynamic_callback_keeps_colon_prefix():
    assert checker.normalize_dynamic_callback("qr:{proto}:{username}") == "qr:"
    assert checker.normalize_dynamic_callback("conf:{proto}:{username}") == "conf:"
    assert checker.normalize_dynamic_callback("ask_del:{proto}:{u}") == "ask_del:"
    assert (
        checker.normalize_dynamic_callback("confirm_del:{proto}:{username}")
        == "confirm_del:"
    )


def test_star_prefixes_are_resolved():
    with patch.object(
        checker,
        "CALLBACK_ROUTES",
        tuple(
            CallbackRoute(
                pattern,
                lambda: None,
                CallbackAccess.ADMIN,
                prefix=True,
            )
            for pattern in ("qr:", "conf:", "ask_del:", "confirm_del:")
        ),
    ):
        assert checker.has_prefix_handler("qr:")
        assert checker.has_prefix_handler("conf:")
        assert checker.has_prefix_handler("ask_del:")
        assert checker.has_prefix_handler("confirm_del:")


def test_star_prefixes_do_not_match_shortened_prefixes():
    with patch.object(
        checker,
        "CALLBACK_ROUTES",
        tuple(
            CallbackRoute(
                pattern,
                lambda: None,
                CallbackAccess.ADMIN,
                prefix=True,
            )
            for pattern in ("qr:", "conf:", "ask_del:", "confirm_del:")
        ),
    ):
        assert not checker.has_prefix_handler("qr")
        assert not checker.has_prefix_handler("conf")
        assert not checker.has_prefix_handler("ask_del")
        assert not checker.has_prefix_handler("confirm_del")


def test_main_exits_successfully_when_callbacks_pass():
    with patch.object(checker, "check_callbacks", return_value=True):
        try:
            checker.main()
        except SystemExit as exc:
            assert exc.code == 0
        else:
            raise AssertionError("Expected SystemExit")


def test_main_exits_with_error_when_callbacks_fail():
    with patch.object(checker, "check_callbacks", return_value=False):
        try:
            checker.main()
        except SystemExit as exc:
            assert exc.code == 1
        else:
            raise AssertionError("Expected SystemExit")


def test_main_success(monkeypatch):
    from core import callback_checker

    monkeypatch.setattr(callback_checker, "check_callbacks", lambda: True)

    try:
        callback_checker.main()
    except SystemExit as exc:
        assert exc.code == 0


def test_main_failure(monkeypatch):
    from core import callback_checker

    monkeypatch.setattr(callback_checker, "check_callbacks", lambda: False)

    try:
        callback_checker.main()
    except SystemExit as exc:
        assert exc.code == 1
