"""时长采样：以 duration_ms 为统一单位。"""

from __future__ import annotations

import random

from .config import DurationDistribution, weighted_choice


class DurationSampler:
    """按分桶加权采样字幕时长（毫秒）。"""

    def __init__(self, distribution: DurationDistribution, rng: random.Random) -> None:
        self._distribution = distribution
        self._rng = rng

    def sample(self) -> int:
        bucket = weighted_choice(
            self._rng,
            [(b, b.weight) for b in self._distribution.buckets],
        )
        return self._rng.randint(bucket.min_ms, bucket.max_ms)
