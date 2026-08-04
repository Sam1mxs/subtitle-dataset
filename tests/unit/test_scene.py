"""场景切分与代表帧选择。"""

from __future__ import annotations

from pathlib import Path

import pytest

from subtitle_dataset.media import (
    VideoTimeline,
    build_scenes,
    pick_representative_frames,
    probe_video,
)
from tests.helpers import make_synthetic_video


@pytest.fixture(scope="module")
def video_with_timeline(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, float | None, VideoTimeline]:
    path = tmp_path_factory.mktemp("video") / "test.mp4"
    make_synthetic_video(path)
    probe = probe_video(path)
    timeline = VideoTimeline.build(
        path,
        time_base=probe.video.time_base,
        video_sha256=probe.sha256,
    )
    return path, probe.duration_seconds, timeline


def test_scene_split_at_middle(
    video_with_timeline: tuple[Path, float | None, VideoTimeline],
) -> None:
    path, duration, timeline = video_with_timeline
    scenes = build_scenes(
        path,
        timeline,
        threshold=0.35,
        duration_seconds=duration or 3.0,
    )
    assert len(scenes) == 2
    assert abs(scenes[1].start_time_ms - 1500) <= 100


def test_representative_frame_in_scene(
    video_with_timeline: tuple[Path, float | None, VideoTimeline],
) -> None:
    path, duration, timeline = video_with_timeline
    scenes = build_scenes(
        path,
        timeline,
        threshold=0.35,
        duration_seconds=duration or 3.0,
    )
    picks = pick_representative_frames(scenes[0], timeline, 1)
    assert len(picks) == 1
    frame = picks[0]
    assert scenes[0].start_frame <= frame.native_frame_index < scenes[0].end_frame_exclusive
