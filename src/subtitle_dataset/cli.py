"""最小命令行入口：校验样本/清单 JSON。"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .contracts import Sample, SampleManifest


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("顶层必须是 JSON 对象")
    return data


def _cmd_validate_sample(path: Path) -> int:
    sample = Sample.model_validate(_load_json(path))
    print(f"OK: sample {sample.sample_id} ({sample.split.value})")
    return 0


def _cmd_validate_manifest(path: Path) -> int:
    manifest = SampleManifest.model_validate(_load_json(path))
    print(f"OK: {len(manifest.samples)} samples ({manifest.split.value})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="subtitle-dataset", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_sample = sub.add_parser("validate-sample", help="校验单个样本 JSON")
    p_sample.add_argument("path", type=Path)

    p_manifest = sub.add_parser("validate-manifest", help="校验样本清单 JSON")
    p_manifest.add_argument("path", type=Path)

    args = parser.parse_args(argv)
    handlers: dict[str, Callable[[Path], int]] = {
        "validate-sample": _cmd_validate_sample,
        "validate-manifest": _cmd_validate_manifest,
    }
    handler = handlers[args.command]
    try:
        return handler(args.path)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
