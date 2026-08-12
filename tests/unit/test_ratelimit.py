"""多来源并发限速器。"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from subtitle_dataset.ingest import RateLimiter


def test_per_source_interval() -> None:
    limiter = RateLimiter(per_source_ms=100)
    limiter.wait("a")
    start = time.monotonic()
    limiter.wait("a")
    assert time.monotonic() - start >= 0.08


def test_independent_sources_not_serialized() -> None:
    limiter = RateLimiter(per_source_ms=200)
    limiter.wait("a")
    start = time.monotonic()
    limiter.wait("b")
    assert time.monotonic() - start < 0.1


def test_global_interval_across_sources() -> None:
    limiter = RateLimiter(global_ms=120)
    limiter.wait("a")
    start = time.monotonic()
    limiter.wait("b")
    assert time.monotonic() - start >= 0.1


def test_thread_safe_global_staggering() -> None:
    limiter = RateLimiter(global_ms=50)

    def worker(index: int) -> None:
        for step in range(3):
            limiter.wait(f"src-{index}-{step}")

    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(worker, range(4)))
    assert time.monotonic() - start >= 0.3
