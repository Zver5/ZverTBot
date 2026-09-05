"""
Проверка целостности callback-кнопок.

Проверяет callback_data, найденные в ui/*.py.

Поддерживает:
- обычные callback

- динамические callback:
    callback_data=f"qr:{proto}:{username}"
    callback_data=f"stats_{proto}_{username}"
"""

import re
from pathlib import Path

from core.callback_router import CALLBACK_ROUTES, resolve
from utils.logger import logger

BASE_DIR = Path(__file__).resolve().parent.parent


def extract_callbacks():
    """Находит callback_data в UI-файлах."""

    callbacks = set()

    scan_dirs = (
        BASE_DIR / "ui",
        BASE_DIR / "handlers",
        BASE_DIR / "services",
        BASE_DIR / "core",
    )

    files = []
    for directory in scan_dirs:
        if directory.exists():
            files.extend(directory.rglob("*.py"))

    for file in files:
        try:
            text = file.read_text(encoding="utf-8")

            found = re.findall(
                r'callback_data\s*=\s*(?:f)?["\']([^"\']+)["\']',
                text,
            )

            for callback in found:
                callback = callback.replace(
                    "{CLIENT_CONF_CALLBACK_PREFIX}",
                    "client:conf:",
                )
                callback = callback.replace(
                    "{CLIENT_CONF_RU_CALLBACK_PREFIX}",
                    "client:conf_ru:",
                )
                callbacks.add(callback)

        except Exception as e:
            logger.warning(
                "callbacks.scan.failed | file=%s | error=%s",
                file,
                e,
            )

    return callbacks


def normalize_dynamic_callback(value: str) -> str:
    """
    Преобразует f-string callback в его статический префикс.

    Например:

        qr_{proto}_{username}
            -> qr_

        stats_{proto}_{u}
            -> stats_

    """

    if "{" in value:
        return value.split("{", 1)[0]

    return value


def has_prefix_handler(prefix: str) -> bool:
    """
    Проверяет, существует ли зарегистрированный обработчик
    для указанного динамического callback-префикса.

    Совпадение считается найденным в обе стороны:
    - переданный prefix начинается с зарегистрированного префикса;
    - зарегистрированный префикс начинается с переданного prefix.

    Это позволяет проверять как полный динамический префикс,
    так и его укороченную базовую форму.
    """
    for route in CALLBACK_ROUTES:
        if route.prefix and prefix.startswith(route.pattern):
            return True

    return False


def check_callbacks():
    """
    Проверяет callback-кнопки.

    Обычные callback проверяются через resolve().
    Динамические callback проверяются по их префиксу.

    Дополнительно выводит статистику:
    - реальные callback;
    - динамические callback;
    - общее количество.
    """

    callbacks = extract_callbacks()
    errors = []

    real_callbacks = set()
    dynamic_callbacks = set()

    for callback in sorted(callbacks):
        # --------------------------------------------------
        # Динамический callback
        # --------------------------------------------------

        if "{" in callback or "*" in callback:
            dynamic_callbacks.add(callback)

            prefix = normalize_dynamic_callback(callback)

            if not has_prefix_handler(prefix):
                errors.append(callback)

            continue

        # --------------------------------------------------
        # Реальный callback
        # --------------------------------------------------

        real_callbacks.add(callback)

        if resolve(callback) is None:
            errors.append(callback)

    # ------------------------------------------------------
    # Статистика
    # ------------------------------------------------------

    real_count = len(real_callbacks)
    dynamic_count = len(dynamic_callbacks)
    total_count = len(callbacks)

    logger.info(
        "callbacks.check.completed | total=%s | real=%s | dynamic=%s",
        total_count,
        real_count,
        dynamic_count,
    )

    # ------------------------------------------------------
    # Результат
    # ------------------------------------------------------

    if errors:
        logger.warning(
            "callbacks.check.failed | count=%s",
            len(errors),
        )

        for callback in errors:
            logger.warning(
                "callbacks.check.unknown | callback=%s",
                callback,
            )

        return False

    logger.info(
        "callbacks.check.passed | total=%s",
        total_count,
    )

    return True


def main():
    """Запускает проверку callback-ов как CLI-команду."""
    success = check_callbacks()
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
