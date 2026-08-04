"""视频元数据探测（ffprobe）。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from subtitle_dataset.contracts import FrameRate, TimeBase

from .ffmpeg import ffprobe_version, parse_fraction, run_ffprobe


class VideoStreamProbe(BaseModel):
    """视频流元数据（保留原生时间语义，不做 30fps 重采样）。"""

    index: int
    codec_name: str
    width: int
    height: int
    avg_frame_rate: FrameRate
    r_frame_rate: FrameRate
    time_base: TimeBase
    duration_seconds: float | None = None
    nb_frames: int | None = None
    pix_fmt: str | None = None
    color_range: str | None = None
    color_space: str | None = None
    color_primaries: str | None = None
    color_transfer: str | None = None
    is_vfr: bool


class VideoProbe(BaseModel):
    path: str
    sha256: str
    format_name: str
    duration_seconds: float | None
    video: VideoStreamProbe
    ffprobe_version: str


def probe_video(video_path: str | Path) -> VideoProbe:
    """用 ffprobe 探测视频：格式、视频流、帧率、time_base 与色彩信息。"""
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(path)
    proc = run_ffprobe(
        [
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    data = json.loads(proc.stdout)
    streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if not streams:
        raise ValueError(f"{path} 没有视频流")
    stream = streams[0]
    fmt = data.get("format", {})
    avg_num, avg_den = parse_fraction(stream.get("avg_frame_rate"))
    r_num, r_den = parse_fraction(stream.get("r_frame_rate"))
    is_vfr = avg_num == 0 or (avg_num, avg_den) != (r_num, r_den)
    return VideoProbe(
        path=str(path),
        sha256=sha256_file(path),
        format_name=fmt.get("format_name", ""),
        duration_seconds=_opt_float(fmt.get("duration")),
        video=VideoStreamProbe(
            index=int(stream.get("index", 0)),
            codec_name=stream.get("codec_name", ""),
            width=int(stream.get("width", 0)),
            height=int(stream.get("height", 0)),
            avg_frame_rate=FrameRate(
                avg_num=avg_num, avg_den=avg_den, r_num=r_num, r_den=r_den, is_vfr=is_vfr
            ),
            r_frame_rate=FrameRate(
                avg_num=r_num, avg_den=r_den, r_num=r_num, r_den=r_den, is_vfr=is_vfr
            ),
            time_base=_parse_time_base(stream.get("time_base")),
            duration_seconds=_opt_float(stream.get("duration")),
            nb_frames=_opt_int(stream.get("nb_frames")),
            pix_fmt=stream.get("pix_fmt"),
            color_range=stream.get("color_range"),
            color_space=stream.get("color_space"),
            color_primaries=stream.get("color_primaries"),
            color_transfer=stream.get("color_transfer"),
            is_vfr=is_vfr,
        ),
        ffprobe_version=ffprobe_version(),
    )


def sha256_file(path: Path) -> str:
    """流式计算文件 SHA-256。"""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_time_base(value: Any) -> TimeBase:
    num, den = parse_fraction(value)
    return TimeBase(num=num or 1, den=den or 1000)


def _opt_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _opt_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
