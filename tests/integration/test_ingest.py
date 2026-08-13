"""阶段三 pilot：真实视频帧接入采样闭环。"""

from __future__ import annotations

import json
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
        assert record.crop_mode in {"center", "random"}
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


def test_generate_with_frames_manifest_preserves_source(video_dir: Path) -> None:
    from subtitle_dataset.cli import main

    video = video_dir / "src.mp4"
    make_synthetic_video(video)
    outdir = video_dir / "frames_src"
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
    generated = video_dir / "generated_src"
    assert (
        main(
            [
                "generate",
                "--clean",
                str(outdir / "frames"),
                "--frames-manifest",
                str(outdir / "manifest.json"),
                "--config",
                str(SAMPLING_CONFIG),
                "--outdir",
                str(generated),
                "--n",
                "3",
            ]
        )
        == 0
    )
    frames_manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
    generated_manifest = json.loads((generated / "manifest.json").read_text(encoding="utf-8"))
    frame_indices = {frame["native_frame_index"] for frame in frames_manifest["frames"]}
    for sample in generated_manifest["samples"]:
        source = sample["source"]
        assert source is not None
        assert source["video_sha256"] == frames_manifest["video_sha256"]
        assert source["native_frame_index"] in frame_indices
        assert source["platform"] == "unknown"
        assert source["time_base"] == frames_manifest["probe"]["video"]["time_base"]
        assert sample["transform"]["target_size"] == [1280, 720]
        assert sample["build"]["ffmpeg_version"] == frames_manifest["ffmpeg_version"]
        assert sample["build"]["seed"] == sample["sample_seed"]
        assert sample["build"]["renderer_version"]


def test_generate_with_split_map(video_dir: Path) -> None:
    from subtitle_dataset.cli import main

    video = video_dir / "split.mp4"
    make_synthetic_video(video)
    frames_out = video_dir / "frames_split"
    assert (
        main(
            [
                "extract-frames",
                "--video",
                str(video),
                "--config",
                str(INGEST_CONFIG),
                "--outdir",
                str(frames_out),
            ]
        )
        == 0
    )
    dedup_out = video_dir / "dedup"
    assert (
        main(
            [
                "dedup",
                "--manifests",
                str(frames_out / "manifest.json"),
                "--outdir",
                str(dedup_out),
            ]
        )
        == 0
    )
    split_out = video_dir / "splits"
    split_config = REPO_ROOT / "configs" / "splits" / "default.json"
    assert (
        main(
            [
                "split",
                "--clusters",
                str(dedup_out / "clusters.json"),
                "--config",
                str(split_config),
                "--outdir",
                str(split_out),
            ]
        )
        == 0
    )
    item_splits = json.loads((split_out / "item_splits.json").read_text(encoding="utf-8"))
    generated = video_dir / "generated_split"
    assert (
        main(
            [
                "generate",
                "--clean",
                str(frames_out / "frames"),
                "--frames-manifest",
                str(frames_out / "manifest.json"),
                "--split-map",
                str(split_out / "item_splits.json"),
                "--config",
                str(SAMPLING_CONFIG),
                "--outdir",
                str(generated),
                "--n",
                "2",
            ]
        )
        == 0
    )
    frames_manifest = json.loads((frames_out / "manifest.json").read_text(encoding="utf-8"))
    generated_manifest = json.loads((generated / "manifest.json").read_text(encoding="utf-8"))
    video_sha256 = frames_manifest["video_sha256"]
    for index, sample in enumerate(generated_manifest["samples"]):
        record = frames_manifest["frames"][index % 2]
        expected = item_splits[f"frame:{video_sha256}:{record['uri']}"]
        assert sample["split"] == expected
