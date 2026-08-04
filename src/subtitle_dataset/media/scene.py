"""场景切分：基于 ffmpeg scene 滤镜的镜头边界检测。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from .ffmpeg import parse_showinfo, run_ffmpeg
from .timeline import TimelineFrame, VideoTimeline


class Scene(BaseModel):
    index: int
    start_frame: int
    end_frame_exclusive: int
    start_pts: int
    end_pts_exclusive: int
    start_time_ms: int
    end_time_ms: int
    duration_ms: int


def detect_scene_cut_times(video_path: str | Path, threshold: float) -> list[float]:
    """返回镜头切换点的 pts_time（秒），已按时间排序。"""
    proc = run_ffmpeg(
        [
            "-i",
            str(video_path),
            "-vf",
            f"select='gt(scene,{threshold})',showinfo",
            "-f",
            "null",
            "-",
        ]
    )
    cut_times = sorted(pts_time for _, _, pts_time in parse_showinfo(proc.stderr))
    return cut_times


def build_scenes(
    video_path: str | Path,
    timeline: VideoTimeline,
    *,
    threshold: float,
    duration_seconds: float,
) -> list[Scene]:
    """把时间轴切分为场景；边界按帧对齐，保留原生 PTS 与毫秒。"""
    cut_times = detect_scene_cut_times(video_path, threshold)
    boundaries = [0.0, *cut_times, duration_seconds]
    scenes: list[Scene] = []
    for index, (start_t, end_t) in enumerate(zip(boundaries, boundaries[1:], strict=False)):
        start_frame = _first_frame_at_or_after(timeline, start_t)
        end_frame = _first_frame_at_or_after(timeline, end_t)
        start_frame = min(start_frame, len(timeline.frames) - 1)
        end_frame = max(end_frame, start_frame + 1)
        if start_frame >= len(timeline.frames):
            continue
        start = timeline.frames[start_frame]
        end_idx = min(end_frame, len(timeline.frames) - 1)
        end = timeline.frames[end_idx]
        scenes.append(
            Scene(
                index=index,
                start_frame=start_frame,
                end_frame_exclusive=end_frame,
                start_pts=start.pts,
                end_pts_exclusive=end.pts,
                start_time_ms=start.timestamp_ms,
                end_time_ms=end.timestamp_ms,
                duration_ms=max(end.timestamp_ms - start.timestamp_ms, 1),
            )
        )
    return scenes


def pick_representative_frames(
    scene: Scene,
    timeline: VideoTimeline,
    frames_per_scene: int,
) -> list[TimelineFrame]:
    """每个场景均匀抽取代表帧（默认取中间帧）。"""
    count = scene.end_frame_exclusive - scene.start_frame
    if count <= 0:
        return []
    k = min(frames_per_scene, count)
    if k == 1:
        picks = [scene.start_frame + count // 2]
    else:
        picks = [scene.start_frame + round(i * (count - 1) / (k - 1)) for i in range(k)]
    return [timeline.frames[i] for i in sorted(set(picks))]


def _first_frame_at_or_after(timeline: VideoTimeline, pts_time: float) -> int:
    for index, frame in enumerate(timeline.frames):
        if frame.pts_time_seconds >= pts_time:
            return index
    return len(timeline.frames)
