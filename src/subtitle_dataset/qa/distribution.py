"""分布报告：样本/帧分布统计与目标分布对比。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from math import gcd
from typing import Any

from pydantic import BaseModel, Field


class DurationTarget(BaseModel):
    """时长分桶目标（qa 独立定义，避免与 sampling 循环依赖）。"""

    min_ms: int = Field(ge=0)
    max_ms: int = Field(gt=0)
    weight: float = Field(gt=0, default=1.0)


DEFAULT_DURATION_TARGETS = [
    DurationTarget(min_ms=130, max_ms=270, weight=1.0),
    DurationTarget(min_ms=300, max_ms=500, weight=1.5),
    DurationTarget(min_ms=530, max_ms=1000, weight=2.0),
    DurationTarget(min_ms=1030, max_ms=2000, weight=1.5),
    DurationTarget(min_ms=2030, max_ms=3000, weight=0.8),
    DurationTarget(min_ms=3030, max_ms=4000, weight=0.4),
]


class StatRange(BaseModel):
    min: float
    max: float
    mean: float


class BucketStat(BaseModel):
    bucket_min_ms: int
    bucket_max_ms: int
    count: int
    actual_ratio: float
    target_ratio: float | None = None
    deviation: float | None = None
    within_tolerance: bool | None = None


class SampleDistributionReport(BaseModel):
    n_samples: int
    duration_buckets: list[BucketStat]
    duration_out_of_bucket: int
    fonts: dict[str, int]
    font_size_h_ratio: StatRange
    center_x: StatRange
    center_y: StatRange
    line_counts: dict[int, int]
    aligns: dict[str, int]
    fill_colors: dict[str, int]
    unique_config_hashes: int
    pairing_ok: int
    verdict: str


class FrameDistributionReport(BaseModel):
    n_frames: int
    n_scenes: int
    target_sizes: dict[str, int]
    aspect_ratios: dict[str, int]
    unique_image_hashes: int
    scene_duration_ms: StatRange
    timestamp_span_ms: int
    pts_monotonic: bool


class DistributionReportConfig(BaseModel):
    tolerance: float = Field(gt=0.0, le=1.0, default=0.15)
    min_samples: int = Field(ge=1, default=5)
    duration_targets: list[DurationTarget] | None = None


def build_sample_distribution(
    records: Sequence[Mapping[str, Any]],
    *,
    targets: Sequence[DurationTarget] | None = None,
    tolerance: float = 0.15,
    min_samples: int = 5,
) -> SampleDistributionReport:
    """统计生成样本的分布并与目标时长分布对比。"""
    n = len(records)
    durations = [int(record["duration_ms"]) for record in records]
    fonts = Counter(str(record["font_id"]) for record in records)
    font_sizes = [float(record["style"]["font_size_h_ratio"]) for record in records]
    center_x = [float(record["center"][0]) for record in records]
    center_y = [float(record["center"][1]) for record in records]
    line_counts = Counter(str(record["text"]).count("\n") + 1 for record in records)
    aligns = Counter(str(record["style"]["align"]) for record in records)
    fill_colors = Counter(_color_key(record["style"]["fill_color"]) for record in records)
    unique_config = len({str(record["config_sha256"]) for record in records})
    pairing_ok = sum(1 for record in records if record["pairing_ok"])

    distribution = targets if targets is not None else DEFAULT_DURATION_TARGETS
    total_weight = sum(target.weight for target in distribution)
    bucket_stats: list[BucketStat] = []
    for target in distribution:
        count = sum(1 for ms in durations if target.min_ms <= ms <= target.max_ms)
        actual_ratio = count / n if n else 0.0
        if targets is not None:
            target_ratio = target.weight / total_weight
            deviation = actual_ratio - target_ratio
            bucket_stats.append(
                BucketStat(
                    bucket_min_ms=target.min_ms,
                    bucket_max_ms=target.max_ms,
                    count=count,
                    actual_ratio=actual_ratio,
                    target_ratio=target_ratio,
                    deviation=deviation,
                    within_tolerance=abs(deviation) <= tolerance,
                )
            )
        else:
            bucket_stats.append(
                BucketStat(
                    bucket_min_ms=target.min_ms,
                    bucket_max_ms=target.max_ms,
                    count=count,
                    actual_ratio=actual_ratio,
                )
            )
    out_of_bucket = n - sum(bucket.count for bucket in bucket_stats)

    issues: list[str] = []
    if n < min_samples:
        issues.append(f"样本数 {n} 少于 {min_samples}，分布判定仅供参考")
    if targets is not None:
        for stat in bucket_stats:
            if stat.within_tolerance is False:
                issues.append(
                    f"时长桶 {stat.bucket_min_ms}-{stat.bucket_max_ms}ms 偏差 {stat.deviation:+.3f}"
                )
    verdict = "；".join(issues) if issues else "全部维度在容差内"
    return SampleDistributionReport(
        n_samples=n,
        duration_buckets=bucket_stats,
        duration_out_of_bucket=out_of_bucket,
        fonts=dict(fonts),
        font_size_h_ratio=_stats(font_sizes),
        center_x=_stats(center_x),
        center_y=_stats(center_y),
        line_counts={int(key): value for key, value in line_counts.items()},
        aligns=dict(aligns),
        fill_colors=dict(fill_colors),
        unique_config_hashes=unique_config,
        pairing_ok=pairing_ok,
        verdict=verdict,
    )


def build_frame_distribution(manifest: Mapping[str, Any]) -> FrameDistributionReport:
    """统计 ingest 帧清单：场景、分辨率、宽高比、去重与时间跨度。"""
    frames = manifest.get("frames", [])
    scenes = manifest.get("scenes", [])
    target_sizes = Counter(
        f"{size[0]}x{size[1]}" for size in (frame["target_size"] for frame in frames)
    )
    aspect_ratios = Counter(
        _aspect_label(size[0], size[1]) for size in (frame["target_size"] for frame in frames)
    )
    unique_images = len({frame["image_sha256"] for frame in frames})
    scene_durations = [int(scene["duration_ms"]) for scene in scenes]
    timestamps = [int(frame["timestamp_ms"]) for frame in frames]
    timestamp_span = max(timestamps) - min(timestamps) if timestamps else 0
    pts = [int(frame["pts"]) for frame in frames]
    pts_monotonic = all(a <= b for a, b in zip(pts, pts[1:], strict=False))
    return FrameDistributionReport(
        n_frames=len(frames),
        n_scenes=len(scenes),
        target_sizes=dict(target_sizes),
        aspect_ratios=dict(aspect_ratios),
        unique_image_hashes=unique_images,
        scene_duration_ms=_stats(scene_durations),
        timestamp_span_ms=timestamp_span,
        pts_monotonic=pts_monotonic,
    )


def _stats(values: Sequence[float] | Sequence[int]) -> StatRange:
    if not values:
        return StatRange(min=0.0, max=0.0, mean=0.0)
    floats = [float(value) for value in values]
    return StatRange(
        min=min(floats),
        max=max(floats),
        mean=sum(floats) / len(floats),
    )


def _color_key(color: Sequence[int]) -> str:
    return ",".join(str(channel) for channel in color)


def _aspect_label(width: int, height: int) -> str:
    divisor = gcd(width, height)
    return f"{width // divisor}:{height // divisor}"
