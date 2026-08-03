"""样本级数据契约。"""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from .base import Sha256Hex, Split
from .build import BuildInfo
from .hashing import compute_sample_id
from .image import ImageInfo, Transform
from .source import SourceInfo
from .subtitle import SubtitleEvent

#: 字幕可见区域中心允许的纵向范围（相对最终图像高度）
VISIBLE_CENTER_Y_MIN = 0.60
VISIBLE_CENTER_Y_MAX = 0.90
#: 归一化坐标与像素坐标互相换算的容差（示例 JSON 保留 3 位小数）
NORMALIZED_TOLERANCE = 0.002


class Sample(BaseModel):
    """一条严格对齐的训练样本。"""

    sample_id: Sha256Hex
    source: SourceInfo
    image: ImageInfo
    subtitle: SubtitleEvent
    transform: Transform
    build: BuildInfo
    split: Split

    @model_validator(mode="after")
    def _check_image_and_crop(self) -> Sample:
        if (self.image.width, self.image.height) != self.transform.target_size:
            raise ValueError("image 尺寸必须与 transform.target_size 一致")
        return self

    @model_validator(mode="after")
    def _check_bbox_within_image(self) -> Sample:
        x0, y0, x1, y1 = self.subtitle.bbox_xyxy
        if not (0 <= x0 < x1 <= self.image.width and 0 <= y0 < y1 <= self.image.height):
            raise ValueError("subtitle.bbox_xyxy 必须完整位于图像内部")
        return self

    @model_validator(mode="after")
    def _check_normalized_bbox(self) -> Sample:
        pixel = self.subtitle.bbox_xyxy
        norm = self.subtitle.bbox_normalized
        expected = (
            pixel[0] / self.image.width,
            pixel[1] / self.image.height,
            pixel[2] / self.image.width,
            pixel[3] / self.image.height,
        )
        for actual, exp in zip(norm, expected, strict=True):
            if abs(actual - exp) > NORMALIZED_TOLERANCE:
                raise ValueError(
                    f"bbox_normalized {norm} 与像素坐标 {pixel} 不一致（期望 {expected}）"
                )
        return self

    @model_validator(mode="after")
    def _check_visible_center_band(self) -> Sample:
        _, y0, _, y1 = self.subtitle.bbox_xyxy
        center_y = (y0 + y1) / 2 / self.image.height
        if not VISIBLE_CENTER_Y_MIN <= center_y <= VISIBLE_CENTER_Y_MAX:
            raise ValueError(
                f"字幕可见区域中心纵坐标 {center_y:.3f} 超出 "
                f"[{VISIBLE_CENTER_Y_MIN}, {VISIBLE_CENTER_Y_MAX}]"
            )
        return self

    @model_validator(mode="after")
    def _check_sample_id(self) -> Sample:
        expected = compute_sample_id(
            dataset_version=self.build.dataset_version,
            video_sha256=self.source.video_sha256,
            native_frame_index=self.source.native_frame_index,
            pts=self.source.pts,
            crop_xywh=self.transform.crop_xywh,
            event_id=self.subtitle.event_id,
            style_seed=self.subtitle.style.style_seed,
        )
        if self.sample_id != expected:
            raise ValueError(f"sample_id 与确定性计算不一致：{expected}")
        return self
