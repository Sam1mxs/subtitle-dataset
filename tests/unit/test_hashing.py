"""确定性哈希与 canonical 序列化。"""

from __future__ import annotations

from typing import Any

import pytest

from subtitle_dataset.contracts import (
    TimeBase,
    canonical_dumps,
    compute_sample_id,
    config_sha256,
    sha256_hex,
)


def test_canonical_dumps_sorts_keys() -> None:
    assert canonical_dumps({"b": 1, "a": 2}) == canonical_dumps({"a": 2, "b": 1})
    assert canonical_dumps({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_sha256_hex_is_stable() -> None:
    assert sha256_hex("今天一起吃饭") == sha256_hex("今天一起吃饭")
    assert len(sha256_hex("x")) == 64


def test_config_sha256_ignores_key_order() -> None:
    assert config_sha256({"seed": 1, "styles": {"font": "f"}}) == config_sha256(
        {"styles": {"font": "f"}, "seed": 1}
    )


def test_sample_id_changes_with_each_component() -> None:
    base: dict[str, Any] = {
        "dataset_version": "v1",
        "video_sha256": "a" * 64,
        "native_frame_index": 381,
        "pts": 38148,
        "crop_xywh": (0, 0, 1080, 1920),
        "event_id": "event-001",
        "style_seed": 42,
    }
    sample_id = compute_sample_id(**base)
    assert sample_id == compute_sample_id(**base)
    for key in base:
        changed = dict(base)
        value = base[key]
        if key == "crop_xywh":
            changed[key] = (value[0] + 1, value[1], value[2], value[3])
        elif isinstance(value, str):
            changed[key] = value + "x"
        else:
            changed[key] = value + 1
        assert compute_sample_id(**changed) != sample_id, key


@pytest.mark.parametrize(
    ("ticks", "time_base", "expected_ms"),
    [
        (38148, {"num": 1, "den": 3000}, 12716),
        (36000, {"num": 1, "den": 3000}, 12000),
        (100, {"num": 1, "den": 25}, 4000),
    ],
)
def test_ticks_to_ms(ticks: int, time_base: dict[str, int], expected_ms: int) -> None:
    assert TimeBase.model_validate(time_base).ticks_to_ms(ticks) == expected_ms
