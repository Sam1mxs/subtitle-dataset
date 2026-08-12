"""精确与近重复聚类。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .hashing import hamming_distance
from .models import ContentCluster, DedupItem


def items_from_ingest_manifest(manifest: Mapping[str, Any]) -> list[DedupItem]:
    """把 ingest manifest 展开为去重条目：视频级 + 帧级。"""
    video_sha256 = manifest["video_sha256"]
    items = [
        DedupItem(
            id=f"video:{video_sha256}",
            sha256=video_sha256,
            group_id=video_sha256,
        )
    ]
    for frame in manifest["frames"]:
        items.append(
            DedupItem(
                id=f"frame:{video_sha256}:{frame['uri']}",
                sha256=frame["image_sha256"],
                group_id=video_sha256,
            )
        )
    return items


def build_exact_clusters(items: Sequence[DedupItem]) -> list[ContentCluster]:
    """按 SHA-256 精确去重；同一哈希的条目归入一个簇。"""
    groups: dict[str, list[DedupItem]] = defaultdict(list)
    for item in items:
        groups[item.sha256].append(item)
    clusters: list[ContentCluster] = []
    for sha256, group in sorted(groups.items()):
        ordered = sorted(group, key=lambda item: item.id)
        clusters.append(
            ContentCluster(
                cluster_id=f"exact-{sha256[:16]}",
                cluster_type="exact",
                representative_id=ordered[0].id,
                items=ordered,
            )
        )
    return clusters


def build_near_clusters(
    items: Sequence[DedupItem],
    *,
    hamming_threshold: int = 2,
) -> list[ContentCluster]:
    """按感知哈希汉明距离近重复聚类（骨架实现，代表性贪心）。"""
    with_hash = [item for item in items if item.near_hash]
    clusters: list[ContentCluster] = []
    for item in sorted(with_hash, key=lambda item: item.id):
        placed = False
        for cluster in clusters:
            representative = next(
                member for member in cluster.items if member.id == cluster.representative_id
            )
            if (
                representative.near_hash is not None
                and item.near_hash is not None
                and hamming_distance(representative.near_hash, item.near_hash) <= hamming_threshold
            ):
                cluster.items.append(item)
                placed = True
                break
        if not placed:
            near_hash = item.near_hash or ""
            clusters.append(
                ContentCluster(
                    cluster_id=f"near-{near_hash[:12]}",
                    cluster_type="near",
                    representative_id=item.id,
                    items=[item],
                )
            )
    return clusters
