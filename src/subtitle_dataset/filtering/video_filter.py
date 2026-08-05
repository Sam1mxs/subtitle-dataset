"""视频级粗筛：抽样帧 → 单帧检测 → 时序跟踪 → 判定。"""

from __future__ import annotations

from pathlib import Path

from subtitle_dataset.media.decode import extract_frames
from subtitle_dataset.media.probe import probe_video
from subtitle_dataset.media.timeline import VideoTimeline

from .config import FilteringConfig
from .models import FrameDetection, TextRole, VideoSubtitleReport
from .text_regions import (
    HeuristicTextRegionDetector,
    TextRegionDetector,
    assign_geometric_roles,
)
from .tracking import track_boxes


class VideoSubtitleFilter:
    """判断视频是否带原生硬字幕，并输出字幕/台标/场景文字的证据。"""

    def __init__(
        self,
        config: FilteringConfig,
        detector: TextRegionDetector | None = None,
    ) -> None:
        self._config = config
        self._detector = detector or HeuristicTextRegionDetector(config)

    def analyze(self, video_path: str | Path) -> VideoSubtitleReport:
        probe = probe_video(video_path)
        timeline = VideoTimeline.build(
            video_path,
            time_base=probe.video.time_base,
            video_sha256=probe.sha256,
        )
        if not timeline.frames:
            raise ValueError("视频没有可解码的帧")
        indices = _sample_indices(len(timeline.frames), self._config.sample_frames)
        frames = extract_frames(video_path, indices)
        detections: list[FrameDetection] = []
        for index, frame in zip(indices, frames, strict=True):
            timeline_frame = timeline.frames[index]
            boxes = self._detector.detect(frame)
            boxes = assign_geometric_roles(
                boxes,
                width=frame.width,
                height=frame.height,
                config=self._config,
            )
            detections.append(
                FrameDetection(
                    native_frame_index=timeline_frame.native_frame_index,
                    pts=timeline_frame.pts,
                    timestamp_ms=timeline_frame.timestamp_ms,
                    boxes=boxes,
                )
            )
        persistent = track_boxes(detections, frames, self._config)
        subtitle_boxes = [box for box in persistent if box.role is TextRole.SUBTITLE]
        watermark_boxes = [box for box in persistent if box.role is TextRole.WATERMARK]
        scene_text_boxes = [box for box in persistent if box.role is TextRole.SCENE_TEXT]
        subtitle_present = len(subtitle_boxes) > 0
        reason = (
            f"检出 {len(subtitle_boxes)} 个持久字幕框、{len(watermark_boxes)} 个台标框、"
            f"{len(scene_text_boxes)} 个场景文字框（采样 {len(indices)} 帧）"
        )
        return VideoSubtitleReport(
            video_sha256=probe.sha256,
            sampled_frames=len(indices),
            subtitle_present=subtitle_present,
            subtitle_boxes=subtitle_boxes,
            watermark_boxes=watermark_boxes,
            scene_text_boxes=scene_text_boxes,
            per_frame=detections,
            verdict_reason=reason,
        )


def _sample_indices(total: int, count: int) -> list[int]:
    if total <= count:
        return list(range(total))
    return sorted({round(i * (total - 1) / (count - 1)) for i in range(count)})
