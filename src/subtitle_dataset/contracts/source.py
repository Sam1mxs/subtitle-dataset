"""视频来源与原生时间轴信息。"""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from .base import FrameRate, NonNegativeInt, Sha256Hex, TimeBase


class SourceInfo(BaseModel):
    """样本对应的原始视频、帧与时间信息。

    跨视频统一的时间单位为毫秒；``native_frame_index`` 仅用于索引与回放，
    不作为跨视频比较时长的统一单位。
    """

    platform: str
    video_sha256: Sha256Hex
    creator_hash: str | None = None
    content_cluster_id: str | None = None
    native_frame_index: NonNegativeInt
    pts: int
    timestamp_ms: NonNegativeInt
    time_base: TimeBase
    frame_rate: FrameRate

    @model_validator(mode="after")
    def _check_timestamp_consistency(self) -> SourceInfo:
        expected_ms = self.time_base.ticks_to_ms(self.pts)
        if abs(self.timestamp_ms - expected_ms) > 1:
            raise ValueError(
                f"timestamp_ms={self.timestamp_ms} 与 pts={self.pts} × time_base "
                f"({self.time_base.num}/{self.time_base.den}) 换算结果 {expected_ms} ms 不一致"
            )
        return self
