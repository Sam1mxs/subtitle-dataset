"""分布报告 CLI 端到端。"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
from pathlib import Path

import pytest
from tests.helpers import make_synthetic_video

REPO_ROOT = Path(__file__).resolve().parents[2]
INGEST_CONFIG = REPO_ROOT / "configs" / "ingest" / "default.json"
SAMPLING_CONFIG = REPO_ROOT / "configs" / "sampling" / "default.json"
DISTRIBUTION_CONFIG = REPO_ROOT / "configs" / "qa" / "distribution.json"


def test_distribution_report_cli(tmp_path: Path) -> None:
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
                "--config",
                str(SAMPLING_CONFIG),
                "--outdir",
                str(samples_out),
                "--n",
                "8",
            ]
        )
        == 0
    )

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        assert (
            main(
                [
                    "distribution-report",
                    "--samples",
                    str(samples_out / "manifest.json"),
                    "--frames",
                    str(frames_out / "manifest.json"),
                    "--config",
                    str(DISTRIBUTION_CONFIG),
                ]
            )
            == 0
        )
    result = json.loads(buffer.getvalue())
    assert result["samples"]["n_samples"] == 8
    assert result["samples"]["pairing_ok"] == 8
    assert result["samples"]["fonts"] == {"noto-sans-cjk-sc": 8}
    assert result["frames"]["n_frames"] == 2
    assert result["frames"]["n_scenes"] == 2
    assert result["frames"]["aspect_ratios"] == {"16:9": 2}
