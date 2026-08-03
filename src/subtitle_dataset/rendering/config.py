"""字幕渲染配置模型。"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

from subtitle_dataset.contracts import Sha256Hex, UnitFloat

Channel = Annotated[int, Field(ge=0, le=255)]
#: RGBA 颜色
RGBA = tuple[Channel, Channel, Channel, Channel]
#: 归一化坐标（相对图像宽高）
Center = tuple[UnitFloat, UnitFloat]


class TextAlign(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class RenderStyle(BaseModel):
    """字幕渲染样式；相对图像高度的比例参数在渲染时换算为像素。"""

    font_path: str = Field(min_length=1)
    font_sha256: Sha256Hex
    font_size_h_ratio: float = Field(gt=0, lt=1)
    letter_spacing_px: float = Field(ge=0)
    line_spacing_px: float = Field(ge=0)
    stroke_width_h_ratio: float = Field(ge=0)
    opacity: UnitFloat
    align: TextAlign = TextAlign.CENTER
    fill_color: RGBA = (255, 255, 255, 255)
    stroke_color: RGBA = (0, 0, 0, 255)
    shadow_color: RGBA = (0, 0, 0, 255)
    shadow_offset_xy: tuple[float, float] = (0.0, 0.0)
    shadow_blur_px: float = Field(default=0.0, ge=0)


class RenderConfig(BaseModel):
    """一次字幕渲染的完整配置。"""

    text: str = Field(min_length=1)
    style: RenderStyle
    center: Center = (0.5, 0.75)
    inpaint_dilation_px: int = Field(default=3, ge=0)
