"""原生时间轴：showinfo 帧索引 / PTS / 毫秒映射。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from subtitle_dataset.contracts import TimeBase

from .ffmpeg import parse_showinfo, run_ffmpeg


class TimelineFrame(BaseModel):
    native_frame_index: int
    pts: int
    pts_time_seconds: float
    timestamp_ms: int


class VideoTimeline(BaseModel):
    """解码顺序的全量帧时间轴；PTS 必须单调。"""

    video_sha256: str
    time_base: TimeBase
    monotonic_pts: bool
    frames: list[TimelineFrame]

    @classmethod
    def build(
        cls,
        video_path: str | Path,
        *,
        time_base: TimeBase,
        video_sha256: str,
    ) -> VideoTimeline:
        proc = run_ffmpeg(["-i", str(video_path), "-vf", "showinfo", "-f", "null", "-"])
        raw = parse_showinfo(proc.stderr)
        frames = [
            TimelineFrame(
                native_frame_index=index,
                pts=pts,
                pts_time_seconds=pts_time,
                timestamp_ms=round(pts_time * 1000),
            )
            for index, pts, pts_time in raw
        ]
        pts_values = [frame.pts for frame in frames]
        monotonic = all(b >= a for a, b in zip(pts_values, pts_values[1:], strict=False))
        return cls(
            video_sha256=video_sha256,
            time_base=time_base,
            monotonic_pts=monotonic,
            frames=frames,
        )

    def frame_nearest(self, pts_time_seconds: float) -> TimelineFrame:
        if not self.frames:
            raise ValueError("时间轴为空")
        return min(
            self.frames,
            key=lambda frame: abs(frame.pts_time_seconds - pts_time_seconds),
        )
