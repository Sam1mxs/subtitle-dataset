"""渲染增强：背景条、旋转 polygon、透明度覆盖。"""

from __future__ import annotations

import pytest

from subtitle_dataset.rendering import BackgroundBar, PillowRenderer, RenderResult
from subtitle_dataset.rendering.config import RenderConfig, RenderStyle
from tests.helpers import make_clean_image


def _style(**overrides: object) -> RenderStyle:
    base = RenderStyle(
        font_ids=["noto-sans-cjk-sc"],
        font_size_h_ratio=0.05,
        letter_spacing_px=0.0,
        line_spacing_px=0.0,
        stroke_width_h_ratio=0.0,
        opacity=1.0,
        fill_color=(255, 255, 255, 255),
        stroke_color=(0, 0, 0, 255),
        shadow_color=(0, 0, 0, 255),
    )
    return base.model_copy(update=overrides)


def _render(
    style: RenderStyle,
    *,
    opacity_override: float | None = None,
) -> RenderResult:
    config = RenderConfig(text="今天晚上一起吃饭", style=style)
    if opacity_override is not None:
        config.opacity_override = opacity_override
    return PillowRenderer().render(make_clean_image(), config)


def test_background_bar_expands_effect_bbox() -> None:
    plain = _render(_style())
    barred = _render(
        _style(
            background_bar=BackgroundBar(
                color=(0, 0, 0, 200),
                padding_x_h_ratio=0.01,
                padding_y_h_ratio=0.01,
                corner_radius_h_ratio=0.01,
            )
        )
    )
    assert barred.alpha_mask.getbbox() != plain.alpha_mask.getbbox()
    assert barred.effect_bbox_xyxy != plain.effect_bbox_xyxy
    # 背景条区域 alpha 非零（文本 bbox 之外）
    assert barred.alpha_mask.getextrema()[1] == 255


def test_rotation_produces_polygon_within_bbox() -> None:
    plain = _render(_style())
    rotated = _render(_style(rotation_degrees=8.0))
    assert plain.polygon == []
    assert len(rotated.polygon) == 4
    xs = [point[0] for point in rotated.polygon]
    ys = [point[1] for point in rotated.polygon]
    ex0, ey0, ex1, ey1 = rotated.effect_bbox_xyxy
    assert ex0 <= min(xs) <= max(xs) <= ex1
    assert ey0 <= min(ys) <= max(ys) <= ey1


def test_opacity_override_scales_alpha() -> None:
    half = _render(_style(), opacity_override=0.5)
    histogram = half.alpha_mask.histogram()
    max_alpha = max(index for index, count in enumerate(histogram) if count)
    assert 120 <= max_alpha <= 136


def test_rotation_out_of_bounds_rejected() -> None:
    from PIL import Image

    clean = Image.new("RGB", (120, 160), (40, 44, 56))
    config = RenderConfig(
        text="今天晚上一起吃饭",
        style=_style(font_size_h_ratio=0.4, rotation_degrees=25.0),
        center=(0.5, 0.75),
    )
    with pytest.raises(ValueError, match="越界"):
        PillowRenderer().render(clean, config)
