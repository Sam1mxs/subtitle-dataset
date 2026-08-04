"""ffprobe 元数据探测。"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from subtitle_dataset.media import probe_video
from tests.helpers import make_synthetic_video


@pytest.fixture(scope="module")
def video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("ffmpeg") is None:
        pytest.skip("缺少 ffmpeg")
    path = tmp_path_factory.mktemp("video") / "test.mp4"
    make_synthetic_video(path)
    return path


def test_probe_fields(video: Path) -> None:
    probe = probe_video(video)
    assert probe.video.width == 640
    assert probe.video.height == 360
    assert probe.video.avg_frame_rate.avg_num == 30
    assert probe.video.avg_frame_rate.avg_den == 1
    assert probe.video.is_vfr is False
    assert len(probe.sha256) == 64
    assert probe.duration_seconds is not None
    assert 2.8 < probe.duration_seconds < 3.2
    assert probe.video.time_base.num > 0
    assert probe.video.time_base.den > 0
    assert probe.video.pix_fmt
