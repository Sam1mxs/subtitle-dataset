"""版本化文本规范化：(language, version) → 有序规则集。"""

from __future__ import annotations

from pydantic import BaseModel

from .rules import RULES

DEFAULT_VERSION = "1.0"

# 未来按语言注册特定规则集，例如：
# {"ja": {"1.0": (*_GENERIC_1_0, "halfwidth_kana")}}
_RULE_SETS: dict[str, dict[str, tuple[str, ...]]] = {
    "*": {
        "1.0": (
            "fullwidth_ascii",
            "ideographic_space",
            "newlines",
            "whitespace",
            "punctuation_spacing",
            "strip_lines",
        ),
    },
}


class UnknownNormalizationError(ValueError):
    """未知的 (language, version) 规则集。"""


class NormalizationResult(BaseModel):
    normalized: str
    language: str
    version: str
    applied_rules: list[str]


class TextNormalizer:
    """按语言与版本执行有序规范化规则。"""

    def __init__(self, language: str = "*", version: str = DEFAULT_VERSION) -> None:
        self._language = language
        self._version = version
        self._rules = [(rule_id, RULES[rule_id]) for rule_id in _rule_ids(language, version)]

    def normalize(self, text: str) -> NormalizationResult:
        normalized = text
        applied: list[str] = []
        for rule_id, rule in self._rules:
            normalized = rule(normalized)
            applied.append(rule_id)
        return NormalizationResult(
            normalized=normalized,
            language=self._language,
            version=self._version,
            applied_rules=applied,
        )


def _rule_ids(language: str, version: str) -> tuple[str, ...]:
    rule_sets = _RULE_SETS.get(language) or _RULE_SETS.get("*")
    if rule_sets is None or version not in rule_sets:
        raise UnknownNormalizationError(f"未知规范化规则集: language={language}, version={version}")
    return rule_sets[version]
