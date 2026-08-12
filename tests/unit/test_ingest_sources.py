"""来源登记表模型与授权检查。"""

from __future__ import annotations

from datetime import date
from typing import Any

from subtitle_dataset.ingest import (
    LicenseStatus,
    SourceRecord,
    SourceRegistry,
    check_authorization,
)


def _record(**overrides: Any) -> SourceRecord:
    base: dict[str, Any] = {
        "source_id": "src-001",
        "platform": "bilibili",
        "license_status": "authorized",
        "allowed_to_download": True,
        "allowed_for_derivative_work": True,
        "allowed_for_ml_training": True,
        "allowed_to_redistribute": False,
        "authorization_start_at": "2026-01-01",
        "authorization_expire_at": "2026-12-31",
    }
    base.update(overrides)
    return SourceRecord(**base)


def test_authorized_within_window() -> None:
    result = check_authorization(_record(), date(2026, 6, 1))
    assert result.authorized
    assert result.reasons == []


def test_expired_rejected() -> None:
    result = check_authorization(_record(), date(2027, 1, 1))
    assert not result.authorized
    assert any("过期" in reason for reason in result.reasons)


def test_not_yet_valid_rejected() -> None:
    result = check_authorization(_record(), date(2025, 12, 31))
    assert not result.authorized
    assert any("未生效" in reason for reason in result.reasons)


def test_ml_flag_required() -> None:
    result = check_authorization(
        _record(allowed_for_ml_training=False),
        date(2026, 6, 1),
    )
    assert not result.authorized
    assert "allowed_for_ml_training=False" in result.reasons


def test_status_must_be_authorized() -> None:
    result = check_authorization(
        _record(license_status=LicenseStatus.PENDING),
        date(2026, 6, 1),
    )
    assert not result.authorized
    assert any("license_status" in reason for reason in result.reasons)


def test_registry_get_and_by_platform() -> None:
    registry = SourceRegistry.model_validate(
        {
            "version": "1",
            "sources": [
                _record().model_dump(mode="json"),
                _record(source_id="src-002").model_dump(mode="json"),
            ],
        }
    )
    assert registry.get("src-002").source_id == "src-002"
    assert len(registry.by_platform("bilibili")) == 2


def test_registry_validate_duplicate_id() -> None:
    registry = SourceRegistry.model_validate(
        {
            "version": "1",
            "sources": [
                _record().model_dump(mode="json"),
                _record().model_dump(mode="json"),
            ],
        }
    )
    assert any("重复 source_id" in error for error in registry.validate_registry())


def test_registry_validate_ml_requires_authorized() -> None:
    registry = SourceRegistry.model_validate(
        {
            "version": "1",
            "sources": [
                _record(
                    license_status=LicenseStatus.UNKNOWN,
                    allowed_for_ml_training=True,
                ).model_dump(mode="json")
            ],
        }
    )
    assert any("allowed_for_ml_training=True" in error for error in registry.validate_registry())


def test_registry_validate_expire_before_start() -> None:
    registry = SourceRegistry.model_validate(
        {
            "version": "1",
            "sources": [
                _record(
                    authorization_start_at="2026-06-01",
                    authorization_expire_at="2026-01-01",
                ).model_dump(mode="json")
            ],
        }
    )
    assert any("授权到期日早于生效日" in error for error in registry.validate_registry())
