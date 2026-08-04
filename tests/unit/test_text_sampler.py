"""文本语料与行数采样。"""

from __future__ import annotations

import random
from pathlib import Path

from subtitle_dataset.sampling import TextCorpus, TextSampler


def test_corpus_skips_comments_and_empty_lines(tmp_path: Path) -> None:
    path = tmp_path / "corpus.txt"
    path.write_text("# comment\n\n第一行\n\n# another\n第二行\n", encoding="utf-8")
    corpus = TextCorpus.load(path)
    assert len(corpus._lines) == 2  # noqa: SLF001


def test_corpus_rejects_empty() -> None:
    try:
        TextCorpus(["# only comment", ""])
    except ValueError as exc:
        assert "语料为空" in str(exc)
    else:
        raise AssertionError("空语料应当被拒绝")


def test_text_sampler_single_and_double_lines() -> None:
    corpus = TextCorpus(["甲", "乙", "丙", "丁"])
    sampler = TextSampler(corpus, single_line_prob=0.5, rng=random.Random(3))
    sizes = {len(sampler.sample()) for _ in range(50)}
    assert sizes == {1, 2}
