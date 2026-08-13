"""保持比例的居中裁剪。"""

from __future__ import annotations

import random

from PIL import Image

from subtitle_dataset.media import CropConfig, CropTarget, crop_and_resize


def _frame(width: int = 640, height: int = 360) -> Image.Image:
    return Image.new("RGB", (width, height), (10, 20, 30))


def test_full_frame_when_aspect_matches() -> None:
    config = CropConfig(targets=[CropTarget(aspect_w=16, aspect_h=9, target=(1280, 720))])
    image, result = crop_and_resize(_frame(), config, random.Random(0))
    assert result.crop_xywh == (0, 0, 640, 360)
    assert image.size == (1280, 720)


def test_center_crop_square() -> None:
    config = CropConfig(targets=[CropTarget(aspect_w=1, aspect_h=1, target=(360, 360))])
    image, result = crop_and_resize(_frame(), config, random.Random(0))
    assert result.crop_xywh == (140, 0, 500, 360)
    assert image.size == (360, 360)


def test_center_crop_portrait_target() -> None:
    config = CropConfig(targets=[CropTarget(aspect_w=9, aspect_h=16, target=(360, 640))])
    image, result = crop_and_resize(_frame(), config, random.Random(0))
    x0, y0, x1, y1 = result.crop_xywh
    assert y1 - y0 == 360
    assert image.size == (360, 640)


def test_random_crop_within_bounds_and_aspect() -> None:
    config = CropConfig(
        mode="random",
        targets=[CropTarget(aspect_w=1, aspect_h=1, target=(360, 360))],
    )
    frame = _frame()
    for seed in range(10):
        _, result = crop_and_resize(frame, config, random.Random(seed))
        x0, y0, x1, y1 = result.crop_xywh
        assert 0 <= x0 < x1 <= 640
        assert 0 <= y0 < y1 <= 360
        assert (x1 - x0, y1 - y0) == (360, 360)
        assert result.crop_mode == "random"


def test_random_crop_varies_when_room_exists() -> None:
    config = CropConfig(
        mode="random",
        targets=[CropTarget(aspect_w=1, aspect_h=1, target=(360, 360))],
    )
    frame = _frame()
    offsets = {
        crop_and_resize(frame, config, random.Random(seed))[1].crop_xywh for seed in range(10)
    }
    assert len(offsets) > 1


def test_mixed_ratio_controls_strategy() -> None:
    frame = _frame()
    target = CropTarget(aspect_w=1, aspect_h=1, target=(360, 360))
    all_random = CropConfig(mode="mixed", random_ratio=1.0, targets=[target])
    modes = {
        crop_and_resize(frame, all_random, random.Random(seed))[1].crop_mode for seed in range(20)
    }
    assert modes == {"random"}
    all_center = CropConfig(mode="mixed", random_ratio=0.0, targets=[target])
    modes = {
        crop_and_resize(frame, all_center, random.Random(seed))[1].crop_mode for seed in range(20)
    }
    assert modes == {"center"}


def test_full_frame_no_move_space() -> None:
    config = CropConfig(
        mode="mixed",
        random_ratio=1.0,
        targets=[CropTarget(aspect_w=16, aspect_h=9, target=(1280, 720))],
    )
    _, result = crop_and_resize(_frame(), config, random.Random(0))
    assert result.crop_xywh == (0, 0, 640, 360)
    assert result.crop_mode == "random"
