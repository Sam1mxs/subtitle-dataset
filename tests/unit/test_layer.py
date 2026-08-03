"""RGBA 字幕图层渲染。"""

from __future__ import annotations

from typing import Any

from PIL import ImageFont

from subtitle_dataset.rendering.config import RenderStyle
from subtitle_dataset.rendering.layer import render_line_layer

DEJAVU_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _style(**overrides: Any) -> RenderStyle:
    base: dict[str, Any] = {
        "font_ids": ["dejavu-sans"],
        "font_size_h_ratio": 0.05,
        "letter_spacing_px": 0.0,
        "line_spacing_px": 0.0,
        "stroke_width_h_ratio": 0.0,
        "opacity": 1.0,
        "fill_color": (255, 255, 255, 255),
        "stroke_color": (0, 0, 0, 255),
        "shadow_color": (0, 0, 0, 255),
        "shadow_offset_xy": (0.0, 0.0),
        "shadow_blur_px": 0.0,
    }
    base.update(overrides)
    return RenderStyle(**base)


def test_render_line_has_visible_alpha() -> None:
    font = ImageFont.truetype(DEJAVU_FONT, 32)
    layer = render_line_layer("Hello", font, style=_style(), image_height=640)
    assert layer.mode == "RGBA"
    assert layer.getchannel("A").getbbox() == (0, 0, layer.width, layer.height)


def test_stroke_expands_bbox() -> None:
    font = ImageFont.truetype(DEJAVU_FONT, 32)
    plain = render_line_layer("Hello", font, style=_style(), image_height=640)
    stroked = render_line_layer(
        "Hello", font, style=_style(stroke_width_h_ratio=0.02), image_height=640
    )
    assert stroked.width > plain.width
    assert stroked.height > plain.height


def test_shadow_expands_bbox() -> None:
    font = ImageFont.truetype(DEJAVU_FONT, 32)
    plain = render_line_layer("Hello", font, style=_style(), image_height=640)
    shadowed = render_line_layer(
        "Hello", font, style=_style(shadow_offset_xy=(10.0, 8.0)), image_height=640
    )
    assert shadowed.width > plain.width
    assert shadowed.height > plain.height
