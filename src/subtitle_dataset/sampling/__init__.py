"""文本、样式、位置与时长采样。"""

from .config import (
    ColorOption,
    DurationBucket,
    DurationDistribution,
    FontOption,
    PositionDistribution,
    RangeF,
    RangeOption,
    SamplingConfig,
    ShadowDistribution,
    StyleDistribution,
    weighted_choice,
)
from .durations import DurationSampler
from .pipeline import (
    GeneratedSample,
    GeneratedSampleRecord,
    SampleSampler,
    SamplingExhaustedError,
)
from .positions import PositionSampler
from .styles import StyleSampler
from .texts import TextCorpus, TextSampler

__all__ = [
    "ColorOption",
    "DurationBucket",
    "DurationDistribution",
    "DurationSampler",
    "FontOption",
    "GeneratedSample",
    "GeneratedSampleRecord",
    "PositionDistribution",
    "PositionSampler",
    "RangeF",
    "RangeOption",
    "SampleSampler",
    "SamplingConfig",
    "SamplingExhaustedError",
    "ShadowDistribution",
    "StyleDistribution",
    "StyleSampler",
    "TextCorpus",
    "TextSampler",
    "weighted_choice",
]
