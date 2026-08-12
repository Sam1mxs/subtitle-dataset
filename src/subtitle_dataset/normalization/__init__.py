"""文本规范化与文字判定（§10.5）。"""

from .normalizer import (
    DEFAULT_VERSION,
    NormalizationResult,
    TextNormalizer,
    UnknownNormalizationError,
)
from .rules import RULES
from .scripts import detect_script

__all__ = [
    "DEFAULT_VERSION",
    "NormalizationResult",
    "RULES",
    "TextNormalizer",
    "UnknownNormalizationError",
    "detect_script",
]
