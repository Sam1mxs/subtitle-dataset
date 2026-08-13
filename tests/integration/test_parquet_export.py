"""Parquet 导出 CLI 端到端。"""

from __future__ import annotations

import shutil
from pathlib import Path

import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest
from tests.helpers import make_synthetic_video

from subtitle_dataset.export import EVENTS_SCHEMA, FRAMES_SCHEMA, SAMPLES_SCHEMA, SCENES_SCHEMA

REPO_ROOT = Path(__file__).resolve().parents[2]
INGEST_CONFIG = REPO_ROOT / "configs" / "ingest" / "default.json"
SAMPLING_CONFIG = REPO_ROOT / "configs" / "sampling" / "default.json"


def test_export_parquet_cli(tmp_path: Path) -> None:
    from subtitle_dataset.cli import main

    if shutil.which("ffmpeg") is None:
        pytest.skip("缺少 ffmpeg")
    video = tmp_path / "test.mp4"
    make_synthetic_video(video)

    frames_out = tmp_path / "frames"
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
    samples_out = tmp_path / "samples"
    assert (
        main(
            [
                "generate",
                "--clean",
                str(frames_out / "frames"),
                "--frames-manifest",
                str(frames_out / "manifest.json"),
                "--config",
                str(SAMPLING_CONFIG),
                "--outdir",
                str(samples_out),
                "--n",
                "3",
            ]
        )
        == 0
    )
    parquet_out = tmp_path / "parquet"
    assert (
        main(
            [
                "export-parquet",
                "--samples",
                str(samples_out / "manifest.json"),
                "--frames",
                str(frames_out / "manifest.json"),
                "--outdir",
                str(parquet_out),
            ]
        )
        == 0
    )
    samples = pq.read_table(parquet_out / "samples.parquet")
    events = pq.read_table(parquet_out / "events.parquet")
    frames = pq.read_table(parquet_out / "frames.parquet")
    scenes = pq.read_table(parquet_out / "scenes.parquet")
    failures = pq.read_table(parquet_out / "failures.parquet")
    assert samples.num_rows == 3
    assert samples.schema == SAMPLES_SCHEMA
    assert events.num_rows == 3
    assert events.schema == EVENTS_SCHEMA
    assert frames.num_rows == 2
    assert frames.schema == FRAMES_SCHEMA
    assert scenes.num_rows == 2
    assert scenes.schema == SCENES_SCHEMA
    assert failures.num_rows == 0
    assert set(samples.column("split").to_pylist()) == {""}
    assert samples.column("source_video_sha256").to_pylist()[0]
