"""原生时间轴。"""

from __future__ import annotations

import pytest

from subtitle_dataset.media import VideoTimeline, probe_video
from tests.helpers import make_synthetic_video


@pytest.fixture(scope="module")
def timeline(tmp_path_factory: pytest.TempPathFactory) -> VideoTimeline:
    path = tmp_path_factory.mktemp("video") / "test.mp4"
    make_synthetic_video(path)
    probe = probe_video(path)
    return VideoTimeline.build(
        path,
        time_base=probe.video.time_base,
        video_sha256=probe.sha256,
    )


def test_timeline_frame_count_and_monotonic(timeline: VideoTimeline) -> None:
    assert 80 <= len(timeline.frames) <= 100
    assert timeline.monotonic_pts
    timestamps = [frame.timestamp_ms for frame in timeline.frames]
    assert timestamps == sorted(timestamps)


def test_timeline_frame_nearest(timeline: VideoTimeline) -> None:
    nearest = timeline.frame_nearest(1.5)
    assert abs(nearest.pts_time_seconds - 1.5) < 0.05
    assert nearest.timestamp_ms == round(nearest.pts_time_seconds * 1000)
