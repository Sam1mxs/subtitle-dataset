"""确定性序列化与哈希工具。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

_CANONICAL_JSON_OPTS: dict[str, Any] = {
    "sort_keys": True,
    "separators": (",", ":"),
    "ensure_ascii": False,
}


def canonical_dumps(obj: Any) -> str:
    """输出键排序、紧凑分隔的 canonical JSON。"""
    return json.dumps(obj, **_CANONICAL_JSON_OPTS)


def sha256_hex(payload: str) -> str:
    """对 UTF-8 编码的字符串计算 SHA-256 十六进制摘要。"""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def config_sha256(config: Mapping[str, Any]) -> str:
    """对配置字典计算可复现的 SHA-256。"""
    return sha256_hex(canonical_dumps(config))


def compute_sample_id(
    *,
    dataset_version: str,
    video_sha256: str,
    native_frame_index: int,
    pts: int,
    crop_xywh: tuple[int, int, int, int],
    event_id: str,
    style_seed: int,
) -> str:
    """按设计文档 §12 规则确定性生成 ``sample_id``。

    hash(dataset_version, video_sha256, native_frame_index, pts, crop_config,
    event_id, style_seed)；不含任何存储 URI 或绝对路径。
    """
    payload = canonical_dumps(
        {
            "dataset_version": dataset_version,
            "video_sha256": video_sha256,
            "native_frame_index": native_frame_index,
            "pts": pts,
            "crop_xywh": list(crop_xywh),
            "event_id": event_id,
            "style_seed": style_seed,
        }
    )
    return sha256_hex(payload)
