"""
Словарь с автоматическим удалением записей по TTL.
"""

import time


class TTLDict(dict):
    """dict-подобное хранилище с временем жизни записей."""

    def __init__(self, ttl=1800, clock=None):
        super().__init__()
        self.ttl = ttl
        self._clock = clock or time.monotonic
        self._timestamps = {}

    def _cleanup(self):
        now = self._clock()
        expired = [
            key
            for key, timestamp in self._timestamps.items()
            if now - timestamp >= self.ttl
        ]

        for key in expired:
            super().pop(key, None)
            self._timestamps.pop(key, None)

    def __setitem__(self, key, value):
        self._cleanup()
        super().__setitem__(key, value)
        self._timestamps[key] = self._clock()

    def __getitem__(self, key):
        self._cleanup()
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._cleanup()
        return super().get(key, default)

    def __contains__(self, key):
        self._cleanup()
        return super().__contains__(key)

    def keys(self):
        self._cleanup()
        return super().keys()

    def items(self):
        self._cleanup()
        return super().items()

    def values(self):
        self._cleanup()
        return super().values()

    def __len__(self):
        self._cleanup()
        return super().__len__()

    def pop(self, key, *args):
        self._cleanup()
        self._timestamps.pop(key, None)
        return super().pop(key, *args)

    def __delitem__(self, key):
        self._cleanup()
        self._timestamps.pop(key, None)
        super().__delitem__(key)

    def clear(self):
        super().clear()
        self._timestamps.clear()
