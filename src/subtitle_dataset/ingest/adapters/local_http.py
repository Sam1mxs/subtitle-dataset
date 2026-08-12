"""本地 HTTP 适配器：采集框架的全链路测试源（不依赖任何真实平台）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import urlopen

from .base import ItemRef, SourceAdapter


class LocalHttpAdapter(SourceAdapter):
    """从一个本地 HTTP 目录的 manifest.json 发现条目并下载视频。"""

    name = "local-http"

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def discover(self, request: dict[str, Any] | None = None) -> list[ItemRef]:
        manifest_url = f"{self._base_url}/manifest.json"
        with urlopen(manifest_url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        source_id = (request or {}).get("source_id", "")
        items: list[ItemRef] = []
        for raw in data.get("items", []):
            url = raw["url"]
            if not url.startswith("http"):
                url = urljoin(self._base_url, url)
            items.append(
                ItemRef(
                    source_id=raw.get("source_id", source_id),
                    item_id=raw["item_id"],
                    url=url,
                    title=raw.get("title"),
                )
            )
        return items

    def download(self, item: ItemRef, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        part = destination.with_name(destination.name + ".part")
        with urlopen(item.url, timeout=30) as response, part.open("wb") as out:
            while True:
                chunk = response.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
        part.replace(destination)
