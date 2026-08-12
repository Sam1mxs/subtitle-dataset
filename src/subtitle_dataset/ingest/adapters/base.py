"""平台适配器接口（设计文档 §5.1）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class ItemRef(BaseModel):
    """一个待下载条目。"""

    source_id: str
    item_id: str
    url: str
    title: str | None = None


class ItemMetadata(BaseModel):
    """规范化后的条目元数据（不含 Cookie/账号等敏感信息）。"""

    item_id: str
    source_id: str
    title: str | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None


class SourceAdapter(ABC):
    """平台适配器基类；平台细节不进入公共管线。"""

    name: str = "base"

    @abstractmethod
    def discover(self, request: dict[str, Any] | None = None) -> list[ItemRef]:
        """发现待下载条目。"""

    @abstractmethod
    def download(self, item: ItemRef, destination: Path) -> None:
        """把条目媒体下载到 destination；幂等与重试由 DownloadManager 负责。"""

    def resolve_metadata(self, item: ItemRef) -> ItemMetadata:
        return ItemMetadata(
            item_id=item.item_id,
            source_id=item.source_id,
            title=item.title,
        )

    def normalize_metadata(self, raw: dict[str, Any]) -> ItemMetadata:
        return ItemMetadata(
            item_id=str(raw.get("item_id", "")),
            source_id=str(raw.get("source_id", "")),
            title=raw.get("title"),
        )
