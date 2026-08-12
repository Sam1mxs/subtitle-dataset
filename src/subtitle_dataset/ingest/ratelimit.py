"""多来源并发限速：来源级最小间隔 + 可选全局最小间隔。"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """按来源（可选按全局）保证请求最小间隔。

    槽位预留放在锁内完成（保证间隔正确），实际休眠放在锁外（避免串行化）。
    """

    def __init__(self, per_source_ms: int = 0, global_ms: int = 0) -> None:
        self._per_source_ms = max(0, per_source_ms)
        self._global_ms = max(0, global_ms)
        self._next_at: dict[str, float] = {}
        self._global_next = 0.0
        self._lock = threading.Lock()

    def wait(self, source_id: str) -> None:
        now = time.monotonic()
        with self._lock:
            per_interval = self._per_source_ms / 1000.0
            global_interval = self._global_ms / 1000.0
            per_next = max(self._next_at.get(source_id, now), now)
            global_next = max(self._global_next, now)
            target = max(per_next, global_next)
            sleep_for = max(target - now, 0.0)
            self._next_at[source_id] = target + per_interval
            self._global_next = target + global_interval
        if sleep_for > 0:
            time.sleep(sleep_for)
