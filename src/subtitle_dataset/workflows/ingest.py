"""小规模视频处理 pilot：probe → 时间轴 → 场景 → 抽帧 → 裁剪 → manifest。"""

from __future__ import annotations

import json
import random
from pathlib import Path

from pydantic import BaseModel

from subtitle_dataset.contracts import FailureRecord, config_sha256
from subtitle_dataset.media.config import IngestConfig
from subtitle_dataset.media.crop import crop_and_resize
from subtitle_dataset.media.decode import extract_frame
from subtitle_dataset.media.ffmpeg import ffmpeg_version
from subtitle_dataset.media.probe import VideoProbe, probe_video, sha256_file
from subtitle_dataset.media.scene import Scene, build_scenes, pick_representative_frames
from subtitle_dataset.media.timeline import VideoTimeline


class FrameRecord(BaseModel):
    """抽取并裁剪后的一帧，携带完整的原生时间信息。"""

    scene_index: int
    native_frame_index: int
    pts: int
    pts_time_seconds: float
    timestamp_ms: int
    crop_xywh: tuple[int, int, int, int]
    target_size: tuple[int, int]
    uri: str
    image_sha256: str


class IngestReport(BaseModel):
    video_sha256: str
    ffmpeg_version: str
    config_sha256: str
    probe: VideoProbe
    scenes: list[Scene]
    frames: list[FrameRecord]
    failures: list[FailureRecord]


def run_ingest(
    video_path: str | Path,
    config: IngestConfig,
    outdir: Path,
) -> IngestReport:
    """对单个视频执行 pilot 管线，输出帧文件与 manifest。"""
    outdir.mkdir(parents=True, exist_ok=True)
    frame_dir = outdir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    probe = probe_video(video_path)
    timeline = VideoTimeline.build(
        video_path,
        time_base=probe.video.time_base,
        video_sha256=probe.sha256,
    )
    if not timeline.monotonic_pts:
        raise ValueError("视频帧 PTS 不单调，拒绝进入管线")

    duration = probe.duration_seconds or (
        timeline.frames[-1].pts_time_seconds if timeline.frames else 0.0
    )
    scenes = build_scenes(
        video_path,
        timeline,
        threshold=config.scene_threshold,
        duration_seconds=duration,
    )

    rng = random.Random(config.crop.seed)
    frames: list[FrameRecord] = []
    failures: list[FailureRecord] = []
    for scene in scenes:
        for timeline_frame in pick_representative_frames(scene, timeline, config.frames_per_scene):
            index = len(frames)
            uri = f"frames/{index:05d}.png"
            try:
                frame_image = extract_frame(video_path, timeline_frame.native_frame_index)
                cropped, crop_result = crop_and_resize(frame_image, config.crop, rng)
                target_path = outdir / uri
                cropped.save(target_path)
                frames.append(
                    FrameRecord(
                        scene_index=scene.index,
                        native_frame_index=timeline_frame.native_frame_index,
                        pts=timeline_frame.pts,
                        pts_time_seconds=timeline_frame.pts_time_seconds,
                        timestamp_ms=timeline_frame.timestamp_ms,
                        crop_xywh=crop_result.crop_xywh,
                        target_size=crop_result.target_size,
                        uri=uri,
                        image_sha256=sha256_file(target_path),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - 单帧失败不应中断整条管线
                failures.append(
                    FailureRecord(
                        stage="extract",
                        input_ref=f"scene={scene.index},frame={timeline_frame.native_frame_index}",
                        error_type=type(exc).__name__,
                        message=str(exc),
                        retryable=True,
                    )
                )

    report = IngestReport(
        video_sha256=probe.sha256,
        ffmpeg_version=ffmpeg_version(),
        config_sha256=config_sha256(config.model_dump(mode="json")),
        probe=probe,
        scenes=scenes,
        frames=frames,
        failures=failures,
    )
    (outdir / "probe.json").write_text(
        probe.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (outdir / "manifest.json").write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (outdir / "failures.json").write_text(
        json.dumps(
            [failure.model_dump(mode="json") for failure in failures],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return report
