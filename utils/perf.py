import time
from functools import wraps

from utils.logger import logger


def profile(threshold=50):
    """
    Декоратор профилирования функций.

    threshold - минимальное время (мс), после которого писать лог.
    """

    def decorator(func):

        @wraps(func)
        def wrapper(*args, **kwargs):

            start = time.perf_counter()

            try:
                return func(*args, **kwargs)

            finally:
                elapsed = (time.perf_counter() - start) * 1000

                name = f"{func.__module__}.{func.__name__}"

                if elapsed >= 1000:
                    logger.warning(
                        "perf.measure.slow | name=%s | elapsed_ms=%.1f",
                        name,
                        elapsed,
                    )

                elif elapsed >= 300:
                    logger.warning(
                        "perf.measure.warning | name=%s | elapsed_ms=%.1f",
                        name,
                        elapsed,
                    )

                elif elapsed >= threshold:
                    logger.info(
                        "perf.measure.completed | name=%s | elapsed_ms=%.1f",
                        name,
                        elapsed,
                    )

        return wrapper

    return decorator
