"""单帧文字区域检测与几何角色。"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from subtitle_dataset.filtering import (
    FilteringConfig,
    HeuristicTextRegionDetector,
    TextRole,
    assign_geometric_roles,
)
from tests.helpers import NOTO_FONT


def _image_with_text(
    text: str,
    xy: tuple[int, int],
    *,
    size: tuple[int, int] = (640, 360),
    font_size: int = 28,
) -> Image.Image:
    image = Image.new("RGB", size, (30, 34, 46))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(NOTO_FONT), font_size)
    draw.text(
        xy,
        text,
        font=font,
        fill=(255, 255, 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0),
    )
    return image


def test_detector_finds_text_box() -> None:
    image = _image_with_text("今天晚上一起吃饭", (160, 300))
    boxes = HeuristicTextRegionDetector(FilteringConfig()).detect(image)
    assert boxes
    x0, y0, x1, y1 = boxes[0].xyxy
    assert y0 < 320 < y1
    assert x1 - x0 > 100


def test_detector_blank_image_has_no_boxes() -> None:
    image = Image.new("RGB", (640, 360), (30, 34, 46))
    assert HeuristicTextRegionDetector(FilteringConfig()).detect(image) == []


def test_geometric_roles_subtitle_and_scene_text() -> None:
    config = FilteringConfig()
    detector = HeuristicTextRegionDetector(config)
    subtitle_image = _image_with_text("字幕", (300, 310))
    subtitle_boxes = assign_geometric_roles(
        detector.detect(subtitle_image),
        width=subtitle_image.width,
        height=subtitle_image.height,
        config=config,
    )
    assert subtitle_boxes[0].role is TextRole.SUBTITLE

    scene_image = _image_with_text("场景文字", (300, 160))
    scene_boxes = assign_geometric_roles(
        detector.detect(scene_image),
        width=scene_image.width,
        height=scene_image.height,
        config=config,
    )
    assert scene_boxes[0].role is TextRole.SCENE_TEXT


def test_geometric_role_watermark_in_corner() -> None:
    config = FilteringConfig()
    image = _image_with_text("台标", (560, 20), font_size=18)
    boxes = assign_geometric_roles(
        HeuristicTextRegionDetector(config).detect(image),
        width=image.width,
        height=image.height,
        config=config,
    )
    assert boxes[0].role is TextRole.WATERMARK
