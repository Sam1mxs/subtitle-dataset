"""采样-渲染-校验闭环。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.helpers import make_clean_image

from subtitle_dataset.contracts import SourceInfo, Split, Transform
from subtitle_dataset.sampling import (
    RangeF,
    SampleSampler,
    SamplingConfig,
    SamplingExhaustedError,
)

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


def test_sample_with_source_and_transform(config: SamplingConfig) -> None:
    clean = make_clean_image()
    source = SourceInfo(
        platform="bilibili",
        video_sha256="a" * 64,
        native_frame_index=45,
        pts=45000,
        timestamp_ms=1500,
        time_base={"num": 1, "den": 30000},
        frame_rate={"avg_num": 30, "avg_den": 1, "r_num": 30, "r_den": 1, "is_vfr": False},
    )
    transform = Transform(crop_xywh=(0, 0, 360, 640), target_size=(360, 640))
    sample = SampleSampler(config).sample(
        clean,
        0,
        source=source,
        transform=transform,
    )
    assert sample.record.source == source
    assert sample.record.transform == transform
    assert sample.record.build is not None
    assert sample.record.build.dataset_version == "v1"
    assert sample.record.build.seed == sample.record.sample_seed
    assert sample.record.build.renderer_version


def test_transform_size_mismatch_rejected(config: SamplingConfig) -> None:
    transform = Transform(crop_xywh=(0, 0, 360, 640), target_size=(720, 1280))
    with pytest.raises(ValueError, match="不一致"):
        SampleSampler(config).sample(make_clean_image(), 0, transform=transform)


def test_native_subtitle_in_target_region_rejected(config: SamplingConfig) -> None:
    from PIL import Image, ImageDraw, ImageFont
    from tests.helpers import NOTO_FONT

    image = Image.new("RGB", (360, 640), (40, 44, 56))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(NOTO_FONT), 28)
    draw.text(
        (180, 550),
        "原生字幕",
        font=font,
        fill=(255, 255, 255),
        anchor="mm",
        stroke_width=2,
        stroke_fill=(0, 0, 0),
    )
    strict = config.model_copy(deep=True)
    strict.max_attempts = 3
    strict.position.center_y_range = RangeF(min=0.85, max=0.85)
    with pytest.raises(SamplingExhaustedError):
        SampleSampler(strict).sample(image, 0)


def test_text_policy_ok_recorded(config: SamplingConfig) -> None:
    sample = SampleSampler(config).sample(make_clean_image(), 0)
    assert sample.record.text_policy_ok is True
    assert sample.record.text_policy_reasons == []


def test_sample_split_field(config: SamplingConfig) -> None:
    sample = SampleSampler(config).sample(make_clean_image(), 0, split=Split.TRAIN)
    assert sample.record.split == Split.TRAIN


def test_normalization_applied_with_language(config: SamplingConfig, tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("今天ＡＢＣ一起吃饭　。\n", encoding="utf-8")
    strict = config.model_copy(deep=True)
    strict.corpus_path = str(corpus)
    strict.single_line_prob = 1.0
    sample = SampleSampler(strict).sample(make_clean_image(), 0)
    assert sample.record.text == "今天ＡＢＣ一起吃饭　。"
    assert sample.record.text_normalized == "今天ABC一起吃饭。"
    assert sample.record.normalization_version == "1.0"
    assert sample.record.language == "zh"
    assert sample.record.script == "CJK"


def test_event_default_single_frame(config: SamplingConfig) -> None:
    sample = SampleSampler(config).sample(make_clean_image(), 0)
    event = sample.record.event
    assert event is not None
    assert event.frames_per_event == 1
    assert sample.record.event_frame_index == 0
    assert sample.record.event_frames_total == 1
    assert event.end_time_ms - event.start_time_ms == event.duration_ms
    assert event.native_duration_frames == (
        event.end_native_frame_exclusive - event.start_native_frame
    )


def test_event_timestamp_contains_source_frame(config: SamplingConfig) -> None:
    source = SourceInfo(
        platform="bilibili",
        video_sha256="a" * 64,
        native_frame_index=45,
        pts=45000,
        timestamp_ms=1500,
        time_base={"num": 1, "den": 30000},
        frame_rate={"avg_num": 30, "avg_den": 1, "r_num": 30, "r_den": 1, "is_vfr": False},
    )
    sample = SampleSampler(config).sample(make_clean_image(), 0, source=source)
    event = sample.record.event
    assert event is not None
    assert event.start_time_ms <= source.timestamp_ms < event.end_time_ms


def test_frames_per_event_three(config: SamplingConfig) -> None:
    strict = config.model_copy(deep=True)
    strict.frames_per_event = 3
    samples = SampleSampler(strict).sample_event(make_clean_image(), 0)
    assert len(samples) == 3
    event_ids = set()
    for sample in samples:
        event = sample.record.event
        assert event is not None
        event_ids.add(event.event_id)
    assert len(event_ids) == 1
    assert [sample.record.event_frame_index for sample in samples] == [0, 1, 2]
    assert all(sample.record.event_frames_total == 3 for sample in samples)
