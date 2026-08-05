"""文字/字幕检测配置。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FilteringConfig(BaseModel):
    """启发式字幕检测阈值；先用合成视频默认值，后续按真实短剧校准。"""

    sample_frames: int = Field(ge=2, default=30)
    edge_threshold: int = Field(ge=1, le=255, default=40)
    morph_close_size: int = Field(ge=3, default=5)
    min_box_height: int = Field(ge=1, default=6)
    min_box_width: int = Field(ge=1, default=20)
    row_band_min_density: float = Field(gt=0.0, le=1.0, default=0.02)
    column_min_density: float = Field(gt=0.0, le=1.0, default=0.10)
    merge_row_gap_px: int = Field(ge=0, default=4)
    merge_col_gap_px: int = Field(ge=0, default=8)
    subtitle_region_y0: float = Field(ge=0.0, le=1.0, default=0.55)
    iou_threshold: float = Field(gt=0.0, le=1.0, default=0.4)
    persistence_ratio: float = Field(gt=0.0, le=1.0, default=0.6)
    position_std_tolerance: float = Field(gt=0.0, default=0.05)
    content_switch_iou_threshold: float = Field(gt=0.0, le=1.0, default=0.75)
    watermark_max_area_ratio: float = Field(gt=0.0, le=1.0, default=0.06)
    watermark_corner_ratio: float = Field(ge=0.0, le=1.0, default=0.25)
