"""时长采样。"""

from __future__ import annotations

import random

from subtitle_dataset.sampling import DurationDistribution, DurationSampler


def _distribution() -> DurationDistribution:
    return DurationDistribution.model_validate(
        {
            "buckets": [
                {"min_ms": 130, "max_ms": 270, "weight": 1.0},
                {"min_ms": 300, "max_ms": 500, "weight": 1.5},
                {"min_ms": 3030, "max_ms": 4000, "weight": 0.4},
            ]
        }
    )


def test_duration_within_bucket_ranges() -> None:
    sampler = DurationSampler(_distribution(), random.Random(42))
    samples = [sampler.sample() for _ in range(200)]
    assert all(130 <= ms <= 270 or 300 <= ms <= 500 or 3030 <= ms <= 4000 for ms in samples)


def test_duration_deterministic_with_seed() -> None:
    first = [DurationSampler(_distribution(), random.Random(7)).sample() for _ in range(10)]
    second = [DurationSampler(_distribution(), random.Random(7)).sample() for _ in range(10)]
    assert first == second


def test_duration_covers_multiple_buckets() -> None:
    sampler = DurationSampler(_distribution(), random.Random(1))
    samples = {sampler.sample() for _ in range(500)}
    assert any(ms <= 270 for ms in samples)
    assert any(300 <= ms <= 500 for ms in samples)
