"""命令行入口：样本/清单校验与字幕渲染。"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image

from .contracts import Sample, SampleManifest, SourceInfo, Transform
from .filtering import FilteringConfig, VideoSubtitleFilter
from .media import IngestConfig, probe_video
from .qa.distribution import (
    DistributionReportConfig,
    build_frame_distribution,
    build_sample_distribution,
)
from .rendering import PillowRenderer, RenderConfig
from .sampling import SampleSampler, SamplingConfig
from .workflows import frame_sources_and_transforms, run_ingest


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
        "font_id": result.font_id,
        "font_sha256": result.font_sha256,
        "fallback_used": result.fallback_used,
        "missing_chars": result.missing_chars,
    }
    (args.outdir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"OK: 渲染输出已写入 {args.outdir}")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    config = SamplingConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    args.outdir.mkdir(parents=True, exist_ok=True)
    records = []
    frame_paths: list[Path] | None = None
    sources: list[SourceInfo] = []
    transforms: list[Transform] = []
    ffmpeg_version = ""
    if args.clean.is_dir():
        frame_paths = sorted(args.clean.glob("*.png"))
        if not frame_paths:
            print("ERROR: 帧目录中没有 PNG 文件", file=sys.stderr)
            return 2
        if args.frames_manifest is not None:
            manifest = _load_json(args.frames_manifest)
            all_sources, all_transforms = frame_sources_and_transforms(
                manifest,
                platform=config.source_platform,
            )
            by_name = {
                Path(record["uri"]).name: (src, transform)
                for record, src, transform in zip(
                    manifest["frames"],
                    all_sources,
                    all_transforms,
                    strict=True,
                )
            }
            for frame_path in frame_paths:
                pair = by_name.get(frame_path.name)
                if pair is None:
                    print(
                        f"ERROR: 帧 {frame_path.name} 不在 frames manifest 中",
                        file=sys.stderr,
                    )
                    return 2
                sources.append(pair[0])
                transforms.append(pair[1])
            ffmpeg_version = manifest.get("ffmpeg_version", "")
    elif args.frames_manifest is not None:
        print("ERROR: --frames-manifest 需要 --clean 为帧目录", file=sys.stderr)
        return 2
    sampler = SampleSampler(config, ffmpeg_version=ffmpeg_version)
    for index in range(args.n):
        if frame_paths is not None:
            clean = Image.open(frame_paths[index % len(frame_paths)]).convert("RGB")
        else:
            clean = Image.open(args.clean).convert("RGB")
        sample = sampler.sample(
            clean,
            index,
            source=sources[index % len(sources)] if sources else None,
            transform=transforms[index % len(transforms)] if transforms else None,
        )
        sample_dir = args.outdir / "samples" / f"{index:05d}"
        sample_dir.mkdir(parents=True, exist_ok=True)
        sample.rendered.save(sample_dir / "rendered.png")
        sample.alpha_mask.save(sample_dir / "alpha.png")
        sample.inpaint_mask.save(sample_dir / "mask.png")
        (sample_dir / "sample.json").write_text(
            sample.record.model_dump_json(indent=2),
            encoding="utf-8",
        )
        records.append(sample.record.model_dump(mode="json"))
    manifest = {
        "dataset_version": config.dataset_version,
        "seed": config.seed,
        "n": args.n,
        "samples": records,
    }
    (args.outdir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"OK: {args.n} 个样本已写入 {args.outdir}")
    return 0


def _cmd_probe(args: argparse.Namespace) -> int:
    probe = probe_video(args.video)
    print(probe.model_dump_json(indent=2))
    return 0


def _cmd_extract_frames(args: argparse.Namespace) -> int:
    config = IngestConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    report = run_ingest(args.video, config, args.outdir)
    print(
        f"OK: {len(report.scenes)} 个场景，{len(report.frames)} 帧，"
        f"{len(report.failures)} 个失败 → {args.outdir}"
    )
    return 0


def _cmd_detect_subtitles(args: argparse.Namespace) -> int:
    config = FilteringConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    report = VideoSubtitleFilter(config).analyze(args.video)
    print(json.dumps(json.loads(report.model_dump_json()), ensure_ascii=False, indent=2))
    return 0


def _cmd_distribution_report(args: argparse.Namespace) -> int:
    config = DistributionReportConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    if args.samples is None and args.frames is None:
        print("ERROR: --samples 或 --frames 至少提供一个", file=sys.stderr)
        return 2
    result: dict[str, Any] = {}
    if args.samples is not None:
        manifest = _load_json(args.samples)
        result["samples"] = build_sample_distribution(
            manifest["samples"],
            targets=config.duration_targets,
            tolerance=config.tolerance,
            min_samples=config.min_samples,
        ).model_dump(mode="json")
    if args.frames is not None:
        result["frames"] = build_frame_distribution(_load_json(args.frames)).model_dump(mode="json")
    print(json.dumps(result, ensure_ascii=False, indent=2))
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

    p_generate = sub.add_parser("generate", help="采样并渲染一批严格配对样本")
    p_generate.add_argument("--clean", type=Path, required=True, help="clean image 路径")
    p_generate.add_argument("--config", type=Path, required=True, help="SamplingConfig JSON 路径")
    p_generate.add_argument("--outdir", type=Path, required=True, help="输出目录")
    p_generate.add_argument("--n", type=int, default=5, help="生成样本数（默认 5）")
    p_generate.add_argument(
        "--frames-manifest",
        type=Path,
        default=None,
        help="extract-frames 的 manifest.json（把原生时间/来源写进样本）",
    )

    p_probe = sub.add_parser("probe", help="探测视频元数据（ffprobe JSON）")
    p_probe.add_argument("video", type=Path, help="视频文件路径")

    p_extract = sub.add_parser("extract-frames", help="视频 pilot：场景切分、抽帧与裁剪")
    p_extract.add_argument("--video", type=Path, required=True, help="视频文件路径")
    p_extract.add_argument("--config", type=Path, required=True, help="IngestConfig JSON 路径")
    p_extract.add_argument("--outdir", type=Path, required=True, help="输出目录")

    p_detect = sub.add_parser("detect-subtitles", help="检测视频是否带原生硬字幕（启发式）")
    p_detect.add_argument("--video", type=Path, required=True, help="视频文件路径")
    p_detect.add_argument("--config", type=Path, required=True, help="FilteringConfig JSON 路径")

    p_distribution = sub.add_parser("distribution-report", help="输出分布报告并与目标对比")
    p_distribution.add_argument(
        "--samples", type=Path, default=None, help="generate 输出的 manifest.json"
    )
    p_distribution.add_argument(
        "--frames", type=Path, default=None, help="extract-frames 输出的 manifest.json"
    )
    p_distribution.add_argument(
        "--config", type=Path, required=True, help="DistributionReportConfig JSON 路径"
    )

    args = parser.parse_args(argv)
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {
        "validate-sample": _cmd_validate_sample,
        "validate-manifest": _cmd_validate_manifest,
        "render": _cmd_render,
        "generate": _cmd_generate,
        "probe": _cmd_probe,
        "extract-frames": _cmd_extract_frames,
        "detect-subtitles": _cmd_detect_subtitles,
        "distribution-report": _cmd_distribution_report,
    }
    handler = handlers[args.command]
    try:
        return handler(args)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
