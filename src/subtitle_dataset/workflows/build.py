"""构建编排：ingest → generate → export，带幂等/恢复/重建。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field

from subtitle_dataset.contracts import SourceInfo, Split, Transform, config_sha256
from subtitle_dataset.ingest import (
    DEFAULT_REGISTRY_PATH,
    SourceRegistry,
    check_authorization,
)
from subtitle_dataset.media.config import IngestConfig
from subtitle_dataset.media.probe import sha256_file
from subtitle_dataset.sampling import SampleSampler, SamplingConfig, SamplingExhaustedError

from .ingest import frame_sources_and_transforms, run_ingest
from .runner import (
    REPO_ROOT,
    RunState,
    StageContext,
    WorkflowRunner,
    code_version,
    compute_run_id,
    dependency_versions,
    load_run,
    save_run,
)


class WorkflowConfig(BaseModel):
    """一次数据构建的输入：视频 + 各阶段配置路径。"""

    dataset_version: str = "v1"
    seed: int = 0
    video_path: str
    n_events: int = Field(ge=1, default=5)
    source_id: str | None = None
    registry: str | None = None
    ingest_config_path: str
    sampling_config_path: str
    export_parquet: bool = True


def generate_samples(
    *,
    clean_dir: Path | None,
    clean_image: Path | None,
    frames_manifest_path: Path | None,
    sampling_config: SamplingConfig,
    outdir: Path,
    n_events: int,
    split_map_path: Path | None = None,
    source_id: str | None = None,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    """采样-渲染-校验闭环（事件驱动），返回 generate manifest。"""
    creator_hash: str | None = None
    if source_id is not None:
        registry = SourceRegistry.load(registry_path or DEFAULT_REGISTRY_PATH)
        source = registry.get(source_id)
        authorization = check_authorization(source, date.today())
        if not authorization.authorized:
            raise ValueError(f"来源 {source_id} 未通过授权检查：{'；'.join(authorization.reasons)}")
        sampling_config.source_platform = source.platform
        creator_hash = source.creator_id_or_hash
    outdir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    frame_paths: list[Path] | None = None
    sources: list[SourceInfo] = []
    transforms: list[Transform] = []
    frame_splits: list[Split] | None = None
    ffmpeg_version = ""
    splits_by_item: dict[str, Split] | None = None
    if split_map_path is not None:
        raw_splits = json.loads(split_map_path.read_text(encoding="utf-8"))
        splits_by_item = {item_id: Split(value) for item_id, value in raw_splits.items()}
    if clean_dir is not None:
        frame_paths = sorted(clean_dir.glob("*.png"))
        if not frame_paths:
            raise ValueError(f"帧目录中没有 PNG 文件: {clean_dir}")
        if frames_manifest_path is not None:
            manifest = json.loads(frames_manifest_path.read_text(encoding="utf-8"))
            video_sha256 = manifest["video_sha256"]
            all_sources, all_transforms = frame_sources_and_transforms(
                manifest,
                platform=sampling_config.source_platform,
                creator_hash=creator_hash,
            )
            by_name = {
                Path(record["uri"]).name: (record, src, transform)
                for record, src, transform in zip(
                    manifest["frames"],
                    all_sources,
                    all_transforms,
                    strict=True,
                )
            }
            if splits_by_item is not None:
                frame_splits = []
            for frame_path in frame_paths:
                entry = by_name.get(frame_path.name)
                if entry is None:
                    raise ValueError(f"帧 {frame_path.name} 不在 frames manifest 中")
                record, src, transform = entry
                sources.append(src)
                transforms.append(transform)
                if frame_splits is not None and splits_by_item is not None:
                    item_id = f"frame:{video_sha256}:{record['uri']}"
                    split_value = splits_by_item.get(item_id)
                    if split_value is None:
                        raise ValueError(f"条目 {item_id} 不在 split map 中")
                    frame_splits.append(split_value)
            ffmpeg_version = manifest.get("ffmpeg_version", "")
    elif frames_manifest_path is not None:
        raise ValueError("--frames-manifest 需要 clean 为帧目录")

    sampler = SampleSampler(sampling_config, ffmpeg_version=ffmpeg_version)
    total_samples = 0
    events_by_id: dict[str, Any] = {}
    for index in range(n_events):
        if frame_paths is not None:
            clean = Image.open(frame_paths[index % len(frame_paths)]).convert("RGB")
        elif clean_image is not None:
            clean = Image.open(clean_image).convert("RGB")
        else:
            raise ValueError("需要 --clean 或帧目录")
        try:
            samples = sampler.sample_event(
                clean,
                index,
                source=sources[index % len(sources)] if sources else None,
                transform=transforms[index % len(transforms)] if transforms else None,
                split=(frame_splits[index % len(frame_splits)] if frame_splits else None),
            )
        except SamplingExhaustedError as exc:
            raise RuntimeError(str(exc)) from exc
        for sample in samples:
            sample_dir = outdir / "samples" / f"{total_samples:05d}"
            sample_dir.mkdir(parents=True, exist_ok=True)
            sample.rendered.save(sample_dir / "rendered.png")
            sample.alpha_mask.save(sample_dir / "alpha.png")
            sample.inpaint_mask.save(sample_dir / "mask.png")
            (sample_dir / "sample.json").write_text(
                sample.record.model_dump_json(indent=2),
                encoding="utf-8",
            )
            records.append(sample.record.model_dump(mode="json"))
            total_samples += 1
        if samples and samples[0].record.event is not None:
            event = samples[0].record.event
            events_by_id[event.event_id] = event.model_dump(mode="json")
    manifest = {
        "dataset_version": sampling_config.dataset_version,
        "seed": sampling_config.seed,
        "n": total_samples,
        "events": list(events_by_id.values()),
        "samples": records,
    }
    (outdir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def run_build(config: WorkflowConfig, outdir: Path, *, force: bool = False) -> RunState:
    """执行 ingest → generate → export 构建；幂等恢复、force 强制重建。"""
    ingest_config = IngestConfig.model_validate_json(
        (REPO_ROOT / config.ingest_config_path).read_text(encoding="utf-8")
    )
    sampling_config = SamplingConfig.model_validate_json(
        (REPO_ROOT / config.sampling_config_path).read_text(encoding="utf-8")
    )
    sampling_config.dataset_version = config.dataset_version
    sampling_config.seed = config.seed
    video = Path(config.video_path)
    if not video.exists():
        raise FileNotFoundError(video)
    video_sha256 = sha256_file(video)
    stage_hashes = {
        "ingest": config_sha256(ingest_config.model_dump(mode="json")),
        "generate": config_sha256(sampling_config.model_dump(mode="json")),
        "export": config_sha256({"export_parquet": config.export_parquet}),
    }
    registry_path = None
    if config.registry:
        raw_registry = Path(config.registry)
        registry_path = raw_registry if raw_registry.is_absolute() else REPO_ROOT / raw_registry
    run_id = compute_run_id(
        dataset_version=config.dataset_version,
        seed=config.seed,
        input_sha256=video_sha256,
        stage_config_hashes=stage_hashes,
        code_version=code_version(),
        n_events=config.n_events,
    )
    existing = load_run(outdir)
    state = (
        existing
        if existing is not None and existing.run_id == run_id
        else RunState(
            run_id=run_id,
            dataset_version=config.dataset_version,
            code_version=code_version(),
            dependency_versions=dependency_versions(),
            seed=config.seed,
            input_sha256=video_sha256,
            stage_config_hashes=stage_hashes,
        )
    )
    save_run(state, outdir)
    runner = WorkflowRunner(outdir, state)

    def stage_ingest(ctx: StageContext) -> None:
        frames_dir = ctx.outdir / "frames"
        report = run_ingest(video, ingest_config, frames_dir)
        ctx.outputs.extend(
            [
                frames_dir / "manifest.json",
                frames_dir / "probe.json",
                frames_dir / "failures.json",
            ]
        )
        if report.failures:
            raise RuntimeError(f"ingest 存在 {len(report.failures)} 个失败")

    def stage_generate(ctx: StageContext) -> None:
        frames_dir = ctx.outdir / "frames" / "frames"
        manifest_path = ctx.outdir / "frames" / "manifest.json"
        samples_dir = ctx.outdir / "samples"
        generate_samples(
            clean_dir=frames_dir,
            clean_image=None,
            frames_manifest_path=manifest_path,
            sampling_config=sampling_config,
            outdir=samples_dir,
            n_events=config.n_events,
            source_id=config.source_id,
            registry_path=registry_path,
        )
        ctx.outputs.append(samples_dir / "manifest.json")

    def stage_export(ctx: StageContext) -> None:
        from subtitle_dataset.export import (
            export_events_manifest,
            export_ingest_manifest,
            export_samples_manifest,
        )

        parquet_dir = ctx.outdir / "parquet"
        samples_data = json.loads(
            (ctx.outdir / "samples" / "manifest.json").read_text(encoding="utf-8")
        )
        export_samples_manifest(samples_data, parquet_dir)
        if "events" in samples_data:
            export_events_manifest(samples_data, parquet_dir)
        frames_data = json.loads(
            (ctx.outdir / "frames" / "manifest.json").read_text(encoding="utf-8")
        )
        export_ingest_manifest(frames_data, parquet_dir)
        ctx.outputs.append(parquet_dir / "samples.parquet")

    stages = [
        ("ingest", stage_ingest, stage_hashes["ingest"]),
        ("generate", stage_generate, stage_hashes["generate"]),
    ]
    if config.export_parquet:
        stages.append(("export", stage_export, stage_hashes["export"]))
    return runner.execute(stages, force=force)
