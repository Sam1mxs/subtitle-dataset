"""字幕渲染：layout、RGBA 图层与合成。"""

from .config import RGBA, Center, RenderConfig, RenderStyle, TextAlign
from .fonts import (
    FontCoverageError,
    FontLicense,
    FontLicenseError,
    FontRecord,
    FontRegistry,
    FontResolution,
)
from .renderer import RENDERER_VERSION, PillowRenderer, RenderResult

__all__ = [
    "Center",
    "FontCoverageError",
    "FontLicense",
    "FontLicenseError",
    "FontRecord",
    "FontRegistry",
    "FontResolution",
    "PillowRenderer",
    "RGBA",
    "RENDERER_VERSION",
    "RenderConfig",
    "RenderResult",
    "RenderStyle",
    "TextAlign",
]
