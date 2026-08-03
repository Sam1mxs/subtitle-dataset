"""构建清单与失败记录。"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from .base import Split
from .sample import Sample


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SampleManifest(BaseModel):
    """一个 split 的样本清单。"""

    dataset_version: str
    split: Split
    samples: list[Sample] = Field(default_factory=list)
    created_at: datetime | None = None


class FailureRecord(BaseModel):
    """处理失败记录，写入 failures manifest，不允许静默丢弃。"""

    stage: str
    input_ref: str
    error_type: str
    message: str
    retryable: bool
    failed_at: datetime = Field(default_factory=_utc_now)
