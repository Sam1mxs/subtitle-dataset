"""下载管理器：授权门禁、限速、重试、幂等、暂停与删除。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from subtitle_dataset.ingest import (
    CollectConfig,
    DownloadManager,
    ItemRef,
    SourceAdapter,
    SourceRegistry,
)


def _registry(source_id: str = "test-src", **overrides: Any) -> SourceRegistry:
    record: dict[str, Any] = {
        "source_id": source_id,
        "platform": "bilibili",
        "license_status": "authorized",
        "allowed_to_download": True,
        "allowed_for_derivative_work": True,
        "allowed_for_ml_training": True,
        "allowed_to_redistribute": False,
        "authorization_reference": "测试合同-2026-001",
        "authorization_start_at": "2026-01-01",
        "authorization_expire_at": "2026-12-31",
    }
    record.update(overrides)
    return SourceRegistry.model_validate({"version": "1", "sources": [record]})


class FakeAdapter(SourceAdapter):
    name = "fake"

    def __init__(self, *, fail_first: int = 0) -> None:
        self.items = [
            ItemRef(source_id="test-src", item_id=f"v{i}", url=f"http://example.com/{i}.mp4")
            for i in range(3)
        ]
        self.download_calls: list[str] = []
        self.fail_first = fail_first

    def discover(self, request: dict[str, Any] | None = None) -> list[ItemRef]:
        return self.items

    def download(self, item: ItemRef, destination: Path) -> None:
        self.download_calls.append(item.item_id)
        if self.fail_first > 0:
            self.fail_first -= 1
            raise ConnectionError("transient")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(f"payload-{item.item_id}".encode())


def _manager(
    tmp_path: Path,
    *,
    config: CollectConfig | None = None,
    registry: SourceRegistry | None = None,
) -> DownloadManager:
    return DownloadManager(
        registry=registry or _registry(),
        config=config or CollectConfig(rate_limit_ms=0),
        outdir=tmp_path,
    )


def test_collect_downloads_items(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    report = manager.collect(FakeAdapter(), "test-src")
    assert report.authorized
    assert report.downloaded == 3
    assert report.failures == []
    for index in range(3):
        assert (tmp_path / "raw" / "test-src" / f"v{index}.mp4").exists()
    state = json.loads((tmp_path / "collected.json").read_text(encoding="utf-8"))
    assert len(state["items"]) == 3
    assert (tmp_path / "failures.json").exists()


def test_collect_authorization_gate(tmp_path: Path) -> None:
    registry = _registry(allowed_for_ml_training=False)
    manager = _manager(tmp_path, registry=registry)
    report = manager.collect(FakeAdapter(), "test-src")
    assert not report.authorized
    assert report.downloaded == 0
    assert report.failures[0].stage == "authorization"
    assert not (tmp_path / "raw").exists()


def test_collect_idempotent(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    manager = _manager(tmp_path)
    first = manager.collect(adapter, "test-src")
    second = manager.collect(adapter, "test-src")
    assert first.downloaded == 3
    assert second.downloaded == 0
    assert second.skipped_duplicates == 3
    assert len(adapter.download_calls) == 3


def test_collect_retries_transient_error(tmp_path: Path) -> None:
    adapter = FakeAdapter(fail_first=1)
    manager = _manager(
        tmp_path, config=CollectConfig(rate_limit_ms=0, max_retries=3, backoff_base_seconds=0)
    )
    report = manager.collect(adapter, "test-src")
    assert report.downloaded == 3
    assert report.failures == []
    assert len(adapter.download_calls) == 4


def test_collect_records_failure_after_retries(tmp_path: Path) -> None:
    adapter = FakeAdapter(fail_first=999)
    manager = _manager(
        tmp_path, config=CollectConfig(rate_limit_ms=0, max_retries=2, backoff_base_seconds=0)
    )
    report = manager.collect(adapter, "test-src")
    assert report.downloaded == 0
    assert len(report.failures) == 3
    assert all(failure.retryable for failure in report.failures)
    assert len(adapter.download_calls) == 9


def test_collect_rate_limit(tmp_path: Path) -> None:
    manager = _manager(tmp_path, config=CollectConfig(rate_limit_ms=120))
    start = time.monotonic()
    report = manager.collect(FakeAdapter(), "test-src")
    elapsed = time.monotonic() - start
    assert report.downloaded == 3
    assert elapsed >= 0.2


def test_pause_blocks_then_resume(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    manager = _manager(tmp_path)
    manager.pause("test-src")
    paused = manager.collect(adapter, "test-src")
    assert paused.failures[0].stage == "paused"
    assert adapter.download_calls == []
    manager.resume("test-src")
    resumed = manager.collect(adapter, "test-src")
    assert resumed.downloaded == 3


def test_delete_item(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.collect(FakeAdapter(), "test-src")
    assert manager.delete_item("test-src", "v0")
    assert not (tmp_path / "raw" / "test-src" / "v0.mp4").exists()
    state = json.loads((tmp_path / "collected.json").read_text(encoding="utf-8"))
    assert len(state["items"]) == 2
    assert not manager.delete_item("test-src", "missing")
