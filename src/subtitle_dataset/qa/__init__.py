"""自动质检与分布报告。"""

from .distribution import (
    DEFAULT_DURATION_TARGETS,
    BucketStat,
    DistributionReportConfig,
    DurationTarget,
    FrameDistributionReport,
    SampleDistributionReport,
    StatRange,
    build_frame_distribution,
    build_sample_distribution,
)
from .pairing import PairingCheck, check_strict_pairing

__all__ = [
    "BucketStat",
    "DEFAULT_DURATION_TARGETS",
    "DistributionReportConfig",
    "DurationTarget",
    "FrameDistributionReport",
    "PairingCheck",
    "SampleDistributionReport",
    "StatRange",
    "build_frame_distribution",
    "build_sample_distribution",
    "check_strict_pairing",
]
