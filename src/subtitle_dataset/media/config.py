"""媒体处理配置。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .crop import CropConfig


class IngestConfig(BaseModel):
    """小规模视频处理 pilot 配置。"""

    scene_threshold: float = Field(ge=0.0, le=1.0, default=0.35)
    frames_per_scene: int = Field(ge=1, default=1)
    crop: CropConfig
