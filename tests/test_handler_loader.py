import ast
from pathlib import Path

from core.handler_loader import HANDLER_MODULES

ROOT = Path(__file__).resolve().parents[1]
HANDLERS_DIR = ROOT / "handlers"


def _module_name(path):
    relative = path.relative_to(ROOT).with_suffix("")
    return ".".join(relative.parts)


def _has_telegram_handler_decorator(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func

        if not isinstance(func, ast.Attribute):
            continue

        if func.attr not in {
            "message_handler",
            "callback_query_handler",
            "inline_handler",
            "channel_post_handler",
            "edited_message_handler",
        }:
            continue

        if isinstance(func.value, ast.Name) and func.value.id == "bot":
            return True

    return False


def test_all_telegram_handler_modules_are_loaded():
    """Каждый модуль с Telegram-декоратором должен быть в HANDLER_MODULES."""

    discovered = {
        _module_name(path)
        for path in HANDLERS_DIR.rglob("*.py")
        if path.name != "__init__.py"
        and "__pycache__" not in path.parts
        and _has_telegram_handler_decorator(path)
    }

    configured = set(HANDLER_MODULES)

    assert discovered == configured


def test_load_handler_modules_imports_all_configured_modules():
    from unittest.mock import patch

    from core.handler_loader import load_handler_modules

    with patch("core.handler_loader.import_module") as mock_import:
        load_handler_modules()

    assert mock_import.call_count == len(HANDLER_MODULES)
    mock_import.assert_has_calls([((module_name,),) for module_name in HANDLER_MODULES])
