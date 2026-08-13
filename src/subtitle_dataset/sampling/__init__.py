"""文本、样式、位置与时长采样。"""

from .config import (
    BackgroundBarDistribution,
    ColorOption,
    DurationBucket,
    DurationDistribution,
    FadeDistribution,
    FontOption,
    PositionDistribution,
    RangeF,
    RangeOption,
    RotationDistribution,
    SamplingConfig,
    ShadowDistribution,
    StyleDistribution,
    weighted_choice,
)
from .durations import DurationSampler
from .events import (
    SubtitleEventSpec,
    compute_event_id,
    fade_factor,
    ms_to_pts,
    representative_time_ms,
)
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
    "BackgroundBarDistribution",
    "DurationBucket",
    "DurationDistribution",
    "DurationSampler",
    "FadeDistribution",
    "FontOption",
    "GeneratedSample",
    "GeneratedSampleRecord",
    "PositionDistribution",
    "PositionSampler",
    "RangeF",
    "RangeOption",
    "RotationDistribution",
    "SampleSampler",
    "SamplingConfig",
    "SamplingExhaustedError",
    "ShadowDistribution",
    "StyleDistribution",
    "StyleSampler",
    "SubtitleEventSpec",
    "TextCorpus",
    "TextSampler",
    "compute_event_id",
    "fade_factor",
    "ms_to_pts",
    "representative_time_ms",
    "weighted_choice",
]
