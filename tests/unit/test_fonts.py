"""字体登记、glyph 覆盖与 fallback。"""

from __future__ import annotations

import pytest

from subtitle_dataset.rendering import FontCoverageError, FontLicenseError, FontRegistry
from subtitle_dataset.rendering.fonts import glyph_coverage

TEXT = "今天晚上一起吃饭"


def test_registry_loads_and_files_valid() -> None:
    registry = FontRegistry.load()
    assert registry.validate_files() == []
    assert {"noto-sans-cjk-sc", "msyh", "dejavu-sans"} <= {f.id for f in registry.fonts}


def test_glyph_coverage_cjk_fonts_cover_chinese() -> None:
    registry = FontRegistry.load()
    for font_id in ("noto-sans-cjk-sc", "msyh"):
        path = registry.resolve_path(registry.get(font_id))
        assert glyph_coverage(path, TEXT) == set()


def test_glyph_coverage_latin_font_misses_chinese() -> None:
    registry = FontRegistry.load()
    path = registry.resolve_path(registry.get("dejavu-sans"))
    assert glyph_coverage(path, TEXT)


def test_primary_font_direct_hit() -> None:
    registry = FontRegistry.load()
    resolution = registry.resolve(TEXT, ["noto-sans-cjk-sc"])
    assert resolution.font_id == "noto-sans-cjk-sc"
    assert not resolution.fallback_used
    assert resolution.missing_chars == {}


def test_fallback_picks_covering_font_and_records_missing() -> None:
    registry = FontRegistry.load()
    resolution = registry.resolve(TEXT, ["dejavu-sans", "noto-sans-cjk-sc"])
    assert resolution.font_id == "noto-sans-cjk-sc"
    assert resolution.fallback_used
    assert resolution.missing_chars["dejavu-sans"]


def test_no_candidate_raises_coverage_error() -> None:
    registry = FontRegistry.load()
    with pytest.raises(FontCoverageError, match="dejavu-sans"):
        registry.resolve(TEXT, ["dejavu-sans"])


def test_ml_training_license_gate() -> None:
    registry = FontRegistry.load()
    with pytest.raises(FontLicenseError, match="ml_training"):
        registry.resolve(TEXT, ["msyh"], require_ml_training=True)
    resolution = registry.resolve(TEXT, ["noto-sans-cjk-sc"], require_ml_training=True)
    assert resolution.font_id == "noto-sans-cjk-sc"


def test_validate_files_detects_wrong_sha() -> None:
    registry = FontRegistry.load()
    payload = registry.model_dump(mode="json")
    payload["fonts"][0]["sha256"] = "0" * 64
    broken = FontRegistry.model_validate(payload)
    errors = broken.validate_files()
    assert any("SHA-256" in error for error in errors)
