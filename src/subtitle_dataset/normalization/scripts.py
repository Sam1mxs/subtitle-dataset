"""文本主要文字（script）判定（用于分布统计与长尾覆盖）。"""

from __future__ import annotations

import unicodedata


def detect_script(text: str) -> str:
    """按码点范围判定主要文字；有假名判日文、有谚文判韩文。"""
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return "Other"
    has_kana = any(0x3040 <= ord(ch) <= 0x30FF or 0x31F0 <= ord(ch) <= 0x31FF for ch in chars)
    has_hangul = any(0xAC00 <= ord(ch) <= 0xD7AF or 0x1100 <= ord(ch) <= 0x11FF for ch in chars)
    has_cjk = any(0x4E00 <= ord(ch) <= 0x9FFF or 0x3400 <= ord(ch) <= 0x4DBF for ch in chars)
    has_latin = any(unicodedata.name(ch, "").startswith("LATIN") for ch in chars)
    has_arabic = any(0x0600 <= ord(ch) <= 0x06FF for ch in chars)
    if has_kana:
        return "Japanese"
    if has_hangul:
        return "Korean"
    if has_cjk:
        return "CJK"
    if has_latin:
        return "Latin"
    if has_arabic:
        return "Arabic"
    return "Other"
