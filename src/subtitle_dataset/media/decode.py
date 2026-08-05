"""按原生帧号抽取视频帧（ffmpeg select）。"""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path

from PIL import Image

from .ffmpeg import run_ffmpeg_bytes

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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


def extract_frames(
    video_path: str | Path,
    indices: Sequence[int],
) -> list[Image.Image]:
    """一次解码批量抽取指定原生帧索引（select 多条件），保持输入顺序。"""
    unique = sorted(set(indices))
    if not unique:
        return []
    expression = "+".join(f"eq(n,{index})" for index in unique)
    stdout = run_ffmpeg_bytes(
        [
            "-i",
            str(video_path),
            "-vf",
            f"select='{expression}'",
            "-vsync",
            "0",
            "-frames:v",
            str(len(unique)),
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ]
    )
    chunks = _split_png_stream(stdout)
    if len(chunks) != len(unique):
        raise ValueError(f"批量抽帧数量不符：期望 {len(unique)}，实际 {len(chunks)}")
    images = [Image.open(io.BytesIO(chunk)).convert("RGB") for chunk in chunks]
    by_index = dict(zip(unique, images, strict=True))
    return [by_index[index] for index in indices]


def _split_png_stream(data: bytes) -> list[bytes]:
    """把 image2pipe 输出的连续 PNG 流按 IEND 切分为独立 PNG。"""
    images: list[bytes] = []
    cursor = 0
    while True:
        start = data.find(_PNG_SIGNATURE, cursor)
        if start == -1:
            break
        pos = start + len(_PNG_SIGNATURE)
        end = -1
        while pos + 12 <= len(data):
            length = int.from_bytes(data[pos : pos + 4], "big")
            chunk_type = data[pos + 4 : pos + 8]
            pos += 12 + length
            if chunk_type == b"IEND":
                end = pos
                break
        if end == -1:
            break
        images.append(data[start:end])
        cursor = end
    return images
