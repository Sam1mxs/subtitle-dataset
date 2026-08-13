"""裁剪与缩放：保持原始几何比例，不拉伸。"""

from __future__ import annotations

import random
from typing import Literal

from PIL import Image
from pydantic import BaseModel, Field

from subtitle_dataset.contracts import PositiveInt


class CropTarget(BaseModel):
    aspect_w: PositiveInt
    aspect_h: PositiveInt
    target: tuple[PositiveInt, PositiveInt]
    weight: float = Field(gt=0, default=1.0)


class CropConfig(BaseModel):
    mode: Literal["center", "random", "mixed"] = "center"
    targets: list[CropTarget] = Field(min_length=1)
    seed: int = 0
    random_ratio: float = Field(ge=0.0, le=1.0, default=0.2)


class CropResult(BaseModel):
    crop_xywh: tuple[int, int, int, int]
    target_size: tuple[int, int]
    crop_mode: Literal["center", "random"]


def crop_and_resize(
    frame: Image.Image,
    config: CropConfig,
    rng: random.Random,
) -> tuple[Image.Image, CropResult]:
    """按目标宽高比裁剪（center/random/mixed）并缩放到目标尺寸，保持几何比例。"""
    target = rng.choices(config.targets, weights=[t.weight for t in config.targets], k=1)[0]
    if config.mode == "random" or (config.mode == "mixed" and rng.random() < config.random_ratio):
        crop_mode = "random"
        crop_xywh = _random_crop_rect(
            frame.width,
            frame.height,
            target.aspect_w,
            target.aspect_h,
            rng,
        )
    else:
        crop_mode = "center"
        crop_xywh = _center_crop_rect(
            frame.width,
            frame.height,
            target.aspect_w,
            target.aspect_h,
        )
    cropped = frame.crop(crop_xywh)
    resized = cropped.resize(target.target, Image.Resampling.LANCZOS)
    return resized, CropResult(
        crop_xywh=crop_xywh,
        target_size=target.target,
        crop_mode=crop_mode,
    )


def _center_crop_rect(
    frame_width: int,
    frame_height: int,
    aspect_w: int,
    aspect_h: int,
) -> tuple[int, int, int, int]:
    """计算保持目标宽高比的居中裁剪矩形（半开区间）。"""
    source_ratio = frame_width / frame_height
    target_ratio = aspect_w / aspect_h
    if target_ratio > source_ratio:
        crop_width = frame_width
        crop_height = max(round(frame_width / target_ratio), 1)
    else:
        crop_height = frame_height
        crop_width = max(round(frame_height * target_ratio), 1)
    if crop_width > frame_width or crop_height > frame_height:
        raise ValueError(
            f"目标宽高比 {aspect_w}:{aspect_h} 无法在 {frame_width}x{frame_height} 内居中裁剪"
        )
    x0 = (frame_width - crop_width) // 2
    y0 = (frame_height - crop_height) // 2
    return (x0, y0, x0 + crop_width, y0 + crop_height)


def _random_crop_rect(
    frame_width: int,
    frame_height: int,
    aspect_w: int,
    aspect_h: int,
    rng: random.Random,
) -> tuple[int, int, int, int]:
    """保持目标宽高比的约束内均匀随机裁剪矩形（半开区间）。"""
    target_ratio = aspect_w / aspect_h
    source_ratio = frame_width / frame_height
    if target_ratio >= source_ratio:
        crop_width = frame_width
        crop_height = max(round(frame_width / target_ratio), 1)
        x0 = 0
        y0 = rng.randrange(0, max(frame_height - crop_height + 1, 1))
    else:
        crop_height = frame_height
        crop_width = max(round(frame_height * target_ratio), 1)
        y0 = 0
        x0 = rng.randrange(0, max(frame_width - crop_width + 1, 1))
    return (x0, y0, x0 + crop_width, y0 + crop_height)
