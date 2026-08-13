"""字幕事件模型：时间语义与事件 ID。"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from subtitle_dataset.contracts import TimeBase
from subtitle_dataset.rendering.config import RenderStyle
from subtitle_dataset.sampling import (
    SubtitleEventSpec,
    compute_event_id,
    ms_to_pts,
    representative_time_ms,
)


def _style() -> RenderStyle:
    return RenderStyle(
        font_ids=["noto-sans-cjk-sc"],
        font_size_h_ratio=0.04,
        letter_spacing_px=0.0,
        line_spacing_px=0.0,
        stroke_width_h_ratio=0.0,
        opacity=1.0,
        fill_color=(255, 255, 255, 255),
        stroke_color=(0, 0, 0, 255),
        shadow_color=(0, 0, 0, 255),
    )


def _spec(**overrides: Any) -> SubtitleEventSpec:
    base: dict[str, Any] = {
        "event_id": "e1",
        "text_raw": "你好",
        "text_normalized": "你好",
        "style": _style(),
        "start_native_frame": 10,
        "end_native_frame_exclusive": 40,
        "native_duration_frames": 30,
        "start_pts": 1000,
        "end_pts_exclusive": 4000,
        "start_time_ms": 1000,
        "end_time_ms": 4000,
        "duration_ms": 3000,
        "frames_per_event": 1,
    }
    base.update(overrides)
    return SubtitleEventSpec(**base)


def test_valid_event_roundtrip() -> None:
    event = _spec()
    assert event.duration_ms == event.end_time_ms - event.start_time_ms
    assert (
        event.native_duration_frames == event.end_native_frame_exclusive - event.start_native_frame
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"duration_ms": 2000},
        {"end_time_ms": 1000},
        {"end_pts_exclusive": 1000},
        {"end_native_frame_exclusive": 10},
        {"native_duration_frames": 29},
    ],
)
def test_invalid_event_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _spec(**overrides)


def test_ms_to_pts() -> None:
    assert ms_to_pts(1500, TimeBase(num=1, den=30000)) == 45000
    assert ms_to_pts(1000, TimeBase(num=1, den=1000)) == 1000


def test_representative_time_ms() -> None:
    assert representative_time_ms(1000, 3000, 3, 0) == 1000
    assert representative_time_ms(1000, 3000, 3, 1) == 2500
    assert representative_time_ms(1000, 3000, 3, 2) == 4000
    assert representative_time_ms(1000, 3000, 1, 0) == 2500


def test_event_id_deterministic() -> None:
    first = compute_event_id(seed=1, text_raw="你好", style_seed=5, start_time_ms=1000)
    second = compute_event_id(seed=1, text_raw="你好", style_seed=5, start_time_ms=1000)
    changed = compute_event_id(seed=1, text_raw="你好", style_seed=5, start_time_ms=2000)
    assert first == second
    assert first != changed
