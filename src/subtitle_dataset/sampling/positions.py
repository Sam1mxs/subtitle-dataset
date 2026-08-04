"""字幕位置采样（归一化中心）。"""

from __future__ import annotations

import random

from .config import PositionDistribution, weighted_choice


class PositionSampler:
    """采样可见效果 bbox 中心的归一化坐标。"""

    def __init__(self, distribution: PositionDistribution, rng: random.Random) -> None:
        self._distribution = distribution
        self._rng = rng

    def sample(self) -> tuple[float, float]:
        center_x_range = weighted_choice(
            self._rng,
            [(option.range, option.weight) for option in self._distribution.center_x_ranges],
        )
        center_x = center_x_range.sample(self._rng)
        center_y = self._distribution.center_y_range.sample(self._rng)
        return (center_x, center_y)
