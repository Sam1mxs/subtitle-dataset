"""字幕文本、样式与标注信息。"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from .base import NonNegativeInt, PositiveInt, Sha256Hex, UnitFloat

#: 像素 bbox [x0, y0, x1, y1)，半开区间
BboxXyxy = tuple[NonNegativeInt, NonNegativeInt, PositiveInt, PositiveInt]
#: 归一化 bbox [x0, y0, x1, y1)，半开区间
BboxNormalized = tuple[UnitFloat, UnitFloat, UnitFloat, UnitFloat]
#: 多边形顶点 (x, y)，旋转或透视字幕使用
Point = tuple[float, float]
Polygon = list[Point]


class SubtitleStyle(BaseModel):
    """字幕渲染样式；比例参数均相对于最终图像高度。"""

    font_sha256: Sha256Hex
    font_size_h_ratio: float = Field(gt=0)
    letter_spacing: float = Field(ge=0)
    line_spacing: float = Field(ge=0)
    stroke_width_h_ratio: float = Field(ge=0)
    opacity: UnitFloat
    style_seed: NonNegativeInt = Field(description="该样本字幕样式采样的随机种子")


class SubtitleEvent(BaseModel):
    """一个字幕事件的文本、时间与标注。"""

    event_id: str
    text_raw: str
    text_normalized: str
    start_native_frame: NonNegativeInt
    end_native_frame_exclusive: NonNegativeInt
    start_pts: int
    end_pts_exclusive: int
    start_time_ms: NonNegativeInt
    end_time_ms: NonNegativeInt
    duration_ms: PositiveInt
    native_duration_frames: PositiveInt
    bbox_xyxy: BboxXyxy
    bbox_normalized: BboxNormalized
    line_bboxes_xyxy: list[BboxXyxy] = Field(default_factory=list)
    polygon: Polygon = Field(default_factory=list)
    alpha_mask_uri: str
    inpaint_mask_uri: str
    style: SubtitleStyle

    @model_validator(mode="after")
    def _check_time_invariants(self) -> SubtitleEvent:
        if self.end_native_frame_exclusive <= self.start_native_frame:
            raise ValueError("end_native_frame_exclusive 必须大于 start_native_frame")
        if self.native_duration_frames != self.end_native_frame_exclusive - self.start_native_frame:
            raise ValueError("native_duration_frames 与原生帧边界不一致")
        if self.end_pts_exclusive <= self.start_pts:
            raise ValueError("end_pts_exclusive 必须大于 start_pts")
        if self.end_time_ms <= self.start_time_ms:
            raise ValueError("end_time_ms 必须大于 start_time_ms")
        if self.duration_ms != self.end_time_ms - self.start_time_ms:
            raise ValueError("duration_ms 必须等于 end_time_ms - start_time_ms")
        return self

    @model_validator(mode="after")
    def _check_bbox_invariants(self) -> SubtitleEvent:
        x0, y0, x1, y1 = self.bbox_xyxy
        if x1 <= x0 or y1 <= y0:
            raise ValueError("bbox_xyxy 必须满足 x1 > x0 且 y1 > y0（半开区间）")
        nx0, ny0, nx1, ny1 = self.bbox_normalized
        if nx1 <= nx0 or ny1 <= ny0:
            raise ValueError("bbox_normalized 必须满足 x1 > x0 且 y1 > y0（半开区间）")
        return self
