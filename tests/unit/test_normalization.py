"""版本化文本规范化。"""

from __future__ import annotations

import pytest

from subtitle_dataset.normalization import (
    TextNormalizer,
    UnknownNormalizationError,
    detect_script,
)


def _normalize(text: str) -> str:
    return TextNormalizer().normalize(text).normalized


def test_fullwidth_ascii_to_halfwidth() -> None:
    assert _normalize("ＡＢＣ１２３＠") == "ABC123@"


def test_ideographic_space_and_whitespace() -> None:
    assert _normalize("你　好  吗") == "你 好 吗"


def test_newlines_normalized_and_lines_stripped() -> None:
    assert _normalize(" 第一行 \r\n第二行\r") == "第一行\n第二行"


def test_chinese_punctuation_preserved() -> None:
    assert _normalize("你好，世界！？") == "你好，世界！？"


def test_pipeline_combined() -> None:
    assert _normalize("今天ＡＢＣ一起吃饭　。\r\n  明天见  ") == "今天ABC一起吃饭。\n明天见"


def test_normalization_idempotent() -> None:
    normalizer = TextNormalizer()
    once = normalizer.normalize(" ＡＢＣ  ，你好  ").normalized
    twice = normalizer.normalize(once).normalized
    assert once == twice


def test_result_records_version_and_rules() -> None:
    result = TextNormalizer().normalize("ＡＢＣ")
    assert result.version == "1.0"
    assert result.applied_rules == [
        "fullwidth_ascii",
        "ideographic_space",
        "newlines",
        "whitespace",
        "punctuation_spacing",
        "strip_lines",
    ]


def test_unknown_version_rejected() -> None:
    with pytest.raises(UnknownNormalizationError):
        TextNormalizer(version="9.9").normalize("你好")


def test_language_falls_back_to_generic_rules() -> None:
    result = TextNormalizer(language="ja").normalize("ＡＢＣ")
    assert result.language == "ja"
    assert result.normalized == "ABC"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("今天晚上一起吃饭", "CJK"),
        ("Hello world", "Latin"),
        ("こんにちは", "Japanese"),
        ("안녕하세요", "Korean"),
        ("مرحبا بالعالم", "Arabic"),
        ("今晚ABC一起吃饭", "CJK"),
    ],
)
def test_detect_script(text: str, expected: str) -> None:
    assert detect_script(text) == expected
