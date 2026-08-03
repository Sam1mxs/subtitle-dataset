"""alpha mask 与 inpainting mask 生成。"""

from __future__ import annotations

from PIL import Image, ImageFilter


def alpha_to_inpaint_mask(alpha: Image.Image, dilation_px: int) -> Image.Image:
    """由 alpha mask 生成二值 inpaint mask，可按像素数膨胀（方形核）。"""
    mask = alpha.point(lambda a: 255 if a > 0 else 0)
    if dilation_px > 0:
        mask = mask.filter(ImageFilter.MaxFilter(2 * dilation_px + 1))
        mask = mask.point(lambda v: 255 if v > 0 else 0)
    return mask
