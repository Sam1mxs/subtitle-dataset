"""像素标注：从 alpha 层计算 bbox。"""

from __future__ import annotations

from PIL import Image


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    """返回 alpha 可见区域 bbox（半开区间 [x0, y0, x1, y1)）。"""
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("图像没有任何可见 alpha 像素")
    return bbox
