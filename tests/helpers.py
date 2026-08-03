"""测试数据工厂。"""

from __future__ import annotations

from typing import Any

from subtitle_dataset.contracts import compute_sample_id

IMAGE_WIDTH = 1080
IMAGE_HEIGHT = 1920


def valid_sample_dict() -> dict[str, Any]:
    """构造一个满足全部契约约束的样本字典（与设计文档 §12 示例一致）。"""
    data: dict[str, Any] = {
        "source": {
            "platform": "bilibili",
            "video_sha256": "a" * 64,
            "creator_hash": "creator-001",
            "content_cluster_id": "cluster-001",
            "native_frame_index": 381,
            "pts": 38148,
            "timestamp_ms": 12716,
            "time_base": {"num": 1, "den": 3000},
            "frame_rate": {
                "avg_num": 30000,
                "avg_den": 1001,
                "r_num": 30000,
                "r_den": 1001,
                "is_vfr": False,
            },
        },
        "image": {
            "width": IMAGE_WIDTH,
            "height": IMAGE_HEIGHT,
            "clean_uri": "s3://bucket/derived/frames/video-001/381.clean.png",
            "rendered_uri": "s3://bucket/derived/frames/video-001/381.rendered.png",
        },
        "subtitle": {
            "event_id": "event-001",
            "text_raw": "今天晚上一起吃饭",
            "text_normalized": "今天晚上一起吃饭",
            "start_native_frame": 360,
            "end_native_frame_exclusive": 405,
            "start_pts": 36000,
            "end_pts_exclusive": 40500,
            "start_time_ms": 12000,
            "end_time_ms": 13500,
            "duration_ms": 1500,
            "native_duration_frames": 45,
            "bbox_xyxy": [181, 1370, 902, 1456],
            "bbox_normalized": [0.168, 0.714, 0.835, 0.758],
            "line_bboxes_xyxy": [[181, 1370, 902, 1456]],
            "polygon": [],
            "alpha_mask_uri": "s3://bucket/derived/frames/video-001/381.alpha.png",
            "inpaint_mask_uri": "s3://bucket/derived/frames/video-001/381.mask.png",
            "style": {
                "font_sha256": "b" * 64,
                "font_size_h_ratio": 0.041,
                "letter_spacing": 1.2,
                "line_spacing": 4.0,
                "stroke_width_h_ratio": 0.002,
                "opacity": 1.0,
                "style_seed": 42,
            },
        },
        "transform": {
            "crop_xywh": [0, 0, IMAGE_WIDTH, IMAGE_HEIGHT],
            "target_size": [IMAGE_WIDTH, IMAGE_HEIGHT],
        },
        "build": {
            "dataset_version": "v1",
            "config_sha256": "c" * 64,
            "renderer_version": "renderer-0.1.0",
            "ffmpeg_version": "6.1.1",
            "seed": 123456,
        },
        "split": "train",
    }
    data["sample_id"] = compute_sample_id(
        dataset_version=data["build"]["dataset_version"],
        video_sha256=data["source"]["video_sha256"],
        native_frame_index=data["source"]["native_frame_index"],
        pts=data["source"]["pts"],
        crop_xywh=tuple(data["transform"]["crop_xywh"]),
        event_id=data["subtitle"]["event_id"],
        style_seed=data["subtitle"]["style"]["style_seed"],
    )
    return data


def set_bbox(data: dict[str, Any], xyxy: list[int]) -> dict[str, Any]:
    """替换像素 bbox 并同步归一化坐标，保持两者一致。"""
    x0, y0, x1, y1 = xyxy
    data["subtitle"]["bbox_xyxy"] = xyxy
    data["subtitle"]["bbox_normalized"] = [
        round(x0 / IMAGE_WIDTH, 3),
        round(y0 / IMAGE_HEIGHT, 3),
        round(x1 / IMAGE_WIDTH, 3),
        round(y1 / IMAGE_HEIGHT, 3),
    ]
    return data
