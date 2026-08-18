"""字体登记、glyph 覆盖检查与带记录的 fallback。"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path

from fontTools.ttLib import TTFont  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[3] / "assets" / "fonts" / "registry.json"

_CMAP_CACHE: dict[str, frozenset[int]] = {}


class FontLicense(BaseModel):
    """字体许可证信息（设计文档 §10.5 要求明确训练与再分发许可）。"""

    name: str = Field(min_length=1)
    spdx: str | None = None
    redistributable: bool
    ml_training: bool
    notes: str = ""


class FontRecord(BaseModel):
    """字体登记条目。"""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    family: str
    file: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license: FontLicense
    source_url: str | None = None
    registered_at: date
    optional: bool = Field(default=False, description="系统字体可缺失（缺文件不报错）")


class FontRegistry(BaseModel):
    """字体登记表；记录文件的 SHA-256 与许可证，禁止未登记字体进入管线。"""

    version: str
    fonts: list[FontRecord]

    @classmethod
    def load(cls, path: Path = DEFAULT_REGISTRY_PATH) -> FontRegistry:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def get(self, font_id: str) -> FontRecord:
        for record in self.fonts:
            if record.id == font_id:
                return record
        raise KeyError(f"字体未登记: {font_id}")

    def resolve_path(self, record: FontRecord) -> Path:
        """相对路径按登记表所在目录解析，绝对路径原样使用。"""
        path = Path(record.file)
        if not path.is_absolute():
            path = DEFAULT_REGISTRY_PATH.parent / path
        return path

    def validate_files(self) -> list[str]:
        """检查所有登记字体文件存在且 SHA-256 匹配，返回错误列表。"""
        errors: list[str] = []
        for record in self.fonts:
            path = self.resolve_path(record)
            if not path.exists():
                if not record.optional:
                    errors.append(f"{record.id}: 文件不存在 {path}")
                continue
            if record.optional:
                # 可选系统字体会随环境版本变化，不强制哈希一致
                continue
            digest = sha256(path.read_bytes()).hexdigest()
            if digest != record.sha256:
                errors.append(f"{record.id}: SHA-256 不匹配（期望 {record.sha256}，实际 {digest}）")
        return errors

    def resolve(
        self,
        text: str,
        font_ids: list[str],
        *,
        require_ml_training: bool = False,
    ) -> FontResolution:
        """按候选顺序选择第一个能覆盖全部字符的字体。

        ``missing_chars`` 记录每个因缺字被跳过的候选及其缺失字符；
        若没有任何候选可用则抛出 :class:`FontCoverageError`。
        """
        missing_by_font: dict[str, list[str]] = {}
        for font_id in font_ids:
            record = self.get(font_id)
            missing = sorted(glyph_coverage(self.resolve_path(record), text))
            if missing:
                missing_by_font[font_id] = missing
                continue
            if require_ml_training and not record.license.ml_training:
                raise FontLicenseError(
                    f"字体 {font_id} 未授权用于 ML 训练（license.ml_training=False）"
                )
            return FontResolution(
                font_id=font_id,
                font_path=str(self.resolve_path(record)),
                font_sha256=record.sha256,
                fallback_used=font_id != font_ids[0],
                missing_chars=missing_by_font,
            )
        raise FontCoverageError(f"候选字体均无法覆盖全部字符: {missing_by_font}")


@dataclass(frozen=True)
class FontResolution:
    """字体解析结果：实际使用的字体与 fallback 记录。"""

    font_id: str
    font_path: str
    font_sha256: str
    fallback_used: bool
    missing_chars: dict[str, list[str]]


class FontCoverageError(ValueError):
    """没有任何候选字体能覆盖全部字符。"""


class FontLicenseError(ValueError):
    """所选字体不满足许可证要求。"""


def glyph_coverage(font_path: Path, text: str) -> set[str]:
    """返回字体无法覆盖的字符集合（基于 cmap，不含空白/控制字符）。"""
    cmap = _load_cmap(font_path)
    return {ch for ch in _checkable_chars(text) if ord(ch) not in cmap}


def _load_cmap(font_path: Path) -> frozenset[int]:
    key = str(font_path)
    if key not in _CMAP_CACHE:
        kwargs: dict[str, int] = {}
        if font_path.suffix.lower() == ".ttc":
            kwargs["fontNumber"] = 0
        font = TTFont(key, **kwargs)
        try:
            cmap = font.getBestCmap() or {}
        finally:
            font.close()
        _CMAP_CACHE[key] = frozenset(cmap)
    return _CMAP_CACHE[key]


def _checkable_chars(text: str) -> set[str]:
    return {
        ch for ch in set(text) if not ch.isspace() and not unicodedata.category(ch).startswith("C")
    }
