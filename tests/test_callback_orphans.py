"""
Диагностический аудит сиротских callback-маршрутов.

Показывает:
1. exact callback, зарегистрированный в CALLBACK_HANDLERS,
   но не найденный среди callback_data в исходном коде;
2. prefix из PREFIX_HANDLERS, для которого не найден
   ни один callback_data с таким prefix.

Тест пока НЕ падает из-за найденных кандидатов.
Цель — сначала классифицировать реальные legacy-маршруты.
"""

from __future__ import annotations

import ast
from pathlib import Path

from core.callback_router import all_callbacks, all_prefixes

ROOT = Path(__file__).resolve().parents[1]

SCAN_DIRS = (
    ROOT / "ui",
    ROOT / "handlers",
    ROOT / "services",
    ROOT / "core",
)


def _python_files():
    for directory in SCAN_DIRS:
        if not directory.exists():
            continue

        yield from (
            path
            for path in directory.rglob("*.py")
            if "__pycache__" not in path.parts
            and path != ROOT / "core" / "callback_router.py"
        )


def _collect_string_constants(tree: ast.AST) -> dict[str, str]:
    constants = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue

        if len(node.targets) != 1:
            continue

        target = node.targets[0]

        if not isinstance(target, ast.Name):
            continue

        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            constants[target.id] = node.value.value

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue

        if node.module != "core.navigation":
            continue

        for alias in node.names:
            if alias.name == "*":
                continue

            constants.setdefault(
                alias.asname or alias.name,
                _navigation_constant_value(alias.name),
            )

    return {key: value for key, value in constants.items() if value is not None}


def _navigation_constant_value(name: str) -> str | None:
    navigation_path = ROOT / "core" / "navigation.py"
    tree = ast.parse(
        navigation_path.read_text(encoding="utf-8"),
        filename=str(navigation_path),
    )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue

        if len(node.targets) != 1:
            continue

        target = node.targets[0]

        if not isinstance(target, ast.Name) or target.id != name:
            continue

        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value

    return None


def _callback_prefix(node: ast.AST, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value

    if isinstance(node, ast.Name):
        return constants.get(node.id)

    if isinstance(node, ast.JoinedStr):
        result = []

        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                result.append(value.value)
                continue

            if isinstance(value, ast.FormattedValue):
                resolved = _callback_prefix(value.value, constants)
                if resolved is not None:
                    result.append(resolved)
                    continue
                break

            break

        return "".join(result)

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _callback_prefix(node.left, constants)
        right = _callback_prefix(node.right, constants)

        if left is None:
            return None

        return left + (right or "")

    return None


def _extract_callback_values():
    values = []

    for path in _python_files():
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )
        constants = _collect_string_constants(tree)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            if not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "InlineKeyboardButton"
            ):
                continue

            callback_node = next(
                (
                    keyword.value
                    for keyword in node.keywords
                    if keyword.arg == "callback_data"
                ),
                None,
            )

            if callback_node is None:
                continue

            callback_nodes = (
                (callback_node.body, callback_node.orelse)
                if isinstance(callback_node, ast.IfExp)
                else (callback_node,)
            )

            for callback_value_node in callback_nodes:
                prefix = _callback_prefix(callback_value_node, constants)

                if prefix:
                    values.append(
                        (
                            prefix,
                            str(path.relative_to(ROOT)),
                            node.lineno,
                        )
                    )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue

            if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
                continue

            if len(node.comparators) != 1:
                continue

            left = node.left
            right = node.comparators[0]

            for callback_node in (left, right):
                prefix = _callback_prefix(callback_node, constants)

                if prefix:
                    values.append(
                        (
                            prefix,
                            str(path.relative_to(ROOT)),
                            node.lineno,
                        )
                    )
                    break

    return values


def test_report_orphan_callback_routes():
    callback_values = _extract_callback_values()
    used = {value for value, _, _ in callback_values}

    exact_routes = set(all_callbacks())

    orphans = sorted(exact_routes - used)

    print("\n=== ORPHAN EXACT CALLBACKS ===")

    if not orphans:
        print("NONE")
    else:
        for callback in orphans:
            print(f"  {callback}")

    assert True


def test_report_orphan_callback_prefixes():
    callback_values = _extract_callback_values()

    prefixes = all_prefixes()

    orphans = []

    for prefix in prefixes:
        matches = [item for item in callback_values if item[0].startswith(prefix)]

        if not matches:
            orphans.append(prefix)

    print("\n=== ORPHAN CALLBACK PREFIXES ===")

    if not orphans:
        print("NONE")
    else:
        for prefix in sorted(orphans):
            print(f"  {prefix}")

    assert True
