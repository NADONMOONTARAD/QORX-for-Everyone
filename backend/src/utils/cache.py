"""Simple thread-safe TTL cache primitives."""

from __future__ import annotations

import threading
import time
from typing import Generic, MutableMapping, Optional, Tuple, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    def __init__(
        self,
        ttl_seconds: float,
        *,
        clock=time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._store: MutableMapping[K, Tuple[V, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return default
            value, expires_at = entry
            now = self._clock()
            if now >= expires_at:
                self._store.pop(key, None)
                return default
            return value

    def set(self, key: K, value: V, ttl_override: Optional[float] = None) -> None:
        ttl = self.ttl_seconds if ttl_override is None else float(ttl_override)
        if ttl <= 0:
            raise ValueError("ttl_override must be positive")
        expires_at = self._clock() + ttl
        with self._lock:
            self._store[key] = (value, expires_at)

    def pop(self, key: K, default: Optional[V] = None) -> Optional[V]:
        with self._lock:
            entry = self._store.pop(key, None)
            if entry is None:
                return default
            value, _ = entry
            return value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __contains__(self, key: K) -> bool:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return False
            _, expires_at = entry
            if self._clock() >= expires_at:
                self._store.pop(key, None)
                return False
            return True

    def size(self) -> int:
        with self._lock:
            now = self._clock()
            stale = [k for k, (_, exp) in self._store.items() if now >= exp]
            for k in stale:
                self._store.pop(k, None)
            return len(self._store)
