"""分布报告统计与目标对比。"""

from __future__ import annotations

from typing import Any

from subtitle_dataset.qa import DurationTarget, build_frame_distribution, build_sample_distribution


def _sample_record(
    index: int,
    duration_ms: int,
    *,
    font_id: str = "noto-sans-cjk-sc",
    lines: int = 1,
) -> dict[str, Any]:
    return {
        "sample_index": index,
        "sample_seed": index,
        "duration_ms": duration_ms,
        "text": "第一句" if lines == 1 else "第一句\n第二句",
        "style": {
            "font_size_h_ratio": 0.04,
            "align": "center",
            "fill_color": [255, 255, 255, 255],
        },
        "center": [0.5, 0.75],
        "font_id": font_id,
        "config_sha256": f"{index:064x}",
        "pairing_ok": True,
    }


def test_sample_distribution_counts() -> None:
    records = [
        _sample_record(0, 700),
        _sample_record(1, 800, lines=2),
        _sample_record(2, 1500, font_id="msyh"),
        _sample_record(3, 3000),
    ]
    report = build_sample_distribution(records)
    assert report.n_samples == 4
    assert report.pairing_ok == 4
    assert report.fonts == {"noto-sans-cjk-sc": 3, "msyh": 1}
    assert report.line_counts == {1: 3, 2: 1}
    assert sum(bucket.count for bucket in report.duration_buckets) == 4
    assert report.duration_out_of_bucket == 0
    assert report.unique_config_hashes == 4


def test_sample_distribution_deviation_detected() -> None:
    records = [_sample_record(i, 1500) for i in range(10)]
    targets = [
        DurationTarget(min_ms=1030, max_ms=2000, weight=1.0),
        DurationTarget(min_ms=130, max_ms=270, weight=1.0),
    ]
    report = build_sample_distribution(records, targets=targets, tolerance=0.15)
    assert report.duration_buckets[0].within_tolerance is False
    assert "偏差" in report.verdict


def test_frame_distribution() -> None:
    manifest = {
        "scenes": [
            {"index": 0, "duration_ms": 1500},
            {"index": 1, "duration_ms": 1500},
        ],
        "frames": [
            {
                "target_size": [1280, 720],
                "image_sha256": "a" * 64,
                "timestamp_ms": 100,
                "pts": 100,
            },
            {
                "target_size": [1280, 720],
                "image_sha256": "b" * 64,
                "timestamp_ms": 1600,
                "pts": 500,
            },
        ],
    }
    report = build_frame_distribution(manifest)
    assert report.n_frames == 2
    assert report.n_scenes == 2
    assert report.target_sizes == {"1280x720": 2}
    assert report.aspect_ratios == {"16:9": 2}
    assert report.unique_image_hashes == 2
    assert report.timestamp_span_ms == 1500
    assert report.pts_monotonic
