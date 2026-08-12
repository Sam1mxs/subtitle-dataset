"""样本级文字过滤策略。"""

from __future__ import annotations

from subtitle_dataset.filtering import (
    SampleTextPolicy,
    TextBox,
    TextRole,
    check_frame_text_policy,
)


def _box(x0: float, y0: float, x1: float, y1: float, role: TextRole) -> TextBox:
    return TextBox(
        xyxy=(0, 0, 1, 1),
        normalized=(x0, y0, x1, y1),
        confidence=0.5,
        role=role,
    )


def test_overlapping_subtitle_rejected() -> None:
    boxes = [_box(0.3, 0.8, 0.7, 0.92, TextRole.SUBTITLE)]
    decision = check_frame_text_policy(boxes, (0.35, 0.82, 0.65, 0.9), SampleTextPolicy())
    assert not decision.ok
    assert decision.reasons


def test_non_overlapping_scene_text_allowed() -> None:
    boxes = [_box(0.3, 0.3, 0.7, 0.4, TextRole.SCENE_TEXT)]
    decision = check_frame_text_policy(boxes, (0.35, 0.82, 0.65, 0.9), SampleTextPolicy())
    assert decision.ok
    assert decision.reasons == []


def test_scene_text_rejected_when_configured() -> None:
    policy = SampleTextPolicy(reject_roles=[TextRole.SUBTITLE, TextRole.SCENE_TEXT])
    boxes = [_box(0.3, 0.84, 0.7, 0.92, TextRole.SCENE_TEXT)]
    decision = check_frame_text_policy(boxes, (0.35, 0.82, 0.65, 0.9), policy)
    assert not decision.ok


def test_margin_expands_target_region() -> None:
    boxes = [_box(0.3, 0.905, 0.7, 0.95, TextRole.SUBTITLE)]
    decision = check_frame_text_policy(boxes, (0.35, 0.82, 0.65, 0.9), SampleTextPolicy())
    assert not decision.ok


def test_disabled_policy_always_ok() -> None:
    policy = SampleTextPolicy(enabled=False)
    boxes = [_box(0.3, 0.8, 0.7, 0.92, TextRole.SUBTITLE)]
    decision = check_frame_text_policy(boxes, (0.35, 0.82, 0.65, 0.9), policy)
    assert decision.ok
