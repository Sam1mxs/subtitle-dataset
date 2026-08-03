"""字幕文本布局：字体加载、分行与多行排版。"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageFont

from .config import TextAlign

_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def load_font(font_path: str, size_px: int) -> ImageFont.FreeTypeFont:
    """加载字体并缓存（同一路径+字号只加载一次）。"""
    key = (font_path, size_px)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(font_path, size_px)
    return _FONT_CACHE[key]


def split_lines(text: str) -> list[str]:
    """按换行符分行，不允许空行（空行会破坏行布局语义）。"""
    lines = text.split("\n")
    if any(not line.strip() for line in lines):
        raise ValueError("字幕文本不允许存在空行")
    return lines


@dataclass(frozen=True)
class ComposedBlock:
    """多行字幕排版结果。

    ``layer`` 已裁剪到 alpha 边界，左上角坐标为 (0, 0)；``line_bboxes``
    与 ``effect_bbox`` 均以裁剪后的 layer 为坐标系。
    """

    layer: Image.Image
    line_bboxes: tuple[tuple[int, int, int, int], ...]
    effect_bbox: tuple[int, int, int, int]


def compose_lines(
    line_images: list[Image.Image],
    *,
    align: TextAlign,
    line_spacing_px: int,
) -> ComposedBlock:
    """按对齐方式和行距把多行图层排成一块，并裁剪到可见 alpha 边界。"""
    if not line_images:
        raise ValueError("没有可排版的行")
    block_w = max(im.width for im in line_images)
    block_h = sum(im.height for im in line_images) + line_spacing_px * (len(line_images) - 1)
    canvas = Image.new("RGBA", (block_w, block_h), (0, 0, 0, 0))
    line_bboxes: list[tuple[int, int, int, int]] = []
    y = 0
    for im in line_images:
        if align is TextAlign.LEFT:
            x = 0
        elif align is TextAlign.RIGHT:
            x = block_w - im.width
        else:
            x = (block_w - im.width) // 2
        canvas.alpha_composite(im, (x, y))
        line_bboxes.append((x, y, x + im.width, y + im.height))
        y += im.height + line_spacing_px

    bbox = canvas.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("字幕层没有任何可见像素")
    layer = canvas.crop(bbox)
    ox, oy = bbox[:2]
    shifted = tuple((x0 - ox, y0 - oy, x1 - ox, y1 - oy) for (x0, y0, x1, y1) in line_bboxes)
    return ComposedBlock(
        layer=layer,
        line_bboxes=shifted,
        effect_bbox=(0, 0, layer.width, layer.height),
    )
