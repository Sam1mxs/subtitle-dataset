"""采样-渲染-校验闭环。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.helpers import make_clean_image

from subtitle_dataset.sampling import SampleSampler, SamplingConfig

SAMPLING_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "sampling" / "default.json"


@pytest.fixture(scope="module")
def config() -> SamplingConfig:
    if not SAMPLING_CONFIG.exists():
        pytest.skip("缺少采样配置")
    return SamplingConfig.model_validate_json(SAMPLING_CONFIG.read_text(encoding="utf-8"))


def test_generate_samples_are_valid_and_deterministic(config: SamplingConfig) -> None:
    clean = make_clean_image()
    first = [SampleSampler(config).sample(clean, i) for i in range(8)]
    second = [SampleSampler(config).sample(clean, i) for i in range(8)]

    for sample in first:
        assert sample.record.pairing_ok
        assert sample.record.max_abs_diff_outside_mask == 0
        assert sample.record.duration_ms >= 130
        assert 0.60 <= _center_y(sample.record.effect_bbox_xyxy, clean.height) <= 0.90

    assert [s.record.model_dump() for s in first] == [s.record.model_dump() for s in second]
    assert len({s.record.sample_seed for s in first}) == len(first)
    assert all(130 <= s.record.duration_ms <= 4000 for s in first)


def _center_y(bbox: tuple[int, int, int, int], height: int) -> float:
    _, y0, _, y1 = bbox
    return (y0 + y1) / 2 / height


def test_cli_generate_writes_files(config: SamplingConfig, tmp_path: Path) -> None:
    from subtitle_dataset.cli import main

    clean_path = tmp_path / "clean.png"
    make_clean_image().save(clean_path)
    outdir = tmp_path / "out"
    assert (
        main(
            [
                "generate",
                "--clean",
                str(clean_path),
                "--config",
                str(SAMPLING_CONFIG),
                "--outdir",
                str(outdir),
                "--n",
                "3",
            ]
        )
        == 0
    )
    manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["n"] == 3
    for index in range(3):
        sample_dir = outdir / "samples" / f"{index:05d}"
        assert (sample_dir / "rendered.png").exists()
        assert (sample_dir / "alpha.png").exists()
        assert (sample_dir / "mask.png").exists()
        record = json.loads((sample_dir / "sample.json").read_text(encoding="utf-8"))
        assert record["pairing_ok"]
