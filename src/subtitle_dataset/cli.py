"""命令行入口：样本/清单校验与字幕渲染。"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image

from .contracts import Sample, SampleManifest
from .dedup import (
    ContentCluster,
    SplitAllocator,
    SplitConfig,
    build_exact_clusters,
    items_from_ingest_manifest,
)
from .export import export_events_manifest, export_ingest_manifest, export_samples_manifest
from .filtering import FilteringConfig, VideoSubtitleFilter
from .ingest import (
    ADAPTERS,
    DEFAULT_REGISTRY_PATH,
    CollectConfig,
    DownloadManager,
    SourceRegistry,
    check_authorization,
)
from .media import IngestConfig, probe_video
from .qa.distribution import (
    DistributionReportConfig,
    build_frame_distribution,
    build_sample_distribution,
)
from .rendering import PillowRenderer, RenderConfig
from .sampling import SamplingConfig
from .workflows import run_ingest
from .workflows.build import WorkflowConfig, generate_samples, run_build
from .workflows.runner import load_run


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
    try:
        manifest = generate_samples(
            clean_dir=args.clean if args.clean.is_dir() else None,
            clean_image=args.clean if not args.clean.is_dir() else None,
            frames_manifest_path=args.frames_manifest,
            sampling_config=config,
            outdir=args.outdir,
            n_events=args.n,
            split_map_path=args.split_map,
            source_id=args.source_id,
            registry_path=args.registry,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"OK: {args.n} 个事件 / {manifest['n']} 个样本已写入 {args.outdir}")
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


def _cmd_source_registry_validate(args: argparse.Namespace) -> int:
    registry = SourceRegistry.load(args.path)
    errors = registry.validate_registry()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(f"OK: {len(registry.sources)} 个来源登记有效")
    return 0


def _cmd_source_registry_check(args: argparse.Namespace) -> int:
    try:
        source = SourceRegistry.load(args.path).get(args.source_id)
    except KeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    result = check_authorization(source, args.at)
    print(result.model_dump_json(indent=2))
    return 0 if result.authorized else 1


def _cmd_collect(args: argparse.Namespace) -> int:
    config = (
        CollectConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
        if args.config is not None
        else CollectConfig()
    )
    if args.limit is not None:
        config.max_items = args.limit
    if args.concurrency is not None:
        config.max_workers = args.concurrency
    adapter_name = args.adapter or config.adapter
    adapter_cls = ADAPTERS.get(adapter_name)
    if adapter_cls is None:
        print(f"ERROR: 未知适配器 {adapter_name}", file=sys.stderr)
        return 2
    options = dict(config.adapter_options)
    if args.base_url is not None:
        options["base_url"] = args.base_url
    adapter = adapter_cls(**options)
    manager = DownloadManager(
        registry=SourceRegistry.load(args.registry or DEFAULT_REGISTRY_PATH),
        config=config,
        outdir=args.outdir,
    )
    reports = manager.collect_many(args.source_id, lambda _source_id: adapter)
    for report in reports:
        print(
            f"来源 {report.source_id}：发现 {report.discovered}，下载 {report.downloaded}，"
            f"跳过重复 {report.skipped_duplicates}，失败 {len(report.failures)}"
        )
    return 0 if all(r.authorized and not r.failures for r in reports) else 1


def _cmd_collect_delete(args: argparse.Namespace) -> int:
    manager = DownloadManager(
        registry=SourceRegistry.load(args.registry or DEFAULT_REGISTRY_PATH),
        config=CollectConfig(),
        outdir=args.outdir,
    )
    deleted = manager.delete_item(args.source_id, args.item_id)
    print(f"OK: 已删除 {args.source_id}/{args.item_id}" if deleted else "条目不存在")
    return 0 if deleted else 1


def _cmd_dedup(args: argparse.Namespace) -> int:
    items = []
    for manifest_path in args.manifests:
        items.extend(items_from_ingest_manifest(_load_json(manifest_path)))
    clusters = build_exact_clusters(items)
    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / "clusters.json").write_text(
        json.dumps(
            [cluster.model_dump(mode="json") for cluster in clusters],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    unique_items = len({item.id for cluster in clusters for item in cluster.items})
    duplicate_count = len(items) - unique_items
    print(
        f"OK: {len(items)} 个条目 → {len(clusters)} 个精确去重簇，"
        f"重复条目 {duplicate_count} → {args.outdir / 'clusters.json'}"
    )
    return 0


def _cmd_split(args: argparse.Namespace) -> int:
    with args.clusters.open("r", encoding="utf-8") as fh:
        raw_clusters = json.load(fh)
    clusters = [ContentCluster.model_validate(cluster) for cluster in raw_clusters]
    config = SplitConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    assignment = SplitAllocator(config).allocate(clusters)
    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / "assignment.json").write_text(
        assignment.model_dump_json(indent=2),
        encoding="utf-8",
    )
    item_splits = {
        item.id: assignment.assignments[cluster.cluster_id].value
        for cluster in clusters
        for item in cluster.items
    }
    (args.outdir / "item_splits.json").write_text(
        json.dumps(item_splits, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for warning in assignment.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    print(
        "OK: 簇数 "
        + ", ".join(f"{split}={count}" for split, count in assignment.cluster_counts.items())
        + "；条目数 "
        + ", ".join(f"{split}={count}" for split, count in assignment.item_counts.items())
    )
    return 0


def _cmd_export_parquet(args: argparse.Namespace) -> int:
    if args.samples is None and args.frames is None:
        print("ERROR: --samples 或 --frames 至少提供一个", file=sys.stderr)
        return 2
    args.outdir.mkdir(parents=True, exist_ok=True)
    if args.samples is not None:
        data = _load_json(args.samples)
        path = export_samples_manifest(data, args.outdir)
        print(f"OK: {path}")
        if "events" in data:
            events_path = export_events_manifest(data, args.outdir)
            print(f"OK: {events_path}")
    if args.frames is not None:
        for path in export_ingest_manifest(_load_json(args.frames), args.outdir):
            print(f"OK: {path}")
    return 0


def _cmd_workflow_run(args: argparse.Namespace) -> int:
    config = WorkflowConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    try:
        state = run_build(config, args.outdir, force=args.force)
    except Exception as exc:  # noqa: BLE001 - 工作流失败统一报错
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    summary = ", ".join(f"{name}={stage.status.value}" for name, stage in state.stages.items())
    print(f"OK: run {state.run_id[:12]} 状态 {state.status.value}；阶段 {summary}")
    return 0


def _cmd_workflow_status(args: argparse.Namespace) -> int:
    state = load_run(args.outdir)
    if state is None:
        print("ERROR: 没有运行记录（outdir 中无 workflow.json）", file=sys.stderr)
        return 2
    print(state.model_dump_json(indent=2))
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
    p_generate.add_argument(
        "--split-map",
        type=Path,
        default=None,
        help="split 输出的 item_splits.json（写入样本 split 字段）",
    )
    p_generate.add_argument("--source-id", default=None, help="来源登记表中的 source_id")
    p_generate.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="来源登记表路径（默认 configs/sources/registry.json）",
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

    p_source = sub.add_parser("source-registry", help="来源登记表：校验与授权检查")
    p_source_sub = p_source.add_subparsers(dest="src_command", required=True)
    p_src_validate = p_source_sub.add_parser("validate", help="校验登记表")
    p_src_validate.add_argument("--path", type=Path, default=DEFAULT_REGISTRY_PATH)
    p_src_check = p_source_sub.add_parser("check", help="检查来源授权")
    p_src_check.add_argument("--path", type=Path, default=DEFAULT_REGISTRY_PATH)
    p_src_check.add_argument("--source-id", required=True)
    p_src_check.add_argument("--at", type=date.fromisoformat, default=date.today())

    p_collect = sub.add_parser("collect", help="按来源下载视频（授权门禁 + 限速 + 幂等）")
    p_collect.add_argument("--source-id", action="append", required=True, help="可重复指定多个来源")
    p_collect.add_argument("--adapter", default=None, help="适配器名（默认 local-http）")
    p_collect.add_argument("--base-url", default=None, help="适配器参数（local-http 的 base URL）")
    p_collect.add_argument("--outdir", type=Path, required=True)
    p_collect.add_argument("--registry", type=Path, default=None)
    p_collect.add_argument("--config", type=Path, default=None, help="CollectConfig JSON 路径")
    p_collect.add_argument("--limit", type=int, default=None, help="本次最多下载条数")
    p_collect.add_argument("--concurrency", type=int, default=None, help="并发来源数")

    p_delete = sub.add_parser("collect-delete", help="删除已下载条目及其状态")
    p_delete.add_argument("--source-id", required=True)
    p_delete.add_argument("--item-id", required=True)
    p_delete.add_argument("--outdir", type=Path, required=True)
    p_delete.add_argument("--registry", type=Path, default=None)

    p_dedup = sub.add_parser("dedup", help="对 ingest manifest 做 SHA-256 精确去重")
    p_dedup.add_argument(
        "--manifests", action="append", type=Path, required=True, help="可重复指定"
    )
    p_dedup.add_argument("--outdir", type=Path, required=True)

    p_split = sub.add_parser("split", help="簇级 train/val/test 划分（簇不可拆分）")
    p_split.add_argument("--clusters", type=Path, required=True, help="dedup 输出的 clusters.json")
    p_split.add_argument("--config", type=Path, required=True, help="SplitConfig JSON 路径")
    p_split.add_argument("--outdir", type=Path, required=True)

    p_export = sub.add_parser("export-parquet", help="把 JSON manifest 导出为 Parquet")
    p_export.add_argument("--samples", type=Path, default=None, help="generate 的 manifest.json")
    p_export.add_argument(
        "--frames", type=Path, default=None, help="extract-frames 的 manifest.json"
    )
    p_export.add_argument("--outdir", type=Path, required=True)

    p_workflow = sub.add_parser("workflow", help="工作流：幂等重跑/失败恢复/强制重建")
    p_wf_sub = p_workflow.add_subparsers(dest="wf_command", required=True)
    p_wf_run = p_wf_sub.add_parser("run", help="运行或恢复构建")
    p_wf_run.add_argument("--config", type=Path, required=True, help="WorkflowConfig JSON 路径")
    p_wf_run.add_argument("--outdir", type=Path, required=True)
    p_wf_run.add_argument("--force", action="store_true", help="强制重建全部阶段")
    p_wf_status = p_wf_sub.add_parser("status", help="查看运行状态")
    p_wf_status.add_argument("--outdir", type=Path, required=True)

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
        "collect": _cmd_collect,
        "collect-delete": _cmd_collect_delete,
        "dedup": _cmd_dedup,
        "split": _cmd_split,
        "export-parquet": _cmd_export_parquet,
    }
    if args.command == "source-registry":
        source_handlers: dict[str, Callable[[argparse.Namespace], int]] = {
            "validate": _cmd_source_registry_validate,
            "check": _cmd_source_registry_check,
        }
        handler = source_handlers[args.src_command]
    elif args.command == "workflow":
        workflow_handlers: dict[str, Callable[[argparse.Namespace], int]] = {
            "run": _cmd_workflow_run,
            "status": _cmd_workflow_status,
        }
        handler = workflow_handlers[args.wf_command]
    else:
        handler = handlers[args.command]
    try:
        return handler(args)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
