"""端到端渲染管线。"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from tests.helpers import (
    SYSTEM_CJK_FONT,
    default_render_config,
    make_clean_image,
    png_sha256,
)

from subtitle_dataset.qa import check_strict_pairing
from subtitle_dataset.rendering import PillowRenderer


@pytest.fixture(scope="module")
def clean() -> Image.Image:
    if not Path(SYSTEM_CJK_FONT).exists():
        pytest.skip("缺少系统字体 msyh.ttc")
    return make_clean_image()


def test_full_render_strict_pairing(clean: Image.Image) -> None:
    result = PillowRenderer().render(clean, default_render_config())
    assert result.rendered.size == clean.size
    assert result.alpha_mask.size == clean.size
    assert result.inpaint_mask.size == clean.size
    check = check_strict_pairing(
        clean,
        result.rendered,
        result.inpaint_mask,
        effect_bbox=result.effect_bbox_xyxy,
    )
    assert check.ok


def test_effect_bbox_center_in_band(clean: Image.Image) -> None:
    result = PillowRenderer().render(clean, default_render_config())
    _, y0, _, y1 = result.effect_bbox_xyxy
    center_y = (y0 + y1) / 2 / clean.height
    assert 0.60 <= center_y <= 0.90


def test_render_is_deterministic(clean: Image.Image) -> None:
    first = PillowRenderer().render(clean, default_render_config())
    second = PillowRenderer().render(clean, default_render_config())
    assert png_sha256(first.rendered) == png_sha256(second.rendered)
    assert first.effect_bbox_xyxy == second.effect_bbox_xyxy
    assert first.config_sha256 == second.config_sha256


def test_multiline_line_bboxes_inside_image(clean: Image.Image) -> None:
    result = PillowRenderer().render(clean, default_render_config(text="第一行\n第二行"))
    width, height = clean.size
    assert len(result.line_bboxes_xyxy) == 2
    for x0, y0, x1, y1 in result.line_bboxes_xyxy:
        assert 0 <= x0 < x1 <= width
        assert 0 <= y0 < y1 <= height


def test_out_of_bounds_raises(clean: Image.Image) -> None:
    config = default_render_config()
    config.center = (0.5, 0.0)
    with pytest.raises(ValueError, match="垂直越界"):
        PillowRenderer().render(clean, config)


def test_cli_render(tmp_path: Path) -> None:
    from subtitle_dataset.cli import main

    clean_path = tmp_path / "clean.png"
    make_clean_image().save(clean_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(default_render_config().model_dump_json(), encoding="utf-8")
    outdir = tmp_path / "out"
    assert (
        main(
            [
                "render",
                "--clean",
                str(clean_path),
                "--config",
                str(config_path),
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )
    for name in ("rendered.png", "alpha.png", "mask.png", "metadata.json"):
        assert (outdir / name).exists()
