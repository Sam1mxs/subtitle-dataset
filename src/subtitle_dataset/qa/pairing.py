"""严格配对质检：clean 与 rendered 必须仅在 mask 内不同。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from PIL import Image, ImageChops


@dataclass(frozen=True)
class PairingCheck:
    same_size: bool
    max_abs_diff_outside_mask: int
    changed_bbox_xyxy: tuple[int, int, int, int] | None
    effect_bbox_xyxy: tuple[int, int, int, int] | None
    changes_inside_effect_bbox: bool
    ok: bool


def check_strict_pairing(
    clean: Image.Image,
    rendered: Image.Image,
    inpaint_mask: Image.Image,
    *,
    effect_bbox: tuple[int, int, int, int] | None = None,
) -> PairingCheck:
    """校验尺寸一致、mask 外逐像素相同、差异区域被 mask/effect_bbox 覆盖。"""
    clean_rgb = clean.convert("RGB")
    rendered_rgb = rendered.convert("RGB")
    same_size = clean_rgb.size == rendered_rgb.size == inpaint_mask.size
    if not same_size:
        return PairingCheck(
            same_size=False,
            max_abs_diff_outside_mask=-1,
            changed_bbox_xyxy=None,
            effect_bbox_xyxy=effect_bbox,
            changes_inside_effect_bbox=False,
            ok=False,
        )

    diff = ImageChops.difference(clean_rgb, rendered_rgb)
    outside = ImageChops.invert(inpaint_mask).convert("RGB")
    leak = ImageChops.multiply(diff, outside)
    band_extrema = cast(tuple[tuple[int, int], ...], leak.getextrema())
    max_abs_diff_outside_mask = max(hi for _, hi in band_extrema)

    changed_bbox = diff.getbbox()
    changes_inside_effect_bbox = True
    if changed_bbox is not None and effect_bbox is not None:
        cx0, cy0, cx1, cy1 = changed_bbox
        ex0, ey0, ex1, ey1 = effect_bbox
        changes_inside_effect_bbox = ex0 <= cx0 and ey0 <= cy0 and cx1 <= ex1 and cy1 <= ey1

    ok = max_abs_diff_outside_mask == 0 and changes_inside_effect_bbox
    return PairingCheck(
        same_size=True,
        max_abs_diff_outside_mask=max_abs_diff_outside_mask,
        changed_bbox_xyxy=changed_bbox,
        effect_bbox_xyxy=effect_bbox,
        changes_inside_effect_bbox=changes_inside_effect_bbox,
        ok=ok,
    )
