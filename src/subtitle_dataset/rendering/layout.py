"""字幕文本布局：字体加载、分行与多行排版。"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

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
    polygon_local: tuple[tuple[float, float], ...] | None = None


@dataclass(frozen=True)
class BarSpec:
    color: tuple[int, int, int, int]
    padding_x: int
    padding_y: int
    corner_radius: int


def compose_lines(
    line_images: list[Image.Image],
    *,
    align: TextAlign,
    line_spacing_px: int,
    background_bar: BarSpec | None = None,
) -> ComposedBlock:
    """按对齐方式和行距把多行图层排成一块，并裁剪到可见 alpha 边界。"""
    if not line_images:
        raise ValueError("没有可排版的行")
    pad_x = background_bar.padding_x if background_bar is not None else 0
    pad_y = background_bar.padding_y if background_bar is not None else 0
    block_w = max(im.width for im in line_images) + 2 * pad_x
    block_h = (
        sum(im.height for im in line_images) + line_spacing_px * (len(line_images) - 1) + 2 * pad_y
    )
    canvas = Image.new("RGBA", (block_w, block_h), (0, 0, 0, 0))
    line_bboxes: list[tuple[int, int, int, int]] = []
    positions: list[tuple[int, int]] = []
    y = 0
    for im in line_images:
        if align is TextAlign.LEFT:
            x = 0
        elif align is TextAlign.RIGHT:
            x = block_w - im.width
        else:
            x = (block_w - im.width) // 2
        positions.append((x, pad_y + y))
        line_bboxes.append((x, pad_y + y, x + im.width, pad_y + y + im.height))
        y += im.height + line_spacing_px
    if background_bar is not None:
        ImageDraw.Draw(canvas).rounded_rectangle(
            (0, 0, block_w, block_h),
            radius=background_bar.corner_radius,
            fill=background_bar.color,
        )
    for im, (x, y) in zip(line_images, positions, strict=True):
        canvas.alpha_composite(im, (x, y))

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


def rotate_block(block: ComposedBlock, angle_degrees: float) -> ComposedBlock:
    """绕块中心旋转字幕层（自建仿射，保证 polygon 与像素一致）。"""
    if angle_degrees == 0:
        return block
    layer = block.layer
    width, height = layer.size
    center_x, center_y = width / 2.0, height / 2.0
    radians = math.radians(angle_degrees)
    cos_a, sin_a = math.cos(radians), math.sin(radians)

    def _rotate(px: float, py: float) -> tuple[float, float]:
        dx, dy = px - center_x, py - center_y
        return (
            dx * cos_a - dy * sin_a + center_x,
            dx * sin_a + dy * cos_a + center_y,
        )

    corners = [_rotate(0, 0), _rotate(width, 0), _rotate(width, height), _rotate(0, height)]
    min_x = math.floor(min(point[0] for point in corners))
    min_y = math.floor(min(point[1] for point in corners))
    max_x = math.ceil(max(point[0] for point in corners))
    max_y = math.ceil(max(point[1] for point in corners))
    out_width = max_x - min_x
    out_height = max_y - min_y
    matrix = (
        cos_a,
        -sin_a,
        center_x - cos_a * center_x + sin_a * center_y - min_x,
        sin_a,
        cos_a,
        center_y - sin_a * center_x - cos_a * center_y - min_y,
    )
    rotated = layer.transform(
        (out_width, out_height),
        Image.Transform.AFFINE,
        matrix,
        resample=Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )
    new_line_bboxes: list[tuple[int, int, int, int]] = []
    for x0, y0, x1, y1 in block.line_bboxes:
        points = [_rotate(x0, y0), _rotate(x1, y0), _rotate(x1, y1), _rotate(x0, y1)]
        ax0 = min(point[0] for point in points)
        ay0 = min(point[1] for point in points)
        ax1 = max(point[0] for point in points)
        ay1 = max(point[1] for point in points)
        new_line_bboxes.append(
            (
                round(ax0 - min_x),
                round(ay0 - min_y),
                round(ax1 - min_x),
                round(ay1 - min_y),
            )
        )
    polygon_local = tuple((point[0] - min_x, point[1] - min_y) for point in corners)
    xs = [point[0] for point in polygon_local]
    ys = [point[1] for point in polygon_local]
    effect_bbox = (
        math.floor(min(xs)),
        math.floor(min(ys)),
        math.ceil(max(xs)),
        math.ceil(max(ys)),
    )
    return ComposedBlock(
        layer=rotated,
        line_bboxes=tuple(new_line_bboxes),
        effect_bbox=effect_bbox,
        polygon_local=polygon_local,
    )
