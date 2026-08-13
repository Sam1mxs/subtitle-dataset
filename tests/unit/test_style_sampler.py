"""样式采样。"""

from __future__ import annotations

import random

from subtitle_dataset.rendering.config import TextAlign
from subtitle_dataset.sampling import (
    BackgroundBarDistribution,
    RangeF,
    RotationDistribution,
    StyleDistribution,
    StyleSampler,
)


def _distribution() -> StyleDistribution:
    return StyleDistribution.model_validate(
        {
            "fonts": [
                {
                    "font_id": "noto-sans-cjk-sc",
                    "weight": 1.0,
                    "size_h_ratio_range": {"min": 0.03, "max": 0.04},
                }
            ],
            "font_size_h_ratio_range": {"min": 0.02, "max": 0.06},
            "letter_spacing_px_range": {"min": 0.0, "max": 2.0},
            "line_spacing_px_range": {"min": 0.0, "max": 8.0},
            "stroke_width_h_ratio_range": {"min": 0.0, "max": 0.006},
            "opacity_range": {"min": 0.85, "max": 1.0},
            "align_weights": {"center": 0.8, "left": 0.1, "right": 0.1},
            "fill_colors": [
                {"color": [255, 255, 255, 255], "weight": 1.0},
                {"color": [255, 240, 200, 255], "weight": 0.2},
            ],
            "stroke_colors": [{"color": [0, 0, 0, 255], "weight": 1.0}],
            "shadow": {
                "probability": 1.0,
                "offset_xy_max": [3.0, 2.0],
                "blur_px_range": {"min": 0.0, "max": 2.0},
            },
        }
    )


def test_style_sampler_respects_ranges() -> None:
    sampler = StyleSampler(_distribution(), random.Random(11))
    styles = [sampler.sample() for _ in range(50)]
    assert all(0.03 <= s.font_size_h_ratio <= 0.04 for s in styles)
    assert all(0.0 <= s.letter_spacing_px <= 2.0 for s in styles)
    assert all(0.0 <= s.stroke_width_h_ratio <= 0.006 for s in styles)
    assert all(0.85 <= s.opacity <= 1.0 for s in styles)
    assert all(s.align in TextAlign for s in styles)
    assert all(s.fill_color in [(255, 255, 255, 255), (255, 240, 200, 255)] for s in styles)
    assert all(s.font_ids == ["noto-sans-cjk-sc"] for s in styles)


def test_style_sampler_deterministic() -> None:
    first = [StyleSampler(_distribution(), random.Random(5)).sample() for _ in range(5)]
    second = [StyleSampler(_distribution(), random.Random(5)).sample() for _ in range(5)]
    assert [s.model_dump() for s in first] == [s.model_dump() for s in second]


def test_shadow_probability_one_always_on() -> None:
    sampler = StyleSampler(_distribution(), random.Random(2))
    offsets = [sampler.sample().shadow_offset_xy for _ in range(20)]
    assert any(offset != (0.0, 0.0) for offset in offsets)


def test_background_bar_and_rotation_ranges() -> None:
    dist = _distribution().model_copy(
        update={
            "background_bar": BackgroundBarDistribution(
                probability=1.0,
                padding_x_h_ratio_range=RangeF(min=0.01, max=0.01),
                padding_y_h_ratio_range=RangeF(min=0.01, max=0.01),
                corner_radius_h_ratio_range=RangeF(min=0.01, max=0.01),
            ),
            "rotation": RotationDistribution(probability=1.0, max_degrees=5.0),
        }
    )
    sampler = StyleSampler(dist, random.Random(1))
    styles = [sampler.sample() for _ in range(10)]
    assert all(style.background_bar is not None for style in styles)
    assert all(-5.0 <= style.rotation_degrees <= 5.0 for style in styles)
    assert any(style.rotation_degrees != 0.0 for style in styles)
