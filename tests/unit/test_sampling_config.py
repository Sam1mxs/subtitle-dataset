"""采样配置校验。"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from subtitle_dataset.sampling import SamplingConfig


def _valid() -> dict[str, Any]:
    return {
        "durations": {"buckets": [{"min_ms": 130, "max_ms": 270}]},
        "style": {
            "fonts": [{"font_id": "noto-sans-cjk-sc"}],
            "font_size_h_ratio_range": {"min": 0.02, "max": 0.06},
            "letter_spacing_px_range": {"min": 0.0, "max": 2.0},
            "line_spacing_px_range": {"min": 0.0, "max": 8.0},
            "stroke_width_h_ratio_range": {"min": 0.0, "max": 0.006},
            "opacity_range": {"min": 0.85, "max": 1.0},
            "align_weights": {"center": 1.0},
            "fill_colors": [{"color": [255, 255, 255, 255]}],
            "stroke_colors": [{"color": [0, 0, 0, 255]}],
        },
    }


def test_valid_config_roundtrip() -> None:
    config = SamplingConfig.model_validate(_valid())
    assert config.seed == 0
    assert config.single_line_prob == 0.75


def test_bucket_requires_min_lt_max() -> None:
    data = _valid()
    data["durations"]["buckets"] = [{"min_ms": 300, "max_ms": 300}]
    with pytest.raises(ValidationError, match="min_ms < max_ms"):
        SamplingConfig.model_validate(data)


def test_unknown_align_rejected() -> None:
    data = _valid()
    data["style"]["align_weights"] = {"middle": 1.0}
    with pytest.raises(ValidationError, match="未知对齐方式"):
        SamplingConfig.model_validate(data)


def test_inverted_range_rejected() -> None:
    data = _valid()
    data["style"]["opacity_range"] = {"min": 0.9, "max": 0.5}
    with pytest.raises(ValidationError):
        SamplingConfig.model_validate(data)
