"""字幕样式采样。"""

from __future__ import annotations

import random

from subtitle_dataset.rendering.config import RenderStyle, TextAlign

from .config import ColorOption, StyleDistribution, weighted_choice


class StyleSampler:
    """按分布采样 RenderStyle；字号范围支持按字体覆盖。"""

    def __init__(self, distribution: StyleDistribution, rng: random.Random) -> None:
        self._distribution = distribution
        self._rng = rng

    def sample(self) -> RenderStyle:
        dist = self._distribution
        font_option = weighted_choice(self._rng, [(f, f.weight) for f in dist.fonts])
        size_range = font_option.size_h_ratio_range or dist.font_size_h_ratio_range

        shadow = dist.shadow
        shadow_dx = shadow_dy = 0.0
        if self._rng.random() < shadow.probability:
            shadow_dx = self._rng.uniform(0.0, shadow.offset_xy_max[0])
            shadow_dy = self._rng.uniform(0.0, shadow.offset_xy_max[1])
        shadow_colors = shadow.colors or dist.stroke_colors

        return RenderStyle(
            font_ids=[font_option.font_id],
            font_size_h_ratio=size_range.sample(self._rng),
            letter_spacing_px=dist.letter_spacing_px_range.sample(self._rng),
            line_spacing_px=dist.line_spacing_px_range.sample(self._rng),
            stroke_width_h_ratio=dist.stroke_width_h_ratio_range.sample(self._rng),
            opacity=dist.opacity_range.sample(self._rng),
            align=weighted_choice(
                self._rng,
                [(TextAlign(key), weight) for key, weight in dist.align_weights.items()],
            ),
            fill_color=weighted_choice(self._rng, _color_choices(dist.fill_colors)),
            stroke_color=weighted_choice(self._rng, _color_choices(dist.stroke_colors)),
            shadow_color=weighted_choice(self._rng, _color_choices(shadow_colors)),
            shadow_offset_xy=(shadow_dx, shadow_dy),
            shadow_blur_px=shadow.blur_px_range.sample(self._rng),
        )


def _color_choices(options: list[ColorOption]) -> list[tuple[tuple[int, int, int, int], float]]:
    return [(option.color, option.weight) for option in options]
