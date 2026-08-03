"""golden 测试：固定字体 + 固定配置的渲染输出摘要。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.helpers import (
    SYSTEM_CJK_FONT,
    default_render_config,
    make_clean_image,
    png_sha256,
)

from subtitle_dataset.rendering import PillowRenderer

GOLDEN_DIR = Path(__file__).resolve().parent
GOLDEN_FILE = GOLDEN_DIR / "golden.json"


def test_golden_render_matches() -> None:
    if not Path(SYSTEM_CJK_FONT).exists():
        pytest.skip("缺少系统字体 msyh.ttc")
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    result = PillowRenderer().render(make_clean_image(), default_render_config())
    assert png_sha256(result.rendered) == golden["rendered_sha256"]
    assert png_sha256(result.alpha_mask) == golden["alpha_sha256"]
    assert png_sha256(result.inpaint_mask) == golden["inpaint_mask_sha256"]
    assert result.effect_bbox_xyxy == tuple(golden["effect_bbox_xyxy"])
    assert result.config_sha256 == golden["config_sha256"]
