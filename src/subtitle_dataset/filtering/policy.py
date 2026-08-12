"""样本级文字过滤策略（§7 精筛）：按任务决定是否拒绝样本。"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

from .models import TextBox, TextRole


class SampleTextPolicy(BaseModel):
    """合成配对样本的文字过滤策略。

    默认规则：字幕目标区域（合成字幕的 effect bbox，外扩 margin）内出现
    原生字幕文字就拒绝样本；inpainting 任务要求目标区域内不能有原生文字。
    """

    enabled: bool = True
    reject_roles: list[TextRole] = Field(default_factory=lambda: [TextRole.SUBTITLE])
    target_region_margin: float = Field(ge=0.0, le=0.1, default=0.01)


class SampleTextDecision(BaseModel):
    ok: bool
    reasons: list[str]


def check_frame_text_policy(
    boxes: Sequence[TextBox],
    target_bbox_normalized: tuple[float, float, float, float],
    policy: SampleTextPolicy,
) -> SampleTextDecision:
    """检查检测到的文字框是否与字幕目标区域冲突。"""
    if not policy.enabled:
        return SampleTextDecision(ok=True, reasons=[])
    x0, y0, x1, y1 = target_bbox_normalized
    margin = policy.target_region_margin
    target = (
        max(0.0, x0 - margin),
        max(0.0, y0 - margin),
        min(1.0, x1 + margin),
        min(1.0, y1 + margin),
    )
    reasons = [
        f"{box.role.value} 文字框 {box.xyxy} 与字幕目标区域重叠"
        for box in boxes
        if box.role in policy.reject_roles and _intersects(box.normalized, target)
    ]
    return SampleTextDecision(ok=not reasons, reasons=reasons)


def _intersects(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])
