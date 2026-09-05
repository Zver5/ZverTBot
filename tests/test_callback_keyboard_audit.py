"""
Строгий аудит callback_data во всём исходном Python-коде.

Проверяет:
- точные callback_data имеют маршрут;
- динамические f-string имеют зарегистрированный prefix;
- callback вида "prefix_" + value имеет зарегистрированный prefix;
- callback из handlers тоже проверяются, а не только ui/keyboards.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

from core.callback_router import all_prefixes, get

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
            path for path in directory.rglob("*.py") if "__pycache__" not in path.parts
        )


NAV_CALLBACK_CONSTANTS = {
    "NAV_BACK_CALLBACK": "nav:back",
    "NAV_HOME_CALLBACK": "nav:home",
    "NAV_MANAGE_CALLBACK": "nav:manage",
    "NAV_CREATE_CALLBACK": "nav:create",
    "NAV_SYSTEM_CALLBACK": "nav:system",
    "NAV_NETWORK_CALLBACK": "nav:network",
    "NAV_ANALYTICS_CALLBACK": "nav:analytics",
    "NAV_BACKUPS_CALLBACK": "nav:backups",
    "NAV_AI_LOGS_CALLBACK": "nav:ai_logs",
    "NAV_CLIENTS_CALLBACK": "nav:clients",
    "NAV_CLIENTS_MANAGE_CALLBACK": "nav:clients_manage",
    "NAV_CLIENTS_VLESS_CALLBACK": "nav:clients_vless",
    "NAV_CLIENTS_AWG_CALLBACK": "nav:clients_awg",
    "NAV_CLIENTS_RENAME_CALLBACK": "nav:clients_rename",
    "NAV_CLIENTS_SEARCH_VLESS_CALLBACK": "nav:clients_search_vless",
    "NAV_CLIENTS_SEARCH_AWG_CALLBACK": "nav:clients_search_awg",
    "PROCESS_MENU_CALLBACK": "processes_menu",
    "PROCESS_TOP_CALLBACK": "processes_top",
    "PROCESS_TOP_CPU_CALLBACK": "processes_top_cpu",
    "PROCESS_TOP_RAM_CALLBACK": "processes_top_ram",
    "PROCESS_SEARCH_CALLBACK": "process_search",
    "PROCESS_KILL_CALLBACK": "process_kill",
    "FAIL2BAN_MENU_CALLBACK": "fail2ban_menu",
    "FAIL2BAN_LOGS_CALLBACK": "fail2ban_logs",
    "FAIL2BAN_UNBAN_CALLBACK": "fail2ban_unban",
    "CLIENT_BACK_CALLBACK": "client:back",
    "CLIENT_CONF_CALLBACK_PREFIX": "client:conf:",
    "CLIENT_CONF_RU_CALLBACK_PREFIX": "client:conf_ru:",
    "NAV_ADMIN_TICKETS_CALLBACK": "nav:admin_tickets",
    "NAV_ADMIN_TICKETS_NEW_CALLBACK": "nav:admin_tickets_new",
    "NAV_ADMIN_TICKETS_WORKING_CALLBACK": "nav:admin_tickets_working",
    "NAV_ADMIN_TICKETS_CLOSED_CALLBACK": "nav:admin_tickets_closed",
    "NAV_BACKUP_HISTORY_CALLBACK": "nav:backup_history",
    "NAV_CLIENT_HOME_CALLBACK": "nav:client_home",
    "NAV_CLIENT_BACK_CALLBACK": "nav:client_back",
    "NAV_CLIENT_HELP_CALLBACK": "nav:client_help",
}


def _extract_constant_prefix(node: ast.AST) -> str | None:
    """
    Извлекает статическую часть callback_data.

    Поддерживает:
        "nav:back"
        NAV_MANAGE_CALLBACK
        f"do_bind_{target}_{user}"
        "bind_existing_" + target
        "qr:" + value
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value

    if isinstance(node, ast.Name):
        return NAV_CALLBACK_CONSTANTS.get(node.id)

    if isinstance(node, ast.JoinedStr):
        parts = []

        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
                continue

            if isinstance(value, ast.FormattedValue):
                if isinstance(value.value, ast.Name):
                    constant = NAV_CALLBACK_CONSTANTS.get(value.value.id)
                    if constant is not None:
                        parts.append(constant)
                        continue
                break

            break

        return "".join(parts)

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _extract_constant_prefix(node.left)
        if left is not None:
            return left

    return None


def _normalize_callback(node: ast.AST) -> str | None:
    value = _extract_constant_prefix(node)

    if value is None:
        return None

    if "{" in value:
        value = value.split("{", 1)[0]

    return value


def _build_parameter_values(tree):
    """
    Находит простые вызовы функций с позиционными аргументами-строками.

    Пример:

        def _refresh_keyboard(callback_data):
            ...

        _refresh_keyboard("ssh_list")

    Возвращает карту:
        {
            ("_refresh_keyboard", "callback_data"): {"ssh_list", "ssh_status"}
        }

    Поддерживаются только однозначные статические строковые аргументы.
    Это намеренно ограниченный анализ: неизвестные значения не считаются
    валидными автоматически.
    """
    result = {}

    functions = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = node

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if not isinstance(node.func, ast.Name):
            continue

        function = functions.get(node.func.id)
        if function is None:
            continue

        positional_params = [arg.arg for arg in function.args.args]

        for index, argument in enumerate(node.args):
            if index >= len(positional_params):
                break

            if not (
                isinstance(argument, ast.Constant) and isinstance(argument.value, str)
            ):
                continue

            key = (function.name, positional_params[index])
            result.setdefault(key, set()).add(argument.value)

    return result


def _parameter_callback_values(tree):
    """
    Находит статические значения параметров функций, переданные из вызовов.

    Например:

        def _refresh_keyboard(callback_data):
            InlineKeyboardButton(..., callback_data=callback_data)

        _refresh_keyboard("ssh_list")
        _refresh_keyboard("ssh_status")

    Для параметра callback_data будут найдены оба значения.
    """
    parent_map = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }

    functions = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = node

    values = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if not isinstance(node.func, ast.Name):
            continue

        function = functions.get(node.func.id)
        if function is None:
            continue

        params = function.args.args

        for index, argument in enumerate(node.args):
            if index >= len(params):
                break

            if not (
                isinstance(argument, ast.Constant) and isinstance(argument.value, str)
            ):
                continue

            key = (function.name, params[index].arg)
            values.setdefault(key, set()).add(argument.value)

        for keyword in node.keywords:
            if keyword.arg is None:
                continue

            if not (
                isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                continue

            if not any(param.arg == keyword.arg for param in params):
                continue

            key = (function.name, keyword.arg)
            values.setdefault(key, set()).add(keyword.value.value)

    return parent_map, values


def _enclosing_function_name(node, parent_map):
    current = node

    while current in parent_map:
        current = parent_map[current]

        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name

    return None


def _find_callback_data():
    found = []

    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parent_map, parameter_values = _parameter_callback_values(tree)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            is_button = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "InlineKeyboardButton"
            )

            if not is_button:
                continue

            callback_node = None

            for keyword in node.keywords:
                if keyword.arg == "callback_data":
                    callback_node = keyword.value
                    break

            if callback_node is None:
                continue

            callback_nodes = (
                [callback_node.body, callback_node.orelse]
                if isinstance(callback_node, ast.IfExp)
                else [callback_node]
            )

            for candidate in callback_nodes:
                normalized = _normalize_callback(candidate)

                if normalized is not None:
                    callbacks = [normalized]
                elif isinstance(candidate, ast.Name):
                    function_name = _enclosing_function_name(
                        node,
                        parent_map,
                    )
                    callbacks = sorted(
                        parameter_values.get(
                            (function_name, candidate.id),
                            set(),
                        )
                    )
                else:
                    callbacks = []

                if callbacks:
                    for callback in callbacks:
                        found.append(
                            {
                                "path": path.relative_to(ROOT),
                                "line": node.lineno,
                                "source": ast.unparse(candidate),
                                "callback": callback,
                            }
                        )
                else:
                    found.append(
                        {
                            "path": path.relative_to(ROOT),
                            "line": node.lineno,
                            "source": ast.unparse(candidate),
                            "callback": None,
                        }
                    )

    return found


def test_all_inline_keyboard_callbacks_have_routes():
    missing = []

    prefixes = tuple(all_prefixes())

    for item in _find_callback_data():
        callback = item["callback"]

        if not callback:
            missing.append(
                f"{item['path']}:{item['line']} "
                f"{item['source']} -> не удалось определить callback prefix"
            )
            continue

        # Сначала точное совпадение.
        if get(callback) is not None:
            continue

        # Затем только односторонняя проверка prefix:
        # зарегистрированный prefix должен быть началом callback.
        if any(callback.startswith(prefix) for prefix in prefixes):
            continue

        missing.append(
            f"{item['path']}:{item['line']} {item['source']} -> {callback!r}"
        )

    assert not missing, "Найдены callback_data без маршрута:\n" + "\n".join(
        f"  - {item}" for item in missing
    )


def test_no_unparseable_callback_data():
    unknown = []

    for item in _find_callback_data():
        if item["callback"] is None:
            unknown.append(f"{item['path']}:{item['line']} {item['source']}")

    assert not unknown, (
        "Не удалось определить статическую часть callback_data:\n"
        + "\n".join(f"  - {item}" for item in unknown)
    )
