"""
Централизованная настройка логирования ZverTBot.

Архитектура:
- все логгеры модулей используют logging.getLogger(__name__);
- окружение хранится в LogRecord.environment;
- форматтер автоматически добавляет окружение, модуль, функцию и строку;
- production/test записи физически разделяются фильтрами;
- пользовательские сообщения логгера не должны содержать [BOT]/[TEST].
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from config.config import BOT_NAME, BOT_VERSION, LOG_FILE
from config.paths import LOG_DIR

ERROR_LOG_FILE = LOG_DIR / "zvertbot-errors.log"
TEST_LOG_FILE = LOG_DIR / "zvertbot-test.log"


class EnvironmentFilter(logging.Filter):
    """Добавляет окружение к LogRecord."""

    def filter(self, record):
        if not getattr(record, "environment", None):
            environment = os.getenv("ZVERTBOT_ENV")

            if not environment:
                environment = "TEST" if "pytest" in sys.modules else "BOT"

            record.environment = environment.upper()

        return True


class ProdOnlyFilter(logging.Filter):
    """Пропускает только production-записи."""

    def filter(self, record):
        return getattr(record, "environment", "BOT") == "BOT"


class TestOnlyFilter(logging.Filter):
    """Пропускает только тестовые записи."""

    def filter(self, record):
        return getattr(record, "environment", "BOT") == "TEST"


class ZverTBotFormatter(logging.Formatter):
    """Единый формат логов приложения."""

    DEFAULT_FORMAT = (
        "%(asctime)s.%(msecs)03d | "
        "%(levelname)-8s | "
        "%(environment)-4s | "
        "%(name)s:%(funcName)s:%(lineno)d | "
        "%(message)s"
    )
    DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __init__(self, fmt=None, datefmt=None):
        super().__init__(
            fmt or self.DEFAULT_FORMAT,
            datefmt or self.DEFAULT_DATE_FORMAT,
        )

    def format(self, record):
        environment = getattr(record, "environment", "BOT")
        record.environment = environment.upper()
        return super().format(record)


def setup_logger():
    """Создаёт и настраивает корневой логгер приложения."""

    logger = logging.getLogger("zvertbot")

    # Принимаем все сообщения.
    # Реальный production-уровень задаётся ZVERTBOT_LOG_LEVEL.
    logger.setLevel(logging.DEBUG)

    # Не передаём записи выше в root logger.
    # Иначе возможны дубли в systemd/journal.
    logger.propagate = False

    log_level_name = os.getenv("ZVERTBOT_LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    if log_level not in (
        logging.DEBUG,
        logging.INFO,
        logging.WARNING,
        logging.ERROR,
        logging.CRITICAL,
    ):
        log_level = logging.INFO

    # Не создаём второй комплект handlers при повторном импорте.
    if logger.handlers:
        return logger

    formatter = ZverTBotFormatter()

    env_filter = EnvironmentFilter()
    prod_filter = ProdOnlyFilter()
    test_filter = TestOnlyFilter()

    # Production log.
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(env_filter)
    file_handler.addFilter(prod_filter)

    # Production error log.
    error_handler = RotatingFileHandler(
        ERROR_LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    error_handler.addFilter(env_filter)
    error_handler.addFilter(prod_filter)

    # Test log.
    test_handler = RotatingFileHandler(
        TEST_LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    test_handler.setLevel(logging.DEBUG)
    test_handler.setFormatter(formatter)
    test_handler.addFilter(env_filter)
    test_handler.addFilter(test_filter)

    # systemd/journalctl.
    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(formatter)
    console.addFilter(env_filter)
    console.addFilter(prod_filter)

    logger.addHandler(file_handler)
    logger.addHandler(error_handler)
    logger.addHandler(test_handler)
    logger.addHandler(console)

    return logger


logger = setup_logger()

logger.info(
    "logger.initialized | app=%s | version=%s | log_file=%s | "
    "rotation=10MBx4",
    BOT_NAME,
    BOT_VERSION,
    LOG_FILE,
)
