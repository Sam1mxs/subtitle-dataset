"""去重与内容簇数据模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DedupItem(BaseModel):
    """参与去重的一个条目（视频文件或帧）。"""

    id: str
    sha256: str
    group_id: str | None = None
    platform: str | None = None
    creator_id: str | None = None
    near_hash: str | None = None


class ContentCluster(BaseModel):
    """去重后的内容簇；簇是划分的最小不可拆分单位。"""

    cluster_id: str
    cluster_type: Literal["exact", "near"]
    representative_id: str
    items: list[DedupItem]
