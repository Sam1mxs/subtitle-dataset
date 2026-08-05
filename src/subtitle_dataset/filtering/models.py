"""检测结果数据结构。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class TextRole(StrEnum):
    SUBTITLE = "subtitle"
    SCENE_TEXT = "scene_text"
    WATERMARK = "watermark"
    UNKNOWN = "unknown"


class TextBox(BaseModel):
    """单帧中的一个文字区域框。"""

    xyxy: tuple[int, int, int, int]
    normalized: tuple[float, float, float, float]
    confidence: float
    role: TextRole = TextRole.UNKNOWN


class FrameDetection(BaseModel):
    native_frame_index: int
    pts: int
    timestamp_ms: int
    boxes: list[TextBox]


class PersistentBox(BaseModel):
    """跨帧跟踪后的稳定文字区域。"""

    role: TextRole
    xyxy: tuple[int, int, int, int]
    normalized: tuple[float, float, float, float]
    persistence: float
    position_std: float
    content_switched: bool
    confidence: float
    observed_frames: list[int]


class VideoSubtitleReport(BaseModel):
    video_sha256: str
    sampled_frames: int
    subtitle_present: bool
    subtitle_boxes: list[PersistentBox]
    watermark_boxes: list[PersistentBox]
    scene_text_boxes: list[PersistentBox]
    per_frame: list[FrameDetection]
    verdict_reason: str
