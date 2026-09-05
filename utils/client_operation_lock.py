"""
Общий lock для операций изменения клиентов и сбора статистики.

Не позволяет одновременно выполнять:
- переименование/изменение клиента;
- сбор и синхронизацию usage.json.

Это важно, потому что collector использует имя клиента
как ключ в usage.json.
"""

import fcntl
import threading
from functools import wraps
from pathlib import Path

LOCK_FILE = Path("/tmp/zvertbot-client-operations.lock")

_lock_state = threading.local()


def client_operation_lock(func):
    """Выполнить функцию под эксклюзивным межпроцессным lock.

    Lock реентерабельный внутри одного потока: вложенные вызовы
    не открывают второй flock, но внешний процесс всё равно блокируется.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        depth = getattr(_lock_state, "depth", 0)

        if depth:
            _lock_state.depth = depth + 1
            try:
                return func(*args, **kwargs)
            finally:
                _lock_state.depth -= 1

        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

        with LOCK_FILE.open("w", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            _lock_state.depth = 1
            try:
                return func(*args, **kwargs)
            finally:
                _lock_state.depth = 0
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    return wrapper
