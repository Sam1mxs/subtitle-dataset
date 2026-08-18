"""独立 RGBA 字幕图层渲染（填充、描边、阴影）。"""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

from .config import RenderStyle

_SAFE_MARGIN = 16

_RAQM_AVAILABLE = features.check("raqm")


def _shaping_kwargs(style: RenderStyle) -> dict[str, Any]:
    """返回塑形参数；Pillow 未编译 raqm 时忽略 language/direction。"""
    kwargs: dict[str, Any] = {}
    if _RAQM_AVAILABLE:
        if style.language is not None:
            kwargs["language"] = style.language
        if style.direction is not None:
            kwargs["direction"] = style.direction
    return kwargs


def render_line_layer(
    line: str,
    font: ImageFont.FreeTypeFont,
    *,
    style: RenderStyle,
    image_height: int,
) -> Image.Image:
    """渲染单行字幕为透明 RGBA 图层，裁剪到 alpha 边界。"""
    stroke_px = round(style.stroke_width_h_ratio * image_height)
    shadow_dx, shadow_dy = style.shadow_offset_xy
    blur_px = style.shadow_blur_px

    ink = font.getbbox(line)
    ink_w = max(ink[2] - ink[0], 1)
    ink_h = max(ink[3] - ink[1], 1)
    width = int(ink_w + 2 * stroke_px + abs(shadow_dx) + round(blur_px * 3) + _SAFE_MARGIN)
    height = int(ink_h + 2 * stroke_px + abs(shadow_dy) + round(blur_px * 3) + _SAFE_MARGIN)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    x0 = (width - ink_w) // 2 - ink[0]
    y0 = (height - ink_h) // 2 - ink[1]

    if shadow_dx != 0 or shadow_dy != 0:
        shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        sdraw.text(
            (x0 + shadow_dx, y0 + shadow_dy),
            line,
            font=font,
            fill=style.shadow_color,
            stroke_width=stroke_px,
            stroke_fill=style.shadow_color,
            letter_spacing=style.letter_spacing_px,
            **_shaping_kwargs(style),
        )
        if blur_px > 0:
            shadow = shadow.filter(ImageFilter.GaussianBlur(blur_px))
        canvas.alpha_composite(shadow)

    draw.text(
        (x0, y0),
        line,
        font=font,
        fill=style.fill_color,
        stroke_width=stroke_px,
        stroke_fill=style.stroke_color,
        letter_spacing=style.letter_spacing_px,
        **_shaping_kwargs(style),
    )

    bbox = canvas.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError(f"行渲染后没有任何可见像素: {line!r}")
    return canvas.crop(bbox)
