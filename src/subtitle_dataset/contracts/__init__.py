"""数据契约：样本、清单、失败记录与确定性哈希。"""

from .base import (
    FrameRate,
    NonNegativeInt,
    PositiveInt,
    Sha256Hex,
    Split,
    StageStatus,
    TimeBase,
    UnitFloat,
)
from .build import BuildInfo
from .hashing import canonical_dumps, compute_sample_id, config_sha256, sha256_hex
from .image import ImageInfo, Transform
from .manifest import FailureRecord, SampleManifest
from .sample import NORMALIZED_TOLERANCE, VISIBLE_CENTER_Y_MAX, VISIBLE_CENTER_Y_MIN, Sample
from .source import SourceInfo
from .subtitle import BboxNormalized, BboxXyxy, Polygon, SubtitleEvent, SubtitleStyle

__all__ = [
    "BboxNormalized",
    "BboxXyxy",
    "BuildInfo",
    "FailureRecord",
    "FrameRate",
    "ImageInfo",
    "NORMALIZED_TOLERANCE",
    "NonNegativeInt",
    "Polygon",
    "PositiveInt",
    "Sample",
    "SampleManifest",
    "Sha256Hex",
    "SourceInfo",
    "Split",
    "StageStatus",
    "SubtitleEvent",
    "SubtitleStyle",
    "TimeBase",
    "Transform",
    "UnitFloat",
    "VISIBLE_CENTER_Y_MAX",
    "VISIBLE_CENTER_Y_MIN",
    "canonical_dumps",
    "compute_sample_id",
    "config_sha256",
    "sha256_hex",
]
