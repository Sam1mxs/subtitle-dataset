"""来源登记表 CLI 与 generate 授权门禁。"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from tests.helpers import make_clean_image

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLING_CONFIG = REPO_ROOT / "configs" / "sampling" / "default.json"


def test_validate_default_registry() -> None:
    from subtitle_dataset.cli import main

    assert main(["source-registry", "validate"]) == 0


def test_check_demo_source_not_authorized() -> None:
    from subtitle_dataset.cli import main

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exit_code = main(["source-registry", "check", "--source-id", "bilibili-demo"])
    assert exit_code == 1
    data = json.loads(buffer.getvalue())
    assert data["authorized"] is False
    assert data["reasons"]


def test_generate_with_authorized_source(tmp_path: Path) -> None:
    from subtitle_dataset.cli import main

    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "version": "1",
                "sources": [
                    {
                        "source_id": "test-src",
                        "platform": "bilibili",
                        "creator_id_or_hash": "creator-001",
                        "license_status": "authorized",
                        "allowed_to_download": True,
                        "allowed_for_derivative_work": True,
                        "allowed_for_ml_training": True,
                        "allowed_to_redistribute": False,
                        "authorization_reference": "测试合同-2026-001",
                        "authorization_start_at": "2026-01-01",
                        "authorization_expire_at": "2026-12-31",
                        "crawled_at": None,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    make_clean_image(width=360, height=640).save(frames_dir / "00000.png")
    frames_manifest = tmp_path / "frames_manifest.json"
    frames_manifest.write_text(
        json.dumps(
            {
                "video_sha256": "a" * 64,
                "ffmpeg_version": "ffmpeg test",
                "probe": {
                    "video": {
                        "time_base": {"num": 1, "den": 15360},
                        "avg_frame_rate": {
                            "avg_num": 30,
                            "avg_den": 1,
                            "r_num": 30,
                            "r_den": 1,
                            "is_vfr": False,
                        },
                    }
                },
                "frames": [
                    {
                        "uri": "frames/00000.png",
                        "native_frame_index": 22,
                        "pts": 11264,
                        "timestamp_ms": 733,
                        "crop_xywh": [0, 0, 360, 640],
                        "target_size": [360, 640],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    outdir = tmp_path / "out"
    assert (
        main(
            [
                "generate",
                "--clean",
                str(frames_dir),
                "--frames-manifest",
                str(frames_manifest),
                "--config",
                str(SAMPLING_CONFIG),
                "--outdir",
                str(outdir),
                "--n",
                "1",
                "--source-id",
                "test-src",
                "--registry",
                str(registry),
            ]
        )
        == 0
    )
    sample = json.loads((outdir / "samples" / "00000" / "sample.json").read_text(encoding="utf-8"))
    assert sample["source"]["platform"] == "bilibili"
    assert sample["source"]["creator_hash"] == "creator-001"


def test_generate_rejects_unauthorized_source(tmp_path: Path) -> None:
    from subtitle_dataset.cli import main

    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "version": "1",
                "sources": [
                    {
                        "source_id": "bad-src",
                        "platform": "douyin",
                        "license_status": "unknown",
                        "allowed_to_download": False,
                        "allowed_for_derivative_work": False,
                        "allowed_for_ml_training": False,
                        "allowed_to_redistribute": False,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    outdir = tmp_path / "out"
    assert (
        main(
            [
                "generate",
                "--clean",
                str(tmp_path / "missing.png"),
                "--config",
                str(SAMPLING_CONFIG),
                "--outdir",
                str(outdir),
                "--n",
                "1",
                "--source-id",
                "bad-src",
                "--registry",
                str(registry),
            ]
        )
        == 2
    )
    assert not outdir.exists()
