"""布局模块：分行与多行排版。"""

from __future__ import annotations

import pytest
from PIL import Image

from subtitle_dataset.rendering.config import TextAlign
from subtitle_dataset.rendering.layout import compose_lines, split_lines


def _solid_line(width: int, height: int) -> Image.Image:
    return Image.new("RGBA", (width, height), (255, 255, 255, 255))


def test_split_lines_ok() -> None:
    assert split_lines("第一行\n第二行") == ["第一行", "第二行"]


def test_split_lines_rejects_empty() -> None:
    with pytest.raises(ValueError, match="空行"):
        split_lines("a\n\nb")


def test_compose_lines_centered() -> None:
    block = compose_lines(
        [_solid_line(100, 20), _solid_line(60, 20)],
        align=TextAlign.CENTER,
        line_spacing_px=4,
    )
    assert block.layer.size == (100, 44)
    assert block.effect_bbox == (0, 0, 100, 44)
    assert block.line_bboxes[0] == (0, 0, 100, 20)
    assert block.line_bboxes[1] == (20, 24, 80, 44)


def test_compose_lines_left_align() -> None:
    block = compose_lines(
        [_solid_line(100, 20), _solid_line(60, 20)],
        align=TextAlign.LEFT,
        line_spacing_px=0,
    )
    assert block.line_bboxes[1] == (0, 20, 60, 40)
