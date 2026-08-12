"""文件哈希与视频近重复聚类。"""

from .cluster import build_exact_clusters, build_near_clusters, items_from_ingest_manifest
from .hashing import DifferenceHash, ImageHasher, hamming_distance
from .models import ContentCluster, DedupItem
from .split import SplitAllocator, SplitAssignment, SplitConfig

__all__ = [
    "ContentCluster",
    "DedupItem",
    "DifferenceHash",
    "ImageHasher",
    "SplitAllocator",
    "SplitAssignment",
    "SplitConfig",
    "build_exact_clusters",
    "build_near_clusters",
    "hamming_distance",
    "items_from_ingest_manifest",
]
