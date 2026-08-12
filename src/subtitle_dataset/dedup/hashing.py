"""图像感知哈希：用于近重复去重（§8.1）。"""

from __future__ import annotations

from typing import Protocol

import numpy as np
from PIL import Image


class ImageHasher(Protocol):
    def hash(self, image: Image.Image) -> str: ...


class DifferenceHash:
    """64 位差异哈希：缩放到 (size+1) x size 灰度，比较相邻列像素。"""

    def __init__(self, size: int = 8) -> None:
        self._size = size

    def hash(self, image: Image.Image) -> str:
        gray = image.convert("L").resize(
            (self._size + 1, self._size),
            Image.Resampling.LANCZOS,
        )
        pixels = np.asarray(gray, dtype=np.int16)
        bits = (pixels[:, 1:] > pixels[:, :-1]).flatten()
        value = 0
        for bit in bits:
            value = (value << 1) | int(bit)
        return f"{value:016x}"


def hamming_distance(a: str, b: str) -> int:
    """两个十六进制感知哈希的汉明距离（位数差）。"""
    return (int(a, 16) ^ int(b, 16)).bit_count()
