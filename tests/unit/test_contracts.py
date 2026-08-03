"""数据契约的结构性校验。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from subtitle_dataset.contracts import Sample, SampleManifest
from tests.helpers import set_bbox, valid_sample_dict


def _with_bbox_and_norm(
    data: dict[str, Any], xyxy: list[int], norm: list[float]
) -> dict[str, Any]:
    """直接设置像素 bbox 与归一化 bbox（用于构造边界用例）。"""
    data["subtitle"]["bbox_xyxy"] = xyxy
    data["subtitle"]["bbox_normalized"] = norm
    return data


def test_valid_sample_roundtrip(sample_dict: dict[str, Any]) -> None:
    sample = Sample.model_validate(sample_dict)
    assert sample.sample_id == sample_dict["sample_id"]
    assert sample.split.value == "train"
    assert sample.image.width == 1080


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda d: d.update({"subtitle": {**d["subtitle"], "duration_ms": 1000}}), "duration_ms"),
        (
            lambda d: d.update({"subtitle": {**d["subtitle"], "end_time_ms": 12000}}),
            "end_time_ms 必须大于 start_time_ms",
        ),
        (
            lambda d: d.update({"subtitle": {**d["subtitle"], "end_native_frame_exclusive": 360}}),
            "end_native_frame_exclusive 必须大于 start_native_frame",
        ),
        (
            lambda d: d.update({"subtitle": {**d["subtitle"], "native_duration_frames": 44}}),
            "native_duration_frames 与原生帧边界不一致",
        ),
        (
            lambda d: d.update({"source": {**d["source"], "timestamp_ms": 13000}}),
            "timestamp_ms",
        ),
        (
            lambda d: d.update({"subtitle": {**d["subtitle"], "bbox_xyxy": [500, 100, 100, 200]}}),
            "半开区间",
        ),
        (
            lambda d: d.update(
                {"subtitle": {**d["subtitle"], "bbox_normalized": [0.0, 0.0, 0.5, 0.5]}}
            ),
            "bbox_normalized",
        ),
        (lambda d: set_bbox(d, [100, 100, 500, 300]), "中心纵坐标"),
        (
            lambda d: _with_bbox_and_norm(d, [0, 100, 1081, 300], [0.0, 0.052, 1.0, 0.156]),
            "必须完整位于图像内部",
        ),
        (
            lambda d: d.update({"image": {**d["image"], "width": 720}}),
            "target_size",
        ),
        (
            lambda d: d.update(
                {"subtitle": {**d["subtitle"], "style": {**d["subtitle"]["style"], "opacity": 1.5}}}
            ),
            "opacity",
        ),
        (lambda d: d.update({"sample_id": "0" * 64}), "sample_id"),
        (
            lambda d: d.update(
                {
                    "subtitle": {
                        **d["subtitle"],
                        "style": {**d["subtitle"]["style"], "style_seed": 7},
                    }
                }
            ),
            "sample_id",
        ),
    ],
)
def test_invalid_samples_are_rejected(
    sample_dict: dict[str, Any],
    mutate: Callable[[dict[str, Any]], None],
    match: str,
) -> None:
    mutate(sample_dict)
    with pytest.raises(ValidationError, match=match):
        Sample.model_validate(sample_dict)


def test_manifest_roundtrip(sample_dict: dict[str, Any]) -> None:
    manifest = SampleManifest.model_validate(
        {"dataset_version": "v1", "split": "train", "samples": [sample_dict]}
    )
    assert len(manifest.samples) == 1
    assert manifest.samples[0].sample_id == sample_dict["sample_id"]


def test_fixture_is_schema_complete() -> None:
    data = valid_sample_dict()
    Sample.model_validate(data)
