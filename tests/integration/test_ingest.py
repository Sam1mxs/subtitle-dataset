"""阶段三 pilot：真实视频帧接入采样闭环。"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from tests.helpers import make_synthetic_video

from subtitle_dataset.media import IngestConfig
from subtitle_dataset.workflows import IngestReport, run_ingest

REPO_ROOT = Path(__file__).resolve().parents[2]
INGEST_CONFIG = REPO_ROOT / "configs" / "ingest" / "default.json"
SAMPLING_CONFIG = REPO_ROOT / "configs" / "sampling" / "default.json"


@pytest.fixture(scope="module")
def video_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("ffmpeg") is None:
        pytest.skip("缺少 ffmpeg")
    return tmp_path_factory.mktemp("video")


def test_run_ingest_on_synthetic_video(video_dir: Path) -> None:
    video = video_dir / "test.mp4"
    make_synthetic_video(video)
    config = IngestConfig.model_validate_json(INGEST_CONFIG.read_text(encoding="utf-8"))
    outdir = video_dir / "out"
    report = run_ingest(video, config, outdir)
    assert len(report.scenes) == 2
    assert len(report.frames) == 2
    assert report.failures == []
    for record in report.frames:
        assert (outdir / record.uri).exists()
        assert record.target_size == (1280, 720)
        assert record.crop_xywh == (0, 0, 640, 360)
        assert record.image_sha256
    reloaded = IngestReport.model_validate_json(
        (outdir / "manifest.json").read_text(encoding="utf-8")
    )
    assert reloaded.video_sha256 == report.video_sha256
    assert (outdir / "probe.json").exists()
    assert (outdir / "failures.json").exists()


def test_cli_extract_frames_and_generate_from_dir(video_dir: Path) -> None:
    from subtitle_dataset.cli import main

    video = video_dir / "test2.mp4"
    make_synthetic_video(video)
    outdir = video_dir / "frames_out"
    assert (
        main(
            [
                "extract-frames",
                "--video",
                str(video),
                "--config",
                str(INGEST_CONFIG),
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )
    frames_dir = outdir / "frames"
    assert len(list(frames_dir.glob("*.png"))) == 2

    generated = video_dir / "generated"
    assert (
        main(
            [
                "generate",
                "--clean",
                str(frames_dir),
                "--config",
                str(SAMPLING_CONFIG),
                "--outdir",
                str(generated),
                "--n",
                "4",
            ]
        )
        == 0
    )
    assert len(list((generated / "samples").iterdir())) == 4
