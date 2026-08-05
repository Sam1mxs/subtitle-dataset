"""单帧文字区域检测（启发式；预留 OCR 后端接口）。"""

from __future__ import annotations

from typing import Protocol

import numpy as np
from PIL import Image, ImageFilter

from .config import FilteringConfig
from .models import TextBox, TextRole


class TextRegionDetector(Protocol):
    """文字区域检测接口；未来 PaddleOCR 后端实现同一协议。"""

    def detect(self, image: Image.Image) -> list[TextBox]: ...


class HeuristicTextRegionDetector:
    """基于边缘密度与行/列投影的启发式检测器，不依赖 OCR 模型。"""

    def __init__(self, config: FilteringConfig) -> None:
        self._config = config

    def detect(self, image: Image.Image) -> list[TextBox]:
        gray = image.convert("L")
        edges = np.asarray(gray.filter(ImageFilter.FIND_EDGES), dtype=np.uint8)
        mask = (edges >= self._config.edge_threshold).astype(np.uint8)
        mask = self._morph_close(mask)
        return [
            TextBox(
                xyxy=box,
                normalized=_normalize_box(box, image.width, image.height),
                confidence=float(mask[box[1] : box[3], box[0] : box[2]].mean()),
            )
            for box in self._projection_boxes(mask)
        ]

    def _morph_close(self, mask: np.ndarray) -> np.ndarray:
        size = self._config.morph_close_size
        pil = Image.fromarray(mask * 255, mode="L")
        closed = pil.filter(ImageFilter.MaxFilter(size)).filter(ImageFilter.MinFilter(size))
        return (np.asarray(closed) > 0).astype(np.uint8)

    def _projection_boxes(self, mask: np.ndarray) -> list[tuple[int, int, int, int]]:
        height, width = mask.shape
        row_sums = mask.sum(axis=1)
        row_threshold = self._config.row_band_min_density * width
        rows = _contiguous_segments(
            row_sums >= row_threshold,
            min_len=self._config.min_box_height,
            merge_gap=self._config.merge_row_gap_px,
        )
        boxes: list[tuple[int, int, int, int]] = []
        for y0, y1 in rows:
            col_sums = mask[y0:y1].sum(axis=0)
            col_threshold = self._config.column_min_density * (y1 - y0)
            for x0, x1 in _contiguous_segments(
                col_sums >= col_threshold,
                min_len=self._config.min_box_width,
                merge_gap=self._config.merge_col_gap_px,
            ):
                boxes.append((x0, y0, x1, y1))
        return boxes


def assign_geometric_roles(
    boxes: list[TextBox],
    *,
    width: int,
    height: int,
    config: FilteringConfig,
) -> list[TextBox]:
    """几何角色初判：下方=字幕，角落小框=台标，其余=场景文字。"""
    for box in boxes:
        x0, y0, x1, y1 = box.xyxy
        center_x = (x0 + x1) / 2 / width
        center_y = (y0 + y1) / 2 / height
        area_ratio = (x1 - x0) * (y1 - y0) / (width * height)
        in_corner = (
            center_x <= config.watermark_corner_ratio
            or center_x >= 1 - config.watermark_corner_ratio
        ) and (
            center_y <= config.watermark_corner_ratio
            or center_y >= 1 - config.watermark_corner_ratio
        )
        if center_y >= config.subtitle_region_y0:
            box.role = TextRole.SUBTITLE
        elif in_corner and area_ratio <= config.watermark_max_area_ratio:
            box.role = TextRole.WATERMARK
        else:
            box.role = TextRole.SCENE_TEXT
    return boxes


def _normalize_box(
    box: tuple[int, int, int, int],
    width: int,
    height: int,
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = box
    return (x0 / width, y0 / height, x1 / width, y1 / height)


def _contiguous_segments(
    values: np.ndarray,
    *,
    min_len: int,
    merge_gap: int,
) -> list[tuple[int, int]]:
    """把布尔数组切成 [start, end) 段；间隔 <= merge_gap 的相邻段合并。"""
    segments: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(values):
        if value and start is None:
            start = index
        elif not value and start is not None:
            segments.append((start, index))
            start = None
    if start is not None:
        segments.append((start, len(values)))
    if not segments:
        return []
    merged: list[tuple[int, int]] = [segments[0]]
    for segment in segments[1:]:
        if segment[0] - merged[-1][1] <= merge_gap:
            merged[-1] = (merged[-1][0], segment[1])
        else:
            merged.append(segment)
    return [(s, e) for s, e in merged if e - s >= min_len]
