"""严格配对渲染器：clean image + RenderConfig → rendered / alpha / inpaint mask / bbox。"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from subtitle_dataset.annotations.masks import alpha_to_inpaint_mask
from subtitle_dataset.contracts import config_sha256

from .config import RenderConfig
from .fonts import FontRegistry
from .layer import render_line_layer
from .layout import compose_lines, load_font, split_lines

RENDERER_VERSION = "0.1.0"


@dataclass(frozen=True)
class RenderResult:
    rendered: Image.Image
    alpha_mask: Image.Image
    inpaint_mask: Image.Image
    effect_bbox_xyxy: tuple[int, int, int, int]
    line_bboxes_xyxy: list[tuple[int, int, int, int]]
    config_sha256: str
    font_id: str
    font_sha256: str
    fallback_used: bool
    missing_chars: dict[str, list[str]]


class PillowRenderer:
    """基于 Pillow 的严格配对渲染器。

    渲染流程：渲染透明字幕层 → 根据 alpha 计算真实可见尺寸 → 对齐到目标中心 →
    与 clean image 合成 → 生成 alpha/inpaint mask 与 bbox。
    """

    def __init__(self, registry: FontRegistry | None = None) -> None:
        self._registry = registry or FontRegistry.load()

    def render(self, clean: Image.Image, config: RenderConfig) -> RenderResult:
        width, height = clean.size
        style = config.style
        resolution = self._registry.resolve(
            config.text,
            style.font_ids,
            require_ml_training=config.require_ml_training_fonts,
        )
        font = load_font(resolution.font_path, round(style.font_size_h_ratio * height))

        line_images = [
            render_line_layer(line, font, style=style, image_height=height)
            for line in split_lines(config.text)
        ]
        block = compose_lines(
            line_images,
            align=style.align,
            line_spacing_px=round(style.line_spacing_px),
        )

        bx0, by0, bx1, by1 = block.effect_bbox
        center_x = round(config.center[0] * width)
        center_y = round(config.center[1] * height)
        paste_x = center_x - (bx0 + bx1) // 2
        paste_y = center_y - (by0 + by1) // 2

        if not (bx0 + paste_x >= 0 and bx1 + paste_x <= width):
            raise ValueError(
                f"字幕层水平越界: paste_x={paste_x}, bbox=({bx0},{bx1}), 图像宽={width}"
            )
        if not (by0 + paste_y >= 0 and by1 + paste_y <= height):
            raise ValueError(
                f"字幕层垂直越界: paste_y={paste_y}, bbox=({by0},{by1}), 图像高={height}"
            )

        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        canvas.alpha_composite(block.layer, (paste_x, paste_y))
        if style.opacity < 1.0:
            alpha = canvas.getchannel("A").point(lambda a: round(a * style.opacity))
            canvas.putalpha(alpha)

        composed = Image.alpha_composite(clean.convert("RGBA"), canvas)
        rendered = composed.convert("RGB")

        alpha_mask = canvas.getchannel("A")
        inpaint_mask = alpha_to_inpaint_mask(alpha_mask, config.inpaint_dilation_px)
        line_bboxes = [
            (x0 + paste_x, y0 + paste_y, x1 + paste_x, y1 + paste_y)
            for (x0, y0, x1, y1) in block.line_bboxes
        ]
        effect_bbox = (bx0 + paste_x, by0 + paste_y, bx1 + paste_x, by1 + paste_y)

        return RenderResult(
            rendered=rendered,
            alpha_mask=alpha_mask,
            inpaint_mask=inpaint_mask,
            effect_bbox_xyxy=effect_bbox,
            line_bboxes_xyxy=line_bboxes,
            config_sha256=self._config_sha256(config),
            font_id=resolution.font_id,
            font_sha256=resolution.font_sha256,
            fallback_used=resolution.fallback_used,
            missing_chars=resolution.missing_chars,
        )

    @staticmethod
    def _config_sha256(config: RenderConfig) -> str:
        """配置哈希：配置中只含字体 ID，不含任何存储路径。"""
        return config_sha256(config.model_dump(mode="json"))
