"""严格配对 QA 检查。"""

from __future__ import annotations

from PIL import Image, ImageDraw

from subtitle_dataset.qa import check_strict_pairing


def _rgb(
    width: int = 100,
    height: int = 60,
    color: tuple[int, int, int] = (10, 20, 30),
) -> Image.Image:
    return Image.new("RGB", (width, height), color)


def _mask(width: int = 100, height: int = 60) -> Image.Image:
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    draw.rectangle([30, 20, 69, 49], fill=255)
    return image


def test_identical_images_pass() -> None:
    check = check_strict_pairing(_rgb(), _rgb(), _mask())
    assert check.ok
    assert check.max_abs_diff_outside_mask == 0
    assert check.changed_bbox_xyxy is None


def test_change_inside_mask_passes() -> None:
    clean = _rgb()
    rendered = clean.copy()
    ImageDraw.Draw(rendered).rectangle([30, 20, 69, 49], fill=(20, 30, 40))
    check = check_strict_pairing(
        clean,
        rendered,
        _mask(),
        effect_bbox=(30, 20, 70, 50),
    )
    assert check.ok


def test_change_outside_mask_fails() -> None:
    clean = _rgb()
    rendered = clean.copy()
    ImageDraw.Draw(rendered).rectangle([0, 0, 9, 9], fill=(20, 30, 40))
    check = check_strict_pairing(clean, rendered, _mask())
    assert not check.ok
    assert check.max_abs_diff_outside_mask > 0


def test_change_outside_effect_bbox_fails() -> None:
    clean = _rgb()
    rendered = clean.copy()
    ImageDraw.Draw(rendered).rectangle([30, 20, 39, 29], fill=(20, 30, 40))
    check = check_strict_pairing(
        clean,
        rendered,
        _mask(),
        effect_bbox=(10, 10, 20, 20),
    )
    assert not check.ok
    assert not check.changes_inside_effect_bbox


def test_size_mismatch_fails() -> None:
    check = check_strict_pairing(_rgb(width=100), _rgb(width=101), _mask())
    assert not check.ok
    assert not check.same_size
