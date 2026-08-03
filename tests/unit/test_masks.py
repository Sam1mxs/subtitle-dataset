"""alpha → inpaint mask 生成。"""

from __future__ import annotations

from PIL import Image, ImageDraw

from subtitle_dataset.annotations import alpha_to_inpaint_mask


def _alpha_rect(width: int = 40, height: int = 30, margin: int = 10) -> Image.Image:
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    draw.rectangle([margin, margin, width - margin - 1, height - margin - 1], fill=255)
    return image


def _count(mask: Image.Image) -> int:
    return sum(mask.histogram()[1:])


def test_binarized_without_dilation() -> None:
    mask = alpha_to_inpaint_mask(_alpha_rect(), 0)
    hist = mask.histogram()
    assert hist[0] + hist[255] == mask.width * mask.height
    assert _count(mask) == 20 * 10  # 40x30 中 margin=10 的矩形面积为 20x10


def test_mask_covers_alpha_pixels() -> None:
    alpha = _alpha_rect()
    mask = alpha_to_inpaint_mask(alpha, 0)
    assert _count(mask) == _count(alpha)


def test_dilation_expands_mask() -> None:
    alpha = _alpha_rect()
    plain = alpha_to_inpaint_mask(alpha, 0)
    dilated = alpha_to_inpaint_mask(alpha, 3)
    assert _count(dilated) > _count(plain)
