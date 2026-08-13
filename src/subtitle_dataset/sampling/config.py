"""采样配置模型与加权随机工具。"""

from __future__ import annotations

import random
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from subtitle_dataset.contracts import UnitFloat
from subtitle_dataset.filtering.policy import SampleTextPolicy
from subtitle_dataset.rendering.config import RGBA, TextAlign

REPO_ROOT = Path(__file__).resolve().parents[3]


def weighted_choice[T](rng: random.Random, choices: Sequence[tuple[T, float]]) -> T:
    """按权重随机选择；权重必须为正。"""
    if not choices:
        raise ValueError("choices 不能为空")
    total = sum(weight for _, weight in choices)
    r = rng.uniform(0.0, total)
    acc = 0.0
    for item, weight in choices:
        acc += weight
        if r <= acc:
            return item
    return choices[-1][0]


class RangeF(BaseModel):
    """闭区间 [min, max]，用于均匀采样浮点数。"""

    min: float
    max: float

    @model_validator(mode="after")
    def _check_order(self) -> RangeF:
        if self.min > self.max:
            raise ValueError(f"RangeF.min 不能大于 max: {self.min} > {self.max}")
        return self

    def sample(self, rng: random.Random) -> float:
        return rng.uniform(self.min, self.max)


class FontOption(BaseModel):
    font_id: str
    weight: float = Field(gt=0, default=1.0)
    size_h_ratio_range: RangeF | None = None


class ColorOption(BaseModel):
    color: RGBA
    weight: float = Field(gt=0, default=1.0)


class RangeOption(BaseModel):
    range: RangeF
    weight: float = Field(gt=0, default=1.0)


class DurationBucket(BaseModel):
    min_ms: int = Field(ge=0)
    max_ms: int = Field(gt=0)
    weight: float = Field(gt=0, default=1.0)

    @model_validator(mode="after")
    def _check_order(self) -> DurationBucket:
        if self.min_ms >= self.max_ms:
            raise ValueError(f"DurationBucket 需要 min_ms < max_ms: {self.min_ms} >= {self.max_ms}")
        return self


class DurationDistribution(BaseModel):
    buckets: list[DurationBucket] = Field(min_length=1)


class ShadowDistribution(BaseModel):
    probability: UnitFloat = 0.3
    offset_xy_max: tuple[float, float] = (0.0, 0.0)
    blur_px_range: RangeF = RangeF(min=0.0, max=0.0)
    colors: list[ColorOption] | None = None


class BackgroundBarDistribution(BaseModel):
    probability: UnitFloat = 0.3
    colors: list[ColorOption] = Field(default_factory=lambda: [ColorOption(color=(0, 0, 0, 180))])
    padding_x_h_ratio_range: RangeF = RangeF(min=0.005, max=0.015)
    padding_y_h_ratio_range: RangeF = RangeF(min=0.004, max=0.010)
    corner_radius_h_ratio_range: RangeF = RangeF(min=0.005, max=0.015)


class RotationDistribution(BaseModel):
    probability: UnitFloat = 0.15
    max_degrees: float = Field(gt=0.0, default=8.0)


class FadeDistribution(BaseModel):
    probability: UnitFloat = 0.3
    fade_in_ratio_range: RangeF = RangeF(min=0.0, max=0.2)
    fade_out_ratio_range: RangeF = RangeF(min=0.0, max=0.2)


class StyleDistribution(BaseModel):
    """样式分布；所有比例参数均相对最终图像高度。"""

    fonts: list[FontOption] = Field(min_length=1)
    font_size_h_ratio_range: RangeF
    letter_spacing_px_range: RangeF
    line_spacing_px_range: RangeF
    stroke_width_h_ratio_range: RangeF
    opacity_range: RangeF
    align_weights: dict[str, float]
    fill_colors: list[ColorOption] = Field(min_length=1)
    stroke_colors: list[ColorOption] = Field(min_length=1)
    shadow: ShadowDistribution = ShadowDistribution()
    background_bar: BackgroundBarDistribution = BackgroundBarDistribution()
    rotation: RotationDistribution = RotationDistribution()

    @model_validator(mode="after")
    def _check_align_keys(self) -> StyleDistribution:
        invalid = set(self.align_weights) - {align.value for align in TextAlign}
        if invalid:
            raise ValueError(f"align_weights 含未知对齐方式: {sorted(invalid)}")
        return self


class PositionDistribution(BaseModel):
    center_y_range: RangeF = RangeF(min=0.65, max=0.85)
    center_x_ranges: list[RangeOption] = Field(
        default_factory=lambda: [RangeOption(range=RangeF(min=0.45, max=0.55))]
    )


class SamplingConfig(BaseModel):
    """一次采样构建的完整配置。"""

    dataset_version: str = "v1"
    seed: int = 0
    source_platform: str = "unknown"
    max_attempts: int = Field(ge=1, default=20)
    inpaint_dilation_px: int = Field(ge=0, default=3)
    require_ml_training_fonts: bool = True
    corpus_path: str = "assets/texts/sample_corpus.txt"
    single_line_prob: UnitFloat = 0.75
    text_language: str = "zh"
    text_normalization_version: str = "1.0"
    frames_per_event: int = Field(ge=1, le=3, default=1)
    fade: FadeDistribution = Field(default_factory=FadeDistribution)
    text_policy: SampleTextPolicy = Field(default_factory=SampleTextPolicy)
    durations: DurationDistribution
    style: StyleDistribution
    position: PositionDistribution = PositionDistribution()
