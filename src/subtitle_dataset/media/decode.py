"""按原生帧号抽取视频帧（ffmpeg select）。"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from .ffmpeg import run_ffmpeg_bytes


def extract_frame(video_path: str | Path, native_frame_index: int) -> Image.Image:
    """按原生帧索引抽取一帧，返回 RGB 图像。"""
    stdout = run_ffmpeg_bytes(
        [
            "-i",
            str(video_path),
            "-vf",
            f"select='eq(n,{native_frame_index})'",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ]
    )
    if not stdout:
        raise ValueError(f"帧 {native_frame_index} 抽取结果为空")
    return Image.open(io.BytesIO(stdout)).convert("RGB")
