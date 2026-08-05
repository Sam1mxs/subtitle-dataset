"""视频级字幕检测（合成视频）。"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
from pathlib import Path

import pytest
from tests.helpers import make_text_video

from subtitle_dataset.filtering import FilteringConfig, VideoSubtitleFilter

FILTERING_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "filtering" / "default.json"


@pytest.fixture(scope="module")
def video_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("ffmpeg") is None:
        pytest.skip("缺少 ffmpeg")
    return tmp_path_factory.mktemp("video")


@pytest.fixture(scope="module")
def config() -> FilteringConfig:
    return FilteringConfig.model_validate_json(FILTERING_CONFIG.read_text(encoding="utf-8"))


def test_clean_video_no_subtitle(video_dir: Path, config: FilteringConfig) -> None:
    path = video_dir / "clean.mp4"
    make_text_video(path)
    report = VideoSubtitleFilter(config).analyze(path)
    assert not report.subtitle_present
    assert report.subtitle_boxes == []
    assert report.watermark_boxes == []


def test_subtitle_video_detected(video_dir: Path, config: FilteringConfig) -> None:
    path = video_dir / "subtitle.mp4"
    make_text_video(path, subtitle_lines=["第一句", "第二句", "第三句"])
    report = VideoSubtitleFilter(config).analyze(path)
    assert report.subtitle_present
    assert report.subtitle_boxes
    box = report.subtitle_boxes[0]
    _, y0, _, y1 = box.normalized
    assert (y0 + y1) / 2 >= 0.55
    assert box.content_switched


def test_watermark_video_detected(video_dir: Path, config: FilteringConfig) -> None:
    path = video_dir / "watermark.mp4"
    make_text_video(path, watermark_text="测试台标")
    report = VideoSubtitleFilter(config).analyze(path)
    assert not report.subtitle_present
    assert report.watermark_boxes
    assert not report.watermark_boxes[0].content_switched


def test_mixed_video_roles(video_dir: Path, config: FilteringConfig) -> None:
    path = video_dir / "mixed.mp4"
    make_text_video(
        path,
        subtitle_lines=["第一句", "第二句"],
        watermark_text="台标",
        scene_text="场景文字",
    )
    report = VideoSubtitleFilter(config).analyze(path)
    assert report.subtitle_present
    assert report.watermark_boxes
    assert report.scene_text_boxes


def test_cli_detect_subtitles(video_dir: Path, config: FilteringConfig) -> None:
    from subtitle_dataset.cli import main

    path = video_dir / "cli.mp4"
    make_text_video(path, subtitle_lines=["第一句", "第二句"])
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        assert (
            main(
                [
                    "detect-subtitles",
                    "--video",
                    str(path),
                    "--config",
                    str(FILTERING_CONFIG),
                ]
            )
            == 0
        )
    data = json.loads(buffer.getvalue())
    assert data["subtitle_present"] is True
