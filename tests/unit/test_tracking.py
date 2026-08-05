"""跨帧跟踪与角色判定。"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from subtitle_dataset.filtering import (
    FilteringConfig,
    FrameDetection,
    HeuristicTextRegionDetector,
    TextRole,
    assign_geometric_roles,
    track_boxes,
)
from tests.helpers import NOTO_FONT


def _make_frames(count: int = 6) -> list[Image.Image]:
    font = ImageFont.truetype(str(NOTO_FONT), 20)
    frames: list[Image.Image] = []
    for index in range(count):
        image = Image.new("RGB", (320, 180), (30, 34, 46))
        draw = ImageDraw.Draw(image)
        line = ["第一句字幕", "第二句字幕"][index % 2]
        draw.text(
            (160, 155),
            line,
            font=font,
            fill=(255, 255, 255),
            anchor="mm",
            stroke_width=1,
            stroke_fill=(0, 0, 0),
        )
        draw.text((300, 12), "台标", font=font, fill=(180, 180, 180), anchor="mm")
        frames.append(image)
    return frames


def test_tracking_classifies_subtitle_and_watermark() -> None:
    config = FilteringConfig()
    detector = HeuristicTextRegionDetector(config)
    frames = _make_frames()
    detections = [
        FrameDetection(
            native_frame_index=index,
            pts=index,
            timestamp_ms=index * 33,
            boxes=assign_geometric_roles(
                detector.detect(frame),
                width=frame.width,
                height=frame.height,
                config=config,
            ),
        )
        for index, frame in enumerate(frames)
    ]
    persistent = track_boxes(detections, frames, config)
    roles = {box.role for box in persistent}
    assert TextRole.SUBTITLE in roles
    assert TextRole.WATERMARK in roles

    subtitle = next(box for box in persistent if box.role is TextRole.SUBTITLE)
    assert subtitle.content_switched
    watermark = next(box for box in persistent if box.role is TextRole.WATERMARK)
    assert not watermark.content_switched
    assert watermark.persistence >= config.persistence_ratio
