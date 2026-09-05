import re
from pathlib import Path

from core.callback_router import all_callbacks, all_prefixes, get

ROOT = Path(__file__).resolve().parents[1]
KEYBOARDS = ROOT / "ui" / "keyboards.py"


def read(path):
    return path.read_text(encoding="utf-8")


def keyboard_callbacks():
    text = read(KEYBOARDS)

    return re.findall(
        r"""callback_data\s*=\s*["']([^"']+)["']""",
        text,
    )


def test_keyboard_callbacks_have_route():
    buttons = set(keyboard_callbacks())

    exact_routes = set(all_callbacks())
    prefix_routes = tuple(all_prefixes())

    missing = []

    for cb in buttons:
        # Динамические callback проверяются по префиксам.
        if (
            cb.endswith("_")
            or "{" in cb
            or cb.startswith(
                (
                    "qr_",
                    "conf_",
                    "del_",
                    "stats_",
                )
            )
        ):
            continue

        # Точный callback.
        if cb in exact_routes:
            continue

        # Проверка через новый router.
        if get(cb) is not None:
            continue

        # Проверка зарегистрированного prefix.
        if any(
            cb.startswith(prefix) or prefix.startswith(cb) for prefix in prefix_routes
        ):
            continue

        missing.append(cb)

    assert not missing, f"No handler route for callbacks: {missing}"


def test_no_duplicate_callbacks_inside_same_keyboard():
    text = read(KEYBOARDS)

    duplicates = []

    # Проверяем только отдельные вызовы kb.add(...).
    blocks = re.findall(
        r"""\.add\((.*?)\)""",
        text,
        re.DOTALL,
    )

    for block in blocks:
        callbacks = re.findall(
            r"""callback_data\s*=\s*["']([^"']+)["']""",
            block,
        )

        seen = set()

        for cb in callbacks:
            if cb in seen:
                duplicates.append(cb)

            seen.add(cb)

    assert not duplicates, f"Duplicate callbacks inside one keyboard row: {duplicates}"
