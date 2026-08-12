"""去重与划分：感知哈希、聚类、分配器。"""

from __future__ import annotations

import random

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from subtitle_dataset.dedup import (
    ContentCluster,
    DedupItem,
    DifferenceHash,
    SplitAllocator,
    SplitConfig,
    build_exact_clusters,
    build_near_clusters,
    hamming_distance,
)


def _pattern_image(seed: int, brightness: int = 0) -> Image.Image:
    rng = random.Random(seed)
    base = np.zeros((64, 64), dtype=np.int16)
    for y in range(64):
        for x in range(64):
            base[y, x] = (x * 3 + y * 7 + rng.randrange(8)) % 220
    pixels = np.clip(np.stack([base, base, base], axis=-1) + brightness, 0, 255)
    return Image.fromarray(pixels.astype(np.uint8))


def _random_image(seed: int) -> Image.Image:
    rng = random.Random(seed)
    pixels = np.asarray(
        [[rng.randrange(256) for _ in range(64)] for _ in range(64)],
        dtype=np.uint8,
    )
    return Image.fromarray(pixels, mode="L")


def test_difference_hash_stable() -> None:
    hasher = DifferenceHash()
    assert hasher.hash(_pattern_image(1)) == hasher.hash(_pattern_image(1))
    assert len(hasher.hash(_pattern_image(1))) == 16


def test_difference_hash_tolerates_brightness_shift() -> None:
    hasher = DifferenceHash()
    a = hasher.hash(_pattern_image(2))
    b = hasher.hash(_pattern_image(2, brightness=25))
    assert hamming_distance(a, b) <= 2


def test_difference_hash_distinguishes_content() -> None:
    hasher = DifferenceHash()
    a = hasher.hash(_random_image(2))
    b = hasher.hash(_random_image(77))
    assert hamming_distance(a, b) > 8


def test_exact_clusters_group_by_sha256() -> None:
    items = [
        DedupItem(id="b", sha256="11" * 32),
        DedupItem(id="a", sha256="11" * 32),
        DedupItem(id="c", sha256="22" * 32),
    ]
    clusters = build_exact_clusters(items)
    assert len(clusters) == 2
    duplicate = next(cluster for cluster in clusters if len(cluster.items) == 2)
    assert duplicate.representative_id == "a"
    assert {item.id for item in duplicate.items} == {"a", "b"}


def test_near_clusters_group_similar_content() -> None:
    hasher = DifferenceHash()
    a = DedupItem(id="a", sha256="a" * 64, near_hash=hasher.hash(_pattern_image(3)))
    a2 = DedupItem(
        id="a2",
        sha256="b" * 64,
        near_hash=hasher.hash(_pattern_image(3, brightness=25)),
    )
    b = DedupItem(id="b", sha256="c" * 64, near_hash=hasher.hash(_random_image(77)))
    clusters = build_near_clusters([a, a2, b], hamming_threshold=2)
    assert len(clusters) == 2
    group = next(cluster for cluster in clusters if len(cluster.items) == 2)
    assert {item.id for item in group.items} == {"a", "a2"}


def _cluster(cluster_id: str, size: int, platform: str | None = None) -> ContentCluster:
    return ContentCluster(
        cluster_id=cluster_id,
        cluster_type="exact",
        representative_id=f"{cluster_id}-0",
        items=[
            DedupItem(
                id=f"{cluster_id}-{index}",
                sha256="0" * 64,
                platform=platform,
                group_id=cluster_id,
            )
            for index in range(size)
        ],
    )


def test_allocator_deterministic_and_cluster_whole() -> None:
    clusters = [
        _cluster("c1", 3, "p1"),
        _cluster("c2", 2, "p1"),
        _cluster("c3", 1, "p2"),
        _cluster("c4", 1, "p2"),
    ]
    config = SplitConfig(ratios={"train": 0.6, "val": 0.2, "test": 0.2}, seed=7)
    first = SplitAllocator(config).allocate(clusters)
    second = SplitAllocator(config).allocate(clusters)
    assert first.assignments == second.assignments
    assert sum(first.item_counts.values()) == 7
    assert sum(first.cluster_counts.values()) == 4
    assert set(first.assignments) == {"c1", "c2", "c3", "c4"}


def test_allocator_warns_when_group_limit_infeasible() -> None:
    clusters = [_cluster(f"c{i}", 1, "p1") for i in range(4)]
    config = SplitConfig(
        ratios={"train": 0.5, "val": 0.5},
        seed=1,
        group_limits={"platform": 0.5},
    )
    assignment = SplitAllocator(config).allocate(clusters)
    assert assignment.warnings


def test_allocator_shares_within_limit_or_warns() -> None:
    clusters = [
        _cluster("a1", 1, "p1"),
        _cluster("a2", 1, "p1"),
        _cluster("b1", 1, "p2"),
        _cluster("b2", 1, "p2"),
    ]
    config = SplitConfig(
        ratios={"train": 0.5, "val": 0.5},
        seed=3,
        group_limits={"platform": 0.75},
    )
    assignment = SplitAllocator(config).allocate(clusters)
    for split_shares in assignment.group_shares.values():
        for shares in split_shares.values():
            for share in shares.values():
                assert share <= 0.75 + 1e-9 or assignment.warnings


def test_split_config_rejects_bad_ratios() -> None:
    with pytest.raises(ValidationError):
        SplitConfig(ratios={"train": 0.5, "val": 0.5, "test": 0.1})
    with pytest.raises(ValidationError):
        SplitConfig(ratios={"train": 1.0, "unknown": 0.0})
