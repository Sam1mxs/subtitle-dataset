"""字幕渲染配置模型。"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

from subtitle_dataset.contracts import UnitFloat

Channel = Annotated[int, Field(ge=0, le=255)]
#: RGBA 颜色
RGBA = tuple[Channel, Channel, Channel, Channel]
#: 归一化坐标（相对图像宽高）
Center = tuple[UnitFloat, UnitFloat]


class TextAlign(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class BackgroundBar(BaseModel):
    """字幕背景条（半透明圆角矩形，画在文字下方）。"""

    color: RGBA = (0, 0, 0, 180)
    padding_x_h_ratio: float = Field(ge=0.0, default=0.01)
    padding_y_h_ratio: float = Field(ge=0.0, default=0.008)
    corner_radius_h_ratio: float = Field(ge=0.0, default=0.01)


class RenderStyle(BaseModel):
    """字幕渲染样式；相对图像高度的比例参数在渲染时换算为像素。"""

    font_ids: list[str] = Field(min_length=1, description="候选字体（按优先级，第一个为主字体）")
    language: str | None = Field(default=None, description="文本语言（raqm 塑形用，如 zh/ar）")
    direction: str | None = Field(default=None, description="文本方向（ltr/rtl，None=自动）")
    rotation_degrees: float = Field(default=0.0, description="字幕块旋转角度（度）")
    background_bar: BackgroundBar | None = Field(default=None)
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
    opacity_override: UnitFloat | None = Field(
        default=None,
        description="覆盖 style.opacity（淡入淡出逐帧用）",
    )
    require_ml_training_fonts: bool = Field(
        default=False,
        description="为 True 时只允许登记表中 ml_training=True 的字体",
    )
