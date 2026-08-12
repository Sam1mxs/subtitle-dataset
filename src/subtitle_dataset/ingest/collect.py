"""下载管理器：授权门禁、来源级限速、退避重试、幂等与失败记录（§5.3）。"""

from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from subtitle_dataset.contracts import FailureRecord
from subtitle_dataset.media.probe import sha256_file

from .adapters.base import ItemRef, SourceAdapter
from .sources import SourceRegistry, check_authorization


class CollectedItem(BaseModel):
    """已下载条目的状态记录（运行态，不进入训练 manifest）。"""

    source_id: str
    item_id: str
    url: str
    path: str
    sha256: str
    size_bytes: int
    downloaded_at: datetime


class CollectionState(BaseModel):
    items: list[CollectedItem] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> CollectionState:
        if not path.exists():
            return cls()
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def find(self, source_id: str, item_id: str) -> CollectedItem | None:
        for item in self.items:
            if item.source_id == source_id and item.item_id == item_id:
                return item
        return None


class CollectionReport(BaseModel):
    source_id: str
    authorized: bool
    discovered: int
    downloaded: int
    skipped_duplicates: int
    failures: list[FailureRecord]


class CollectConfig(BaseModel):
    rate_limit_ms: int = Field(ge=0, default=500)
    max_retries: int = Field(ge=0, default=3)
    backoff_base_seconds: float = Field(ge=0.0, default=1.0)
    max_items: int | None = Field(default=None, ge=1)
    adapter: str = "local-http"
    adapter_options: dict[str, Any] = Field(default_factory=dict)


class DownloadManager:
    """按来源执行授权检查、限速、重试与幂等下载。"""

    def __init__(
        self,
        *,
        registry: SourceRegistry,
        config: CollectConfig,
        outdir: Path,
    ) -> None:
        self._registry = registry
        self._config = config
        self._outdir = outdir
        self._state_path = outdir / "collected.json"
        self._failures_path = outdir / "failures.json"
        self._state = CollectionState.load(self._state_path)
        self._paused: set[str] = set()
        self._last_request_at: dict[str, float] = {}

    def collect(self, adapter: SourceAdapter, source_id: str) -> CollectionReport:
        failures: list[FailureRecord] = []
        source = self._registry.get(source_id) if self._source_exists(source_id) else None
        if source is None:
            failures.append(
                FailureRecord(
                    stage="authorization",
                    input_ref=source_id,
                    error_type="UnknownSource",
                    message=f"来源未登记: {source_id}",
                    retryable=False,
                )
            )
            return self._report(source_id, authorized=False, failures=failures)
        authorization = check_authorization(source, date.today())
        if not authorization.authorized:
            failures.append(
                FailureRecord(
                    stage="authorization",
                    input_ref=source_id,
                    error_type="NotAuthorized",
                    message="；".join(authorization.reasons),
                    retryable=False,
                )
            )
            return self._report(source_id, authorized=False, failures=failures)
        if source_id in self._paused:
            failures.append(
                FailureRecord(
                    stage="paused",
                    input_ref=source_id,
                    error_type="SourcePaused",
                    message="来源已暂停",
                    retryable=True,
                )
            )
            return self._report(source_id, authorized=True, failures=failures)

        items = adapter.discover({"source_id": source_id})
        if self._config.max_items is not None:
            items = items[: self._config.max_items]

        downloaded = 0
        skipped = 0
        for item in items:
            existing = self._state.find(source_id, item.item_id)
            if existing is not None and Path(existing.path).exists():
                skipped += 1
                continue
            destination = self._destination(source_id, item)
            try:
                self._download_with_retry(adapter, source_id, item, destination)
                record = CollectedItem(
                    source_id=source_id,
                    item_id=item.item_id,
                    url=item.url,
                    path=str(destination),
                    sha256=sha256_file(destination),
                    size_bytes=destination.stat().st_size,
                    downloaded_at=datetime.now(UTC),
                )
                self._state.items = [
                    entry
                    for entry in self._state.items
                    if not (entry.source_id == source_id and entry.item_id == item.item_id)
                ] + [record]
                downloaded += 1
            except Exception as exc:  # noqa: BLE001 - 单条目失败不中断整批
                failures.append(
                    FailureRecord(
                        stage="download",
                        input_ref=f"{source_id}/{item.item_id}",
                        error_type=type(exc).__name__,
                        message=str(exc),
                        retryable=True,
                    )
                )
        self._save_state()
        self._write_failures(failures)
        return self._report(
            source_id,
            authorized=True,
            discovered=len(items),
            downloaded=downloaded,
            skipped=skipped,
            failures=failures,
        )

    def pause(self, source_id: str) -> None:
        self._paused.add(source_id)

    def resume(self, source_id: str) -> None:
        self._paused.discard(source_id)

    def delete_item(self, source_id: str, item_id: str) -> bool:
        """删除已下载条目及其状态（§5.3 删除请求）。"""
        existing = self._state.find(source_id, item_id)
        if existing is None:
            return False
        Path(existing.path).unlink(missing_ok=True)
        self._state.items = [
            entry
            for entry in self._state.items
            if not (entry.source_id == source_id and entry.item_id == item_id)
        ]
        self._save_state()
        return True

    def _download_with_retry(
        self,
        adapter: SourceAdapter,
        source_id: str,
        item: ItemRef,
        destination: Path,
    ) -> None:
        last_error: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            self._throttle(source_id)
            try:
                adapter.download(item, destination)
                return
            except Exception as exc:  # noqa: BLE001 - 网络层错误统一重试
                last_error = exc
                if attempt < self._config.max_retries:
                    time.sleep(self._config.backoff_base_seconds * (2**attempt))
        assert last_error is not None
        raise last_error

    def _throttle(self, source_id: str) -> None:
        interval = self._config.rate_limit_ms / 1000.0
        last = self._last_request_at.get(source_id)
        if last is not None:
            wait = interval - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_request_at[source_id] = time.monotonic()

    def _destination(self, source_id: str, item: ItemRef) -> Path:
        suffix = Path(item.url.split("?", 1)[0]).suffix or ".bin"
        return self._outdir / "raw" / source_id / f"{item.item_id}{suffix}"

    def _source_exists(self, source_id: str) -> bool:
        try:
            self._registry.get(source_id)
            return True
        except KeyError:
            return False

    def _report(
        self,
        source_id: str,
        *,
        authorized: bool,
        discovered: int = 0,
        downloaded: int = 0,
        skipped: int = 0,
        failures: list[FailureRecord],
    ) -> CollectionReport:
        return CollectionReport(
            source_id=source_id,
            authorized=authorized,
            discovered=discovered,
            downloaded=downloaded,
            skipped_duplicates=skipped,
            failures=failures,
        )

    def _save_state(self) -> None:
        self._outdir.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            self._state.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def _write_failures(self, failures: list[FailureRecord]) -> None:
        self._outdir.mkdir(parents=True, exist_ok=True)
        self._failures_path.write_text(
            json.dumps(
                [failure.model_dump(mode="json") for failure in failures],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
