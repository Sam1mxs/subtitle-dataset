"""字幕文本语料与行数采样。"""

from __future__ import annotations

import random
from collections.abc import Sequence
from pathlib import Path


class TextCorpus:
    """从 UTF-8 文本加载字幕语料；# 开头与空行被忽略。"""

    def __init__(self, lines: Sequence[str]) -> None:
        cleaned = [
            line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")
        ]
        if not cleaned:
            raise ValueError("字幕语料为空")
        self._lines = tuple(cleaned)

    @classmethod
    def load(cls, path: Path) -> TextCorpus:
        return cls(path.read_text(encoding="utf-8").splitlines())

    def sample(self, rng: random.Random) -> str:
        return rng.choice(self._lines)


class TextSampler:
    """按概率采样单行/双行字幕。"""

    def __init__(self, corpus: TextCorpus, single_line_prob: float, rng: random.Random) -> None:
        self._corpus = corpus
        self._single_line_prob = single_line_prob
        self._rng = rng

    def sample(self) -> list[str]:
        if self._rng.random() < self._single_line_prob:
            return [self._corpus.sample(self._rng)]
        return [self._corpus.sample(self._rng), self._corpus.sample(self._rng)]
