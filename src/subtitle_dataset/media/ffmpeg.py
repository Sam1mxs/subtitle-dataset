"""FFmpeg/ffprobe 子进程封装。"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Sequence

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

_SHOWINFO_RE = re.compile(
    r"\[Parsed_showinfo.*?\]\s+n:\s*(\d+)\s+pts:\s*(\d+)\s+pts_time:([0-9.eE+-]+)"
)


class FfmpegError(RuntimeError):
    """FFmpeg/ffprobe 调用失败。"""


def _clean_env() -> dict[str, str]:
    """去掉 conda 注入的 LD_LIBRARY_PATH，避免污染系统 ffmpeg。"""
    env = os.environ.copy()
    env.pop("LD_LIBRARY_PATH", None)
    return env


def run_ffmpeg(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [FFMPEG, *args],
        capture_output=True,
        text=True,
        env=_clean_env(),
    )
    if proc.returncode != 0:
        raise FfmpegError(_error_tail(proc))
    return proc


def run_ffmpeg_bytes(args: Sequence[str]) -> bytes:
    """运行 ffmpeg 并返回原始 stdout（用于抽帧）。"""
    proc = subprocess.run([FFMPEG, *args], capture_output=True, env=_clean_env())
    if proc.returncode != 0:
        raise FfmpegError(_error_tail(proc))
    return proc.stdout


def run_ffprobe(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [FFPROBE, *args],
        capture_output=True,
        text=True,
        env=_clean_env(),
    )
    if proc.returncode != 0:
        raise FfmpegError(_error_tail(proc))
    return proc


def _error_tail(proc: subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]) -> str:
    stderr = proc.stderr
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    return stderr[-4000:] if stderr else f"退出码 {proc.returncode}"


def ffmpeg_version() -> str:
    return run_ffmpeg(["-version"]).stdout.splitlines()[0].strip()


def ffprobe_version() -> str:
    return run_ffprobe(["-version"]).stdout.splitlines()[0].strip()


def parse_showinfo(stderr: str) -> list[tuple[int, int, float]]:
    """解析 showinfo 输出：[(native_frame_index, pts, pts_time_seconds)]。"""
    frames: list[tuple[int, int, float]] = []
    for line in stderr.splitlines():
        match = _SHOWINFO_RE.search(line)
        if match:
            frames.append((int(match.group(1)), int(match.group(2)), float(match.group(3))))
    return frames


def parse_fraction(value: str | None) -> tuple[int, int]:
    """解析 ffprobe 的帧率/时间基字符串（如 30/1、0/0）。"""
    if not value or value in ("0/0", "N/A"):
        return (0, 1)
    num, _, den = value.partition("/")
    try:
        n, d = int(num), int(den) if den else 1
    except ValueError:
        return (0, 1)
    return (n, d) if d > 0 else (0, 1)
