"""Thread-safe throttling utilities for API clients."""

from __future__ import annotations

import heapq
import itertools
import random
import threading
import time
from collections import deque
from typing import Deque, Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "SlidingWindowRateLimiter",
    "RateLimitedKeyPool",
]


class SlidingWindowRateLimiter:
    """Simple sliding-window limiter (max_calls within period_seconds).

    Call ``acquire()`` before hitting an API endpoint. If the call budget has
    been exhausted, the method blocks until the window clears.
    """

    def __init__(
        self,
        max_calls: int,
        period_seconds: float,
        *,
        name: str | None = None,
    ) -> None:
        if max_calls <= 0 or period_seconds <= 0:
            raise ValueError("max_calls and period_seconds must be positive")
        self.max_calls = int(max_calls)
        self.period_seconds = float(period_seconds)
        self.name = name or ""
        self._timestamps: Deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                # prune timestamps outside the window
                window_start = now - self.period_seconds
                while self._timestamps and self._timestamps[0] < window_start:
                    self._timestamps.popleft()
                if len(self._timestamps) < self.max_calls:
                    self._timestamps.append(now)
                    return
                # compute wait time until earliest call exits window
                wait_time = self._timestamps[0] + self.period_seconds - now
            time.sleep(max(wait_time, 0.001))


class RateLimitedKeyPool:
    """Round-robin key pool respecting a minimum spacing per key.

    Example: 12 Finnhub keys with ``min_interval_seconds=1`` enforces
    ``1 request/sec/key`` while still allowing up to 12 concurrent workers.

    Callers must invoke :meth:`release` once their request finishes so the
    cooldown window begins after the upstream API responds.
    """

    def __init__(
        self,
        keys: Sequence[str],
        *,
        min_interval_seconds: float,
        jitter_seconds: float = 0.0,
        shuffle: bool = True,
        name: str | None = None,
    ) -> None:
        if not keys:
            raise ValueError("RateLimitedKeyPool requires at least one key")
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must be non-negative")
        self.name = name or ""
        self.min_interval_seconds = float(min_interval_seconds)
        self.jitter_seconds = max(0.0, float(jitter_seconds))
        self._lock = threading.Lock()
        keys_list: List[str] = list(keys)
        if shuffle and len(keys_list) > 1:
            random.shuffle(keys_list)
        now = time.monotonic()
        self._counter = itertools.count()
        # heap entries: (available_at, sequence, key)
        self._heap: List[Tuple[float, int, str]] = [
            (now, next(self._counter), key) for key in keys_list
        ]
        heapq.heapify(self._heap)
        self._in_flight: Dict[str, float] = {}
        self._pending_deferrals: Dict[str, float] = {}

    def __len__(self) -> int:
        with self._lock:
            return len(self._heap) + len(self._in_flight)

    def acquire(self) -> str:
        while True:
            with self._lock:
                if not self._heap:
                    raise RuntimeError("No keys available in pool")
                available_at, seq, key = self._heap[0]
                now = time.monotonic()
                wait_time = available_at - now
                if wait_time <= 0:
                    heapq.heappop(self._heap)
                    self._in_flight[key] = now
                    return key
            time.sleep(max(wait_time, 0.001))

    def release(self, key: str) -> None:
        if not key:
            return
        now = time.monotonic()
        with self._lock:
            acquired_at = self._in_flight.pop(key, None)
            if acquired_at is None:
                return
            base_time = max(now, acquired_at)
            next_time = self._next_available_timestamp(base_time)
            extra_wait = self._pending_deferrals.pop(key, 0.0)
            if extra_wait > 0:
                next_time += extra_wait
            heapq.heappush(self._heap, (next_time, next(self._counter), key))

    def defer(self, key: str, extra_seconds: float) -> None:
        """Extend ``key`` availability by at least ``extra_seconds``."""
        if extra_seconds <= 0:
            return
        with self._lock:
            if key in self._in_flight:
                self._pending_deferrals[key] = (
                    self._pending_deferrals.get(key, 0.0) + extra_seconds
                )
                return
            now = time.monotonic()
            for idx, (available_at, seq, existing_key) in enumerate(self._heap):
                if existing_key == key:
                    target = max(available_at, now) + extra_seconds
                    self._heap[idx] = (target, seq, existing_key)
                    heapq.heapify(self._heap)
                    return

    def remove(self, key: str) -> None:
        with self._lock:
            for idx, (_, _, existing_key) in enumerate(self._heap):
                if existing_key == key:
                    self._heap.pop(idx)
                    heapq.heapify(self._heap)
                    break
            else:
                self._in_flight.pop(key, None)
            self._pending_deferrals.pop(key, None)
            if not self._heap and not self._in_flight:
                raise RuntimeError("All keys removed from key pool")

    def _next_available_timestamp(self, base_time: float) -> float:
        jitter = 0.0
        if self.jitter_seconds > 0:
            jitter = random.uniform(0.0, self.jitter_seconds)
        return base_time + self.min_interval_seconds + jitter
