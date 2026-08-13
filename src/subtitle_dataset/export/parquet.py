"""Parquet manifest 导出（设计文档 §13）：显式 schema、行拍平、可复现。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

SAMPLES_SCHEMA = pa.schema(
    [
        pa.field("sample_index", pa.int64()),
        pa.field("sample_seed", pa.int64()),
        pa.field("duration_ms", pa.int64()),
        pa.field("text", pa.string()),
        pa.field("text_normalized", pa.string()),
        pa.field("normalization_version", pa.string()),
        pa.field("language", pa.string()),
        pa.field("script", pa.string()),
        pa.field("font_id", pa.string()),
        pa.field("font_sha256", pa.string()),
        pa.field("fallback_used", pa.bool_()),
        pa.field("missing_chars", pa.map_(pa.string(), pa.list_(pa.string()))),
        pa.field("center_x", pa.float64()),
        pa.field("center_y", pa.float64()),
        pa.field("effect_bbox_x0", pa.int64()),
        pa.field("effect_bbox_y0", pa.int64()),
        pa.field("effect_bbox_x1", pa.int64()),
        pa.field("effect_bbox_y1", pa.int64()),
        pa.field("line_bboxes_xyxy", pa.list_(pa.list_(pa.int64()))),
        pa.field("config_sha256", pa.string()),
        pa.field("pairing_ok", pa.bool_()),
        pa.field("text_policy_ok", pa.bool_()),
        pa.field("split", pa.string()),
        pa.field("style_font_ids", pa.list_(pa.string())),
        pa.field("style_font_size_h_ratio", pa.float64()),
        pa.field("style_letter_spacing_px", pa.float64()),
        pa.field("style_line_spacing_px", pa.float64()),
        pa.field("style_stroke_width_h_ratio", pa.float64()),
        pa.field("style_opacity", pa.float64()),
        pa.field("style_align", pa.string()),
        pa.field("style_fill_color", pa.list_(pa.int64())),
        pa.field("style_stroke_color", pa.list_(pa.int64())),
        pa.field("style_shadow_color", pa.list_(pa.int64())),
        pa.field("style_shadow_offset_xy", pa.list_(pa.float64())),
        pa.field("style_shadow_blur_px", pa.float64()),
        pa.field("style_language", pa.string()),
        pa.field("style_direction", pa.string()),
        pa.field("source_platform", pa.string()),
        pa.field("source_video_sha256", pa.string()),
        pa.field("source_creator_hash", pa.string()),
        pa.field("source_native_frame_index", pa.int64()),
        pa.field("source_pts", pa.int64()),
        pa.field("source_timestamp_ms", pa.int64()),
        pa.field("source_time_base_num", pa.int64()),
        pa.field("source_time_base_den", pa.int64()),
        pa.field("source_avg_num", pa.int64()),
        pa.field("source_avg_den", pa.int64()),
        pa.field("source_r_num", pa.int64()),
        pa.field("source_r_den", pa.int64()),
        pa.field("source_is_vfr", pa.bool_()),
        pa.field("transform_crop_x", pa.int64()),
        pa.field("transform_crop_y", pa.int64()),
        pa.field("transform_crop_w", pa.int64()),
        pa.field("transform_crop_h", pa.int64()),
        pa.field("transform_target_width", pa.int64()),
        pa.field("transform_target_height", pa.int64()),
        pa.field("build_dataset_version", pa.string()),
        pa.field("build_config_sha256", pa.string()),
        pa.field("build_renderer_version", pa.string()),
        pa.field("build_ffmpeg_version", pa.string()),
        pa.field("build_seed", pa.int64()),
    ]
)

FRAMES_SCHEMA = pa.schema(
    [
        pa.field("video_sha256", pa.string()),
        pa.field("scene_index", pa.int64()),
        pa.field("native_frame_index", pa.int64()),
        pa.field("pts", pa.int64()),
        pa.field("pts_time_seconds", pa.float64()),
        pa.field("timestamp_ms", pa.int64()),
        pa.field("crop_x", pa.int64()),
        pa.field("crop_y", pa.int64()),
        pa.field("crop_w", pa.int64()),
        pa.field("crop_h", pa.int64()),
        pa.field("target_width", pa.int64()),
        pa.field("target_height", pa.int64()),
        pa.field("uri", pa.string()),
        pa.field("image_sha256", pa.string()),
        pa.field("source_width", pa.int64()),
        pa.field("source_height", pa.int64()),
        pa.field("time_base_num", pa.int64()),
        pa.field("time_base_den", pa.int64()),
        pa.field("avg_num", pa.int64()),
        pa.field("avg_den", pa.int64()),
        pa.field("r_num", pa.int64()),
        pa.field("r_den", pa.int64()),
        pa.field("is_vfr", pa.bool_()),
    ]
)

SCENES_SCHEMA = pa.schema(
    [
        pa.field("video_sha256", pa.string()),
        pa.field("index", pa.int64()),
        pa.field("start_frame", pa.int64()),
        pa.field("end_frame_exclusive", pa.int64()),
        pa.field("start_pts", pa.int64()),
        pa.field("end_pts_exclusive", pa.int64()),
        pa.field("start_time_ms", pa.int64()),
        pa.field("end_time_ms", pa.int64()),
        pa.field("duration_ms", pa.int64()),
    ]
)

FAILURES_SCHEMA = pa.schema(
    [
        pa.field("stage", pa.string()),
        pa.field("input_ref", pa.string()),
        pa.field("error_type", pa.string()),
        pa.field("message", pa.string()),
        pa.field("retryable", pa.bool_()),
        pa.field("failed_at", pa.string()),
    ]
)

EVENTS_SCHEMA = pa.schema(
    [
        pa.field("event_id", pa.string()),
        pa.field("text_raw", pa.string()),
        pa.field("text_normalized", pa.string()),
        pa.field("normalization_version", pa.string()),
        pa.field("start_time_ms", pa.int64()),
        pa.field("end_time_ms", pa.int64()),
        pa.field("duration_ms", pa.int64()),
        pa.field("start_pts", pa.int64()),
        pa.field("end_pts_exclusive", pa.int64()),
        pa.field("start_native_frame", pa.int64()),
        pa.field("end_native_frame_exclusive", pa.int64()),
        pa.field("native_duration_frames", pa.int64()),
        pa.field("frames_per_event", pa.int64()),
        pa.field("style_font_ids", pa.list_(pa.string())),
        pa.field("style_font_size_h_ratio", pa.float64()),
        pa.field("style_align", pa.string()),
        pa.field("language", pa.string()),
    ]
)


def sample_record_to_row(record: Mapping[str, Any]) -> dict[str, Any]:
    style = record.get("style") or {}
    source = record.get("source")
    transform = record.get("transform")
    build = record.get("build")
    bbox = record.get("effect_bbox_xyxy") or [0, 0, 0, 0]
    center = record.get("center") or [0.0, 0.0]
    crop = (transform or {}).get("crop_xywh") or [0, 0, 0, 0]
    target = (transform or {}).get("target_size") or [0, 0]
    missing = record.get("missing_chars") or {}
    return {
        "sample_index": record.get("sample_index"),
        "sample_seed": record.get("sample_seed"),
        "duration_ms": record.get("duration_ms"),
        "text": record.get("text"),
        "text_normalized": record.get("text_normalized"),
        "normalization_version": record.get("normalization_version"),
        "language": record.get("language"),
        "script": record.get("script"),
        "font_id": record.get("font_id"),
        "font_sha256": record.get("font_sha256"),
        "fallback_used": record.get("fallback_used", False),
        "missing_chars": [(key, list(value)) for key, value in missing.items()],
        "center_x": center[0],
        "center_y": center[1],
        "effect_bbox_x0": bbox[0],
        "effect_bbox_y0": bbox[1],
        "effect_bbox_x1": bbox[2],
        "effect_bbox_y1": bbox[3],
        "line_bboxes_xyxy": record.get("line_bboxes_xyxy") or [],
        "config_sha256": record.get("config_sha256"),
        "pairing_ok": record.get("pairing_ok", False),
        "text_policy_ok": record.get("text_policy_ok"),
        "split": (record.get("split") or ""),
        "style_font_ids": style.get("font_ids") or [],
        "style_font_size_h_ratio": style.get("font_size_h_ratio"),
        "style_letter_spacing_px": style.get("letter_spacing_px"),
        "style_line_spacing_px": style.get("line_spacing_px"),
        "style_stroke_width_h_ratio": style.get("stroke_width_h_ratio"),
        "style_opacity": style.get("opacity"),
        "style_align": style.get("align"),
        "style_fill_color": style.get("fill_color") or [],
        "style_stroke_color": style.get("stroke_color") or [],
        "style_shadow_color": style.get("shadow_color") or [],
        "style_shadow_offset_xy": style.get("shadow_offset_xy") or [],
        "style_shadow_blur_px": style.get("shadow_blur_px"),
        "style_language": style.get("language"),
        "style_direction": style.get("direction"),
        "source_platform": (source or {}).get("platform"),
        "source_video_sha256": (source or {}).get("video_sha256"),
        "source_creator_hash": (source or {}).get("creator_hash"),
        "source_native_frame_index": (source or {}).get("native_frame_index"),
        "source_pts": (source or {}).get("pts"),
        "source_timestamp_ms": (source or {}).get("timestamp_ms"),
        "source_time_base_num": (source or {}).get("time_base", {}).get("num"),
        "source_time_base_den": (source or {}).get("time_base", {}).get("den"),
        "source_avg_num": (source or {}).get("frame_rate", {}).get("avg_num"),
        "source_avg_den": (source or {}).get("frame_rate", {}).get("avg_den"),
        "source_r_num": (source or {}).get("frame_rate", {}).get("r_num"),
        "source_r_den": (source or {}).get("frame_rate", {}).get("r_den"),
        "source_is_vfr": (source or {}).get("frame_rate", {}).get("is_vfr"),
        "transform_crop_x": crop[0],
        "transform_crop_y": crop[1],
        "transform_crop_w": crop[2],
        "transform_crop_h": crop[3],
        "transform_target_width": target[0],
        "transform_target_height": target[1],
        "build_dataset_version": (build or {}).get("dataset_version"),
        "build_config_sha256": (build or {}).get("config_sha256"),
        "build_renderer_version": (build or {}).get("renderer_version"),
        "build_ffmpeg_version": (build or {}).get("ffmpeg_version"),
        "build_seed": (build or {}).get("seed"),
    }


def ingest_manifest_to_rows(
    manifest: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    video_sha256 = manifest["video_sha256"]
    probe_video = manifest.get("probe", {}).get("video", {})
    time_base = probe_video.get("time_base", {})
    rate = probe_video.get("avg_frame_rate", {})
    frames: list[dict[str, Any]] = []
    for frame in manifest.get("frames", []):
        crop = frame.get("crop_xywh") or [0, 0, 0, 0]
        target = frame.get("target_size") or [0, 0]
        frames.append(
            {
                "video_sha256": video_sha256,
                "scene_index": frame.get("scene_index"),
                "native_frame_index": frame.get("native_frame_index"),
                "pts": frame.get("pts"),
                "pts_time_seconds": frame.get("pts_time_seconds"),
                "timestamp_ms": frame.get("timestamp_ms"),
                "crop_x": crop[0],
                "crop_y": crop[1],
                "crop_w": crop[2],
                "crop_h": crop[3],
                "target_width": target[0],
                "target_height": target[1],
                "uri": frame.get("uri"),
                "image_sha256": frame.get("image_sha256"),
                "source_width": probe_video.get("width"),
                "source_height": probe_video.get("height"),
                "time_base_num": time_base.get("num"),
                "time_base_den": time_base.get("den"),
                "avg_num": rate.get("avg_num"),
                "avg_den": rate.get("avg_den"),
                "r_num": rate.get("r_num"),
                "r_den": rate.get("r_den"),
                "is_vfr": rate.get("is_vfr"),
            }
        )
    scenes = [
        {
            "video_sha256": video_sha256,
            "index": scene.get("index"),
            "start_frame": scene.get("start_frame"),
            "end_frame_exclusive": scene.get("end_frame_exclusive"),
            "start_pts": scene.get("start_pts"),
            "end_pts_exclusive": scene.get("end_pts_exclusive"),
            "start_time_ms": scene.get("start_time_ms"),
            "end_time_ms": scene.get("end_time_ms"),
            "duration_ms": scene.get("duration_ms"),
        }
        for scene in manifest.get("scenes", [])
    ]
    failures = [
        {
            "stage": failure.get("stage"),
            "input_ref": failure.get("input_ref"),
            "error_type": failure.get("error_type"),
            "message": failure.get("message"),
            "retryable": failure.get("retryable", False),
            "failed_at": str(failure.get("failed_at") or ""),
        }
        for failure in manifest.get("failures", [])
    ]
    return frames, scenes, failures


def event_spec_to_row(event: Mapping[str, Any]) -> dict[str, Any]:
    style = event.get("style") or {}
    return {
        "event_id": event.get("event_id"),
        "text_raw": event.get("text_raw"),
        "text_normalized": event.get("text_normalized"),
        "normalization_version": event.get("normalization_version"),
        "start_time_ms": event.get("start_time_ms"),
        "end_time_ms": event.get("end_time_ms"),
        "duration_ms": event.get("duration_ms"),
        "start_pts": event.get("start_pts"),
        "end_pts_exclusive": event.get("end_pts_exclusive"),
        "start_native_frame": event.get("start_native_frame"),
        "end_native_frame_exclusive": event.get("end_native_frame_exclusive"),
        "native_duration_frames": event.get("native_duration_frames"),
        "frames_per_event": event.get("frames_per_event"),
        "style_font_ids": style.get("font_ids") or [],
        "style_font_size_h_ratio": style.get("font_size_h_ratio"),
        "style_align": style.get("align"),
        "language": event.get("language"),
    }


def write_records(records: Sequence[Mapping[str, Any]], schema: pa.Schema, path: Path) -> Path:
    """按显式 schema 写 Parquet；空列表也写出（保留 schema）。"""
    table = pa.Table.from_pylist([dict(record) for record in records], schema=schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)
    return path


def export_samples_manifest(manifest: Mapping[str, Any], outdir: Path) -> Path:
    rows = [sample_record_to_row(record) for record in manifest.get("samples", [])]
    return write_records(rows, SAMPLES_SCHEMA, outdir / "samples.parquet")


def export_events_manifest(manifest: Mapping[str, Any], outdir: Path) -> Path:
    rows = [event_spec_to_row(event) for event in manifest.get("events", [])]
    return write_records(rows, EVENTS_SCHEMA, outdir / "events.parquet")


def export_ingest_manifest(manifest: Mapping[str, Any], outdir: Path) -> list[Path]:
    frames, scenes, failures = ingest_manifest_to_rows(manifest)
    paths = [
        write_records(frames, FRAMES_SCHEMA, outdir / "frames.parquet"),
        write_records(scenes, SCENES_SCHEMA, outdir / "scenes.parquet"),
        write_records(failures, FAILURES_SCHEMA, outdir / "failures.parquet"),
    ]
    return paths
