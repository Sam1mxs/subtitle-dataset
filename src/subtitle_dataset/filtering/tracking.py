"""跨帧时序跟踪与角色判定。"""

from __future__ import annotations

from collections import Counter

import numpy as np
from PIL import Image, ImageFilter

from .config import FilteringConfig
from .models import FrameDetection, PersistentBox, TextBox, TextRole


def track_boxes(
    detections: list[FrameDetection],
    frames: list[Image.Image],
    config: FilteringConfig,
) -> list[PersistentBox]:
    """按归一化 IoU 跨帧匹配文字框，输出持久、位置稳定的 track。"""
    tracks: list[list[tuple[int, TextBox]]] = []
    for frame_index, detection in enumerate(detections):
        matched = [False] * len(detection.boxes)
        for track in tracks:
            last_index, last_box = track[-1]
            if last_index == frame_index:
                continue
            best_index, best_iou = -1, config.iou_threshold
            for i, box in enumerate(detection.boxes):
                if matched[i]:
                    continue
                iou = _iou(box.normalized, last_box.normalized)
                if iou >= best_iou:
                    best_iou, best_index = iou, i
            if best_index != -1:
                track.append((frame_index, detection.boxes[best_index]))
                matched[best_index] = True
        for i, box in enumerate(detection.boxes):
            if not matched[i]:
                tracks.append([(frame_index, box)])

    persistent = [_persistent_box(track, len(detections), frames, config) for track in tracks]
    return [box for box in persistent if box is not None]


def _persistent_box(
    track: list[tuple[int, TextBox]],
    total_frames: int,
    frames: list[Image.Image],
    config: FilteringConfig,
) -> PersistentBox | None:
    observed = sorted({index for index, _ in track})
    persistence = len(observed) / total_frames
    if persistence < config.persistence_ratio:
        return None

    normalized = np.asarray([box.normalized for _, box in track], dtype=float)
    centers = (normalized[:, [0, 1]] + normalized[:, [2, 3]]) / 2
    position_std = float(np.mean(np.std(centers, axis=0)))
    if position_std > config.position_std_tolerance:
        return None

    mean_normalized = (
        float(normalized[:, 0].mean()),
        float(normalized[:, 1].mean()),
        float(normalized[:, 2].mean()),
        float(normalized[:, 3].mean()),
    )
    width, height = frames[observed[0]].size
    mean_xyxy = (
        round(mean_normalized[0] * width),
        round(mean_normalized[1] * height),
        round(mean_normalized[2] * width),
        round(mean_normalized[3] * height),
    )
    role = _majority_role([box.role for _, box in track])
    content_switched = _content_switched(track, frames, config)
    if content_switched and role is not TextRole.SUBTITLE:
        role = TextRole.SUBTITLE
    elif not content_switched and role is TextRole.SUBTITLE:
        role = (
            TextRole.WATERMARK
            if _looks_like_watermark(mean_normalized, config)
            else TextRole.SCENE_TEXT
        )
    return PersistentBox(
        role=role,
        xyxy=mean_xyxy,
        normalized=mean_normalized,
        persistence=persistence,
        position_std=position_std,
        content_switched=content_switched,
        confidence=float(np.mean([box.confidence for _, box in track])),
        observed_frames=observed,
    )


def _content_switched(
    track: list[tuple[int, TextBox]],
    frames: list[Image.Image],
    config: FilteringConfig,
) -> bool:
    boxes_by_frame = {index: box for index, box in track}
    observed = sorted(boxes_by_frame)
    for a, b in zip(observed, observed[1:], strict=False):
        mask_a = _foreground_mask(frames[a], boxes_by_frame[a].xyxy, config)
        mask_b = _foreground_mask(frames[b], boxes_by_frame[b].xyxy, config)
        if _mask_iou(mask_a, mask_b) < config.content_switch_iou_threshold:
            return True
    return False


def _foreground_mask(
    frame: Image.Image,
    xyxy: tuple[int, int, int, int],
    config: FilteringConfig,
) -> np.ndarray:
    x0, y0, x1, y1 = xyxy
    crop = frame.crop((max(x0, 0), max(y0, 0), min(x1, frame.width), min(y1, frame.height)))
    if crop.width == 0 or crop.height == 0:
        return np.zeros((1, 1), dtype=bool)
    edges = crop.convert("L").filter(ImageFilter.FIND_EDGES)
    return np.asarray(edges, dtype=np.uint8) >= config.edge_threshold


def _mask_iou(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    height = max(mask_a.shape[0], mask_b.shape[0])
    width = max(mask_a.shape[1], mask_b.shape[1])
    a = np.pad(mask_a, ((0, height - mask_a.shape[0]), (0, width - mask_a.shape[1])))
    b = np.pad(mask_b, ((0, height - mask_b.shape[0]), (0, width - mask_b.shape[1])))
    intersection = float(np.logical_and(a, b).sum())
    union = float(np.logical_or(a, b).sum())
    return 1.0 if union == 0 else intersection / union


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return 0.0 if union <= 0 else inter / union


def _majority_role(roles: list[TextRole]) -> TextRole:
    return Counter(roles).most_common(1)[0][0]


def _looks_like_watermark(
    normalized: tuple[float, float, float, float],
    config: FilteringConfig,
) -> bool:
    x0, y0, x1, y1 = normalized
    center_x = (x0 + x1) / 2
    center_y = (y0 + y1) / 2
    area = (x1 - x0) * (y1 - y0)
    in_corner = (
        center_x <= config.watermark_corner_ratio or center_x >= 1 - config.watermark_corner_ratio
    ) and (
        center_y <= config.watermark_corner_ratio or center_y >= 1 - config.watermark_corner_ratio
    )
    return in_corner and area <= config.watermark_max_area_ratio
