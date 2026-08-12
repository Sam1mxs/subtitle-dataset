"""规范化规则：纯函数 str -> str，每个规则有稳定 id（§10.5）。"""

from __future__ import annotations

import re
from collections.abc import Callable

Rule = Callable[[str], str]

RULES: dict[str, Rule] = {}

# 保留全角形式的中文标点（不映射到半角，保持字形与标签一致）
_PRESERVE_FULLWIDTH_PUNCTUATION = {
    0xFF01,  # ！
    0xFF02,  # ＂
    0xFF07,  # ＇
    0xFF08,  # （
    0xFF09,  # ）
    0xFF0C,  # ，
    0xFF0E,  # ．
    0xFF1A,  # ：
    0xFF1B,  # ；
    0xFF1F,  # ？
    0xFF5B,  # ｛
    0xFF5D,  # ｝
}


def _register(rule_id: str) -> Callable[[Rule], Rule]:
    def decorator(func: Rule) -> Rule:
        RULES[rule_id] = func
        return func

    return decorator


@_register("fullwidth_ascii")
def fullwidth_ascii(text: str) -> str:
    """全角 ASCII → 半角（减 0xFEE0），中文全角标点保留。"""
    table = {
        code: chr(code - 0xFEE0)
        for code in range(0xFF01, 0xFF5F)
        if code not in _PRESERVE_FULLWIDTH_PUNCTUATION
    }
    return text.translate(table)


@_register("ideographic_space")
def ideographic_space(text: str) -> str:
    """全角空格 U+3000 → 普通空格。"""
    return text.replace("\u3000", " ")


@_register("newlines")
def normalize_newlines(text: str) -> str:
    """统一换行符为 \\n。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


@_register("whitespace")
def collapse_whitespace(text: str) -> str:
    """折叠空格/Tab 连续串为单个空格（不影响换行）。"""
    return re.sub(r"[ \t]+", " ", text)


@_register("punctuation_spacing")
def punctuation_spacing(text: str) -> str:
    """中文标点前不留空格（开括号后不留空格）。"""
    text = re.sub(r"[ \t]+(?=[，。！？；：、）】》」』])", "", text)
    text = re.sub(r"(?<=[（【《「『])[ \t]+", "", text)
    return text


@_register("strip_lines")
def strip_lines(text: str) -> str:
    """每行去首尾空白，丢弃空行（字幕不允许空行）。"""
    return "\n".join(line.strip() for line in text.split("\n") if line.strip())
