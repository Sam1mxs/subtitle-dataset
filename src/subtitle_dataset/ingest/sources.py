"""来源登记表（设计文档 §4）：许可证、授权与合规元数据。"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "sources" / "registry.json"
)


class LicenseStatus(StrEnum):
    AUTHORIZED = "authorized"
    PENDING = "pending"
    UNKNOWN = "unknown"
    REJECTED = "rejected"


class SourceRecord(BaseModel):
    """一个已登记数据来源；未通过授权检查的数据不得进入下载/训练管线。"""

    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    platform: str = Field(min_length=1)
    source_url_or_hash: str | None = None
    creator_id_or_hash: str | None = None
    license_status: LicenseStatus = LicenseStatus.UNKNOWN
    allowed_to_download: bool = False
    allowed_for_derivative_work: bool = False
    allowed_for_ml_training: bool = False
    allowed_to_redistribute: bool = False
    authorization_reference: str | None = None
    authorization_start_at: date | None = None
    authorization_expire_at: date | None = None
    crawled_at: datetime | None = None


class SourceRegistry(BaseModel):
    version: str
    sources: list[SourceRecord]

    @classmethod
    def load(cls, path: Path = DEFAULT_REGISTRY_PATH) -> SourceRegistry:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def get(self, source_id: str) -> SourceRecord:
        for source in self.sources:
            if source.source_id == source_id:
                return source
        raise KeyError(f"来源未登记: {source_id}")

    def by_platform(self, platform: str) -> list[SourceRecord]:
        return [source for source in self.sources if source.platform == platform]

    def validate_registry(self) -> list[str]:
        """返回登记表错误列表：重复 ID、授权一致性、时间窗。"""
        errors: list[str] = []
        seen: set[str] = set()
        for source in self.sources:
            if source.source_id in seen:
                errors.append(f"重复 source_id: {source.source_id}")
            seen.add(source.source_id)
            if source.allowed_for_ml_training and (
                source.license_status is not LicenseStatus.AUTHORIZED
            ):
                errors.append(
                    f"{source.source_id}: allowed_for_ml_training=True "
                    "但 license_status 不是 authorized"
                )
            if (
                source.authorization_start_at is not None
                and source.authorization_expire_at is not None
                and source.authorization_expire_at < source.authorization_start_at
            ):
                errors.append(f"{source.source_id}: 授权到期日早于生效日")
        return errors


class SourceAuthorization(BaseModel):
    source_id: str
    authorized: bool
    reasons: list[str]


def check_authorization(source: SourceRecord, at: date) -> SourceAuthorization:
    """判断来源在指定日期是否可用于 ML 训练（全部条件通过才算授权）。"""
    reasons: list[str] = []
    if source.license_status is not LicenseStatus.AUTHORIZED:
        reasons.append(f"license_status={source.license_status.value}，需要 authorized")
    if not source.allowed_to_download:
        reasons.append("allowed_to_download=False")
    if not source.allowed_for_derivative_work:
        reasons.append("allowed_for_derivative_work=False")
    if not source.allowed_for_ml_training:
        reasons.append("allowed_for_ml_training=False")
    if source.authorization_start_at is not None and at < source.authorization_start_at:
        reasons.append(f"授权未生效（{at} < {source.authorization_start_at}）")
    if source.authorization_expire_at is not None and at > source.authorization_expire_at:
        reasons.append(f"授权已过期（{at} > {source.authorization_expire_at}）")
    return SourceAuthorization(
        source_id=source.source_id,
        authorized=not reasons,
        reasons=reasons,
    )
