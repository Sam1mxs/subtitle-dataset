"""样本构建元信息。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .base import NonNegativeInt, Sha256Hex


class BuildInfo(BaseModel):
    """用于可复现性的构建元信息。"""

    dataset_version: str = Field(pattern=r"^v\d+(\.\d+)*$")
    config_sha256: Sha256Hex
    renderer_version: str
    ffmpeg_version: str
    seed: NonNegativeInt
