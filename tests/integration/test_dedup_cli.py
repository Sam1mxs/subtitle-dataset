"""去重与划分 CLI 端到端。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from subtitle_dataset.cli import main

REPO_ROOT = Path(__file__).resolve().parents[2]
SPLIT_CONFIG = REPO_ROOT / "configs" / "splits" / "default.json"


def _ingest_manifest(video_sha256: str, frame_hashes: list[str]) -> dict[str, Any]:
    return {
        "video_sha256": video_sha256,
        "frames": [
            {"uri": f"frames/{index:05d}.png", "image_sha256": image_hash}
            for index, image_hash in enumerate(frame_hashes)
        ],
    }


def test_dedup_and_split_cli(tmp_path: Path) -> None:
    first = tmp_path / "a.json"
    first.write_text(
        json.dumps(_ingest_manifest("a" * 64, ["11" * 32, "11" * 32, "22" * 32])),
        encoding="utf-8",
    )
    second = tmp_path / "b.json"
    second.write_text(
        json.dumps(_ingest_manifest("b" * 64, ["11" * 32, "33" * 32])),
        encoding="utf-8",
    )
    dedup_out = tmp_path / "dedup"
    assert (
        main(
            [
                "dedup",
                "--manifests",
                str(first),
                "--manifests",
                str(second),
                "--outdir",
                str(dedup_out),
            ]
        )
        == 0
    )
    clusters = json.loads((dedup_out / "clusters.json").read_text(encoding="utf-8"))
    # 视频级 2 簇 + 帧级 3 个唯一哈希簇
    assert len(clusters) == 5
    duplicate = next(
        cluster for cluster in clusters if cluster["cluster_id"].startswith("exact-1111")
    )
    assert len(duplicate["items"]) == 3

    split_out = tmp_path / "splits"
    assert (
        main(
            [
                "split",
                "--clusters",
                str(dedup_out / "clusters.json"),
                "--config",
                str(SPLIT_CONFIG),
                "--outdir",
                str(split_out),
            ]
        )
        == 0
    )
    assignment = json.loads((split_out / "assignment.json").read_text(encoding="utf-8"))
    assert sum(assignment["cluster_counts"].values()) == 5
    assert sum(assignment["item_counts"].values()) == 7
    assert assignment["seed"] == 42

    # 确定性：重复运行输出一致
    second_out = tmp_path / "splits2"
    main(
        [
            "split",
            "--clusters",
            str(dedup_out / "clusters.json"),
            "--config",
            str(SPLIT_CONFIG),
            "--outdir",
            str(second_out),
        ]
    )
    assert (split_out / "assignment.json").read_bytes() == (
        second_out / "assignment.json"
    ).read_bytes()
