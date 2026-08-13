"""字幕事件模型（§6.2）：时间语义、代表帧时间点与确定性 event_id。"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from subtitle_dataset.contracts import TimeBase, canonical_dumps, sha256_hex
from subtitle_dataset.rendering.config import RenderStyle


class SubtitleEventSpec(BaseModel):
    """一个字幕事件（事件内文本与样式不变）。

    时间统一用毫秒；原生帧边界只用于索引与回放。bbox/mask 属于事件内
    每一帧样本，不放在事件上。
    """

    event_id: str
    text_raw: str
    text_normalized: str
    normalization_version: str | None = None
    style: RenderStyle
    start_native_frame: int = Field(ge=0)
    end_native_frame_exclusive: int = Field(ge=0)
    native_duration_frames: int = Field(gt=0)
    start_pts: int
    end_pts_exclusive: int
    start_time_ms: int = Field(ge=0)
    end_time_ms: int = Field(ge=0)
    duration_ms: int = Field(gt=0)
    frames_per_event: int = Field(ge=1)
    fade_in_ms: int = Field(ge=0, default=0)
    fade_out_ms: int = Field(ge=0, default=0)

    @model_validator(mode="after")
    def _check_time_invariants(self) -> SubtitleEventSpec:
        if self.end_native_frame_exclusive <= self.start_native_frame:
            raise ValueError("end_native_frame_exclusive 必须大于 start_native_frame")
        if self.native_duration_frames != self.end_native_frame_exclusive - self.start_native_frame:
            raise ValueError("native_duration_frames 与原生帧边界不一致")
        if self.end_pts_exclusive <= self.start_pts:
            raise ValueError("end_pts_exclusive 必须大于 start_pts")
        if self.end_time_ms <= self.start_time_ms:
            raise ValueError("end_time_ms 必须大于 start_time_ms")
        if self.duration_ms != self.end_time_ms - self.start_time_ms:
            raise ValueError("duration_ms 必须等于 end_time_ms - start_time_ms")
        if self.fade_in_ms + self.fade_out_ms > self.duration_ms:
            raise ValueError("fade_in_ms + fade_out_ms 不能超过 duration_ms")
        return self


def ms_to_pts(ms: int, time_base: TimeBase) -> int:
    """毫秒 → PTS（按 time_base 四舍五入）。"""
    return round(ms * time_base.den / (time_base.num * 1000))


def representative_time_ms(start_time_ms: int, duration_ms: int, k: int, index: int) -> int:
    """事件内第 index 个代表帧的毫秒时间点（均匀分布）。"""
    if k <= 1:
        return start_time_ms + duration_ms // 2
    return start_time_ms + round(index * duration_ms / (k - 1))


def fade_factor(
    time_ms: int,
    start_time_ms: int,
    end_time_ms: int,
    fade_in_ms: int,
    fade_out_ms: int,
) -> float:
    """事件内某时刻的可见度系数：淡入 ramp 0→1、淡出 ramp 1→0。"""
    duration = max(end_time_ms - start_time_ms, 1)
    elapsed = time_ms - start_time_ms
    if fade_in_ms > 0 and elapsed < fade_in_ms:
        return max(0.0, elapsed / fade_in_ms)
    if fade_out_ms > 0 and elapsed > duration - fade_out_ms:
        return max(0.0, (duration - elapsed) / fade_out_ms)
    return 1.0


def compute_event_id(*, seed: int, text_raw: str, style_seed: int, start_time_ms: int) -> str:
    """确定性事件 ID，不依赖存储路径。"""
    payload = canonical_dumps(
        {
            "seed": seed,
            "text_raw": text_raw,
            "style_seed": style_seed,
            "start_time_ms": start_time_ms,
        }
    )
    return sha256_hex(payload)
