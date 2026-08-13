"""Parquet 导出：行拍平、显式 schema、读写回验。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow.parquet as pq  # type: ignore[import-untyped]

from subtitle_dataset.export import (
    SAMPLES_SCHEMA,
    export_ingest_manifest,
    export_samples_manifest,
    ingest_manifest_to_rows,
    sample_record_to_row,
    write_records,
)


def _sample_record(index: int = 0) -> dict[str, Any]:
    return {
        "sample_index": index,
        "sample_seed": index,
        "duration_ms": 1500,
        "text": "今天ＡＢＣ一起吃饭",
        "text_normalized": "今天ABC一起吃饭",
        "normalization_version": "1.0",
        "language": "zh",
        "script": "CJK",
        "font_id": "noto-sans-cjk-sc",
        "font_sha256": "b" * 64,
        "fallback_used": False,
        "missing_chars": {"dejavu-sans": ["今", "晚"]},
        "center": [0.5, 0.75],
        "effect_bbox_xyxy": [50, 461, 310, 499],
        "line_bboxes_xyxy": [[50, 461, 310, 499]],
        "config_sha256": "c" * 64,
        "pairing_ok": True,
        "text_policy_ok": True,
        "split": "train",
        "style": {
            "font_ids": ["noto-sans-cjk-sc"],
            "font_size_h_ratio": 0.05,
            "letter_spacing_px": 1.2,
            "line_spacing_px": 4.0,
            "stroke_width_h_ratio": 0.004,
            "opacity": 1.0,
            "align": "center",
            "fill_color": [255, 255, 255, 255],
            "stroke_color": [0, 0, 0, 255],
            "shadow_color": [0, 0, 0, 255],
            "shadow_offset_xy": [0.0, 0.0],
            "shadow_blur_px": 0.0,
            "language": "zh",
            "direction": None,
        },
        "source": {
            "platform": "bilibili",
            "video_sha256": "a" * 64,
            "creator_hash": "creator-001",
            "native_frame_index": 45,
            "pts": 45000,
            "timestamp_ms": 1500,
            "time_base": {"num": 1, "den": 30000},
            "frame_rate": {
                "avg_num": 30,
                "avg_den": 1,
                "r_num": 30,
                "r_den": 1,
                "is_vfr": False,
            },
        },
        "transform": {"crop_xywh": [0, 0, 360, 640], "target_size": [360, 640]},
        "build": {
            "dataset_version": "v1",
            "config_sha256": "c" * 64,
            "renderer_version": "0.1.0",
            "ffmpeg_version": "ffmpeg test",
            "seed": 42,
        },
    }


def test_sample_row_flattening() -> None:
    row = sample_record_to_row(_sample_record())
    assert row["source_time_base_num"] == 1
    assert row["source_time_base_den"] == 30000
    assert row["source_is_vfr"] is False
    assert row["transform_crop_w"] == 360
    assert row["transform_target_height"] == 640
    assert row["style_font_ids"] == ["noto-sans-cjk-sc"]
    assert row["missing_chars"] == [("dejavu-sans", ["今", "晚"])]
    assert row["split"] == "train"
    assert row["effect_bbox_x0"] == 50
    assert row["build_seed"] == 42


def test_sample_row_missing_optional_fields() -> None:
    row = sample_record_to_row({"sample_index": 0, "duration_ms": 100})
    assert row["source_platform"] is None
    assert row["transform_crop_w"] == 0
    assert row["split"] == ""
    assert row["missing_chars"] == []


def test_write_and_read_back(tmp_path: Path) -> None:
    path = write_records(
        [sample_record_to_row(_sample_record()), sample_record_to_row(_sample_record(1))],
        SAMPLES_SCHEMA,
        tmp_path / "s.parquet",
    )
    table = pq.read_table(path)
    assert table.num_rows == 2
    assert table.schema == SAMPLES_SCHEMA
    assert table.column("split").to_pylist() == ["train", "train"]
    assert table.column("source_time_base_den").to_pylist() == [30000, 30000]


def test_empty_records_keep_schema(tmp_path: Path) -> None:
    path = write_records([], SAMPLES_SCHEMA, tmp_path / "empty.parquet")
    table = pq.read_table(path)
    assert table.num_rows == 0
    assert table.schema == SAMPLES_SCHEMA


def test_ingest_manifest_rows_and_export(tmp_path: Path) -> None:
    manifest = {
        "video_sha256": "a" * 64,
        "probe": {
            "video": {
                "width": 640,
                "height": 360,
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
        "scenes": [{"index": 0, "duration_ms": 1500}],
        "frames": [
            {
                "scene_index": 0,
                "native_frame_index": 22,
                "pts": 11264,
                "pts_time_seconds": 0.733,
                "timestamp_ms": 733,
                "crop_xywh": [0, 0, 640, 360],
                "target_size": [1280, 720],
                "uri": "frames/00000.png",
                "image_sha256": "d" * 64,
            }
        ],
        "failures": [
            {
                "stage": "extract",
                "input_ref": "frame=99",
                "error_type": "ValueError",
                "message": "bad frame",
                "retryable": True,
                "failed_at": "2026-08-13T00:00:00Z",
            }
        ],
    }
    frames, scenes, failures = ingest_manifest_to_rows(manifest)
    assert len(frames) == 1 and len(scenes) == 1 and len(failures) == 1
    assert frames[0]["source_width"] == 640
    assert frames[0]["time_base_den"] == 15360
    paths = export_ingest_manifest(manifest, tmp_path / "out")
    assert [p.name for p in paths] == [
        "frames.parquet",
        "scenes.parquet",
        "failures.parquet",
    ]
    assert pq.read_table(paths[0]).num_rows == 1
    assert pq.read_table(paths[2]).num_rows == 1


def test_export_samples_manifest(tmp_path: Path) -> None:
    manifest = {"samples": [_sample_record(), _sample_record(1), _sample_record(2)]}
    path = export_samples_manifest(manifest, tmp_path / "out")
    assert pq.read_table(path).num_rows == 3
