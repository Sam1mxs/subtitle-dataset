"""命令行入口：样本/清单校验与字幕渲染。"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image

from .contracts import Sample, SampleManifest
from .rendering import PillowRenderer, RenderConfig


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("顶层必须是 JSON 对象")
    return data


def _cmd_validate_sample(args: argparse.Namespace) -> int:
    sample = Sample.model_validate(_load_json(args.path))
    print(f"OK: sample {sample.sample_id} ({sample.split.value})")
    return 0


def _cmd_validate_manifest(args: argparse.Namespace) -> int:
    manifest = SampleManifest.model_validate(_load_json(args.path))
    print(f"OK: {len(manifest.samples)} samples ({manifest.split.value})")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    clean = Image.open(args.clean).convert("RGB")
    config = RenderConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    result = PillowRenderer().render(clean, config)
    args.outdir.mkdir(parents=True, exist_ok=True)
    result.rendered.save(args.outdir / "rendered.png")
    result.alpha_mask.save(args.outdir / "alpha.png")
    result.inpaint_mask.save(args.outdir / "mask.png")
    metadata = {
        "image_size": [clean.width, clean.height],
        "effect_bbox_xyxy": result.effect_bbox_xyxy,
        "line_bboxes_xyxy": result.line_bboxes_xyxy,
        "config_sha256": result.config_sha256,
        "font_sha256": result.font_sha256,
    }
    (args.outdir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"OK: 渲染输出已写入 {args.outdir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="subtitle-dataset", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_sample = sub.add_parser("validate-sample", help="校验单个样本 JSON")
    p_sample.add_argument("path", type=Path)

    p_manifest = sub.add_parser("validate-manifest", help="校验样本清单 JSON")
    p_manifest.add_argument("path", type=Path)

    p_render = sub.add_parser("render", help="渲染一张合成字幕样本")
    p_render.add_argument("--clean", type=Path, required=True, help="clean image 路径")
    p_render.add_argument("--config", type=Path, required=True, help="RenderConfig JSON 路径")
    p_render.add_argument("--outdir", type=Path, required=True, help="输出目录")

    args = parser.parse_args(argv)
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {
        "validate-sample": _cmd_validate_sample,
        "validate-manifest": _cmd_validate_manifest,
        "render": _cmd_render,
    }
    handler = handlers[args.command]
    try:
        return handler(args)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
