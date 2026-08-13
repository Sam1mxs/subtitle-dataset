"""采样-渲染-校验-重试闭环（事件驱动）。"""

from __future__ import annotations

import random
from dataclasses import dataclass

from PIL import Image
from pydantic import BaseModel, Field

from subtitle_dataset.contracts import BuildInfo, SourceInfo, Split, TimeBase, Transform
from subtitle_dataset.filtering import (
    FilteringConfig,
    HeuristicTextRegionDetector,
    TextRegionDetector,
    assign_geometric_roles,
)
from subtitle_dataset.filtering.policy import check_frame_text_policy
from subtitle_dataset.normalization import TextNormalizer, detect_script
from subtitle_dataset.qa import check_strict_pairing
from subtitle_dataset.rendering import PillowRenderer
from subtitle_dataset.rendering.config import RenderConfig, RenderStyle
from subtitle_dataset.rendering.renderer import RENDERER_VERSION, RenderResult

from .config import REPO_ROOT, SamplingConfig
from .durations import DurationSampler
from .events import SubtitleEventSpec, compute_event_id, ms_to_pts
from .positions import PositionSampler
from .styles import StyleSampler
from .texts import TextCorpus, TextSampler


class SamplingExhaustedError(RuntimeError):
    """重试次数耗尽仍无法生成合法样本。"""


class GeneratedSampleRecord(BaseModel):
    """一个生成样本的元数据（不含图像字节）。"""

    sample_index: int
    sample_seed: int
    duration_ms: int
    text: str
    style: RenderStyle
    center: tuple[float, float]
    inpaint_dilation_px: int
    effect_bbox_xyxy: tuple[int, int, int, int]
    line_bboxes_xyxy: list[tuple[int, int, int, int]]
    config_sha256: str
    font_id: str
    font_sha256: str
    fallback_used: bool
    missing_chars: dict[str, list[str]]
    pairing_ok: bool
    max_abs_diff_outside_mask: int
    source: SourceInfo | None = None
    transform: Transform | None = None
    build: BuildInfo | None = None
    text_normalized: str = ""
    normalization_version: str | None = None
    language: str | None = None
    script: str | None = None
    text_policy_ok: bool | None = None
    text_policy_reasons: list[str] = Field(default_factory=list)
    split: Split | None = None
    event: SubtitleEventSpec | None = None
    event_frame_index: int = 0
    event_frames_total: int = 1


@dataclass(frozen=True)
class GeneratedSample:
    record: GeneratedSampleRecord
    rendered: Image.Image
    alpha_mask: Image.Image
    inpaint_mask: Image.Image


class SampleSampler:
    """闭环入口：clean image + SamplingConfig → 事件 → 每个事件 K 个代表帧样本。

    每个事件使用独立种子（``config.seed + index * 7919``）；事件内字幕
    文本与样式不变，K 个代表帧共享渲染结果，仅事件帧索引/时间不同。
    """

    def __init__(
        self,
        config: SamplingConfig,
        *,
        renderer: PillowRenderer | None = None,
        ffmpeg_version: str = "",
        detector: TextRegionDetector | None = None,
    ) -> None:
        self._config = config
        self._renderer = renderer or PillowRenderer()
        self._ffmpeg_version = ffmpeg_version
        self._filtering_config = FilteringConfig()
        self._detector = detector or HeuristicTextRegionDetector(self._filtering_config)
        self._normalizer = TextNormalizer(
            language=config.text_language,
            version=config.text_normalization_version,
        )
        corpus_path = REPO_ROOT / config.corpus_path
        self._corpus = TextCorpus.load(corpus_path)

    def sample(
        self,
        clean: Image.Image,
        index: int,
        *,
        source: SourceInfo | None = None,
        transform: Transform | None = None,
        split: Split | None = None,
    ) -> GeneratedSample:
        """兼容入口：返回事件的第一（也是默认唯一的）代表帧样本。"""
        return self.sample_event(
            clean,
            index,
            source=source,
            transform=transform,
            split=split,
        )[0]

    def sample_event(
        self,
        clean: Image.Image,
        index: int,
        *,
        source: SourceInfo | None = None,
        transform: Transform | None = None,
        split: Split | None = None,
    ) -> list[GeneratedSample]:
        if transform is not None and tuple(transform.target_size) != clean.size:
            raise ValueError(
                f"transform.target_size {transform.target_size} 与 clean 尺寸 {clean.size} 不一致"
            )
        sample_seed = self._config.seed + index * 7919
        rng = random.Random(sample_seed)
        duration_ms = DurationSampler(self._config.durations, rng).sample()
        text_lines = TextSampler(self._corpus, self._config.single_line_prob, rng).sample()
        raw_text = "\n".join(text_lines)
        normalized = self._normalizer.normalize(raw_text)
        script = detect_script(raw_text)
        style_sampler = StyleSampler(self._config.style, rng)
        position_sampler = PositionSampler(self._config.position, rng)
        frames_per_event = self._config.frames_per_event

        for _ in range(self._config.max_attempts):
            style = style_sampler.sample()
            style.language = self._config.text_language
            center = position_sampler.sample()
            timing = self._event_timing(duration_ms, source)
            event = SubtitleEventSpec(
                event_id=compute_event_id(
                    seed=sample_seed,
                    text_raw=raw_text,
                    style_seed=sample_seed,
                    start_time_ms=timing["start_time_ms"],
                ),
                text_raw=raw_text,
                text_normalized=normalized.normalized,
                normalization_version=normalized.version,
                style=style,
                start_native_frame=timing["start_frame"],
                end_native_frame_exclusive=timing["end_frame"],
                native_duration_frames=timing["duration_frames"],
                start_pts=timing["start_pts"],
                end_pts_exclusive=timing["end_pts"],
                start_time_ms=timing["start_time_ms"],
                end_time_ms=timing["end_time_ms"],
                duration_ms=duration_ms,
                frames_per_event=frames_per_event,
            )
            render_config = RenderConfig(
                text=raw_text,
                style=style,
                center=center,
                inpaint_dilation_px=self._config.inpaint_dilation_px,
                require_ml_training_fonts=self._config.require_ml_training_fonts,
            )
            attempt = self._render_attempt(clean, render_config, index)
            if attempt is None:
                continue
            result, text_policy_ok, text_policy_reasons = attempt
            return [
                GeneratedSample(
                    record=GeneratedSampleRecord(
                        sample_index=index,
                        sample_seed=sample_seed,
                        duration_ms=duration_ms,
                        text=render_config.text,
                        style=style,
                        center=center,
                        inpaint_dilation_px=self._config.inpaint_dilation_px,
                        effect_bbox_xyxy=result.effect_bbox_xyxy,
                        line_bboxes_xyxy=result.line_bboxes_xyxy,
                        config_sha256=result.config_sha256,
                        font_id=result.font_id,
                        font_sha256=result.font_sha256,
                        fallback_used=result.fallback_used,
                        missing_chars=result.missing_chars,
                        pairing_ok=True,
                        max_abs_diff_outside_mask=0,
                        source=source,
                        transform=transform,
                        text_normalized=normalized.normalized,
                        normalization_version=normalized.version,
                        language=self._config.text_language,
                        script=script,
                        build=BuildInfo(
                            dataset_version=self._config.dataset_version,
                            config_sha256=result.config_sha256,
                            renderer_version=RENDERER_VERSION,
                            ffmpeg_version=self._ffmpeg_version,
                            seed=sample_seed,
                        ),
                        text_policy_ok=text_policy_ok,
                        text_policy_reasons=text_policy_reasons,
                        split=split,
                        event=event,
                        event_frame_index=frame_index,
                        event_frames_total=frames_per_event,
                    ),
                    rendered=result.rendered,
                    alpha_mask=result.alpha_mask,
                    inpaint_mask=result.inpaint_mask,
                )
                for frame_index in range(frames_per_event)
            ]

        raise SamplingExhaustedError(
            f"事件 {index} 在 {self._config.max_attempts} 次尝试内未生成合法布局"
        )

    def _render_attempt(
        self,
        clean: Image.Image,
        render_config: RenderConfig,
        index: int,
    ) -> tuple[RenderResult, bool | None, list[str]] | None:
        """渲染 + 严格配对 + 文字策略 + 中心带校验；失败返回 None。"""
        try:
            result = self._renderer.render(clean, render_config)
        except ValueError:
            return None
        check = check_strict_pairing(
            clean,
            result.rendered,
            result.inpaint_mask,
            effect_bbox=result.effect_bbox_xyxy,
        )
        if not check.ok:
            raise RuntimeError(
                f"样本 {index} 严格配对校验失败: max_abs_diff={check.max_abs_diff_outside_mask}"
            )
        if self._config.text_policy.enabled:
            boxes = self._detector.detect(clean)
            boxes = assign_geometric_roles(
                boxes,
                width=clean.width,
                height=clean.height,
                config=self._filtering_config,
            )
            target = _normalize_bbox(result.effect_bbox_xyxy, clean.size)
            decision = check_frame_text_policy(boxes, target, self._config.text_policy)
            if not decision.ok:
                return None
            text_policy_ok = True
            text_policy_reasons: list[str] = []
        else:
            text_policy_ok = None
            text_policy_reasons = []
        _, y0, _, y1 = result.effect_bbox_xyxy
        center_y = (y0 + y1) / 2 / clean.height
        if not 0.60 <= center_y <= 0.90:
            return None
        return result, text_policy_ok, text_policy_reasons

    def _event_timing(self, duration_ms: int, source: SourceInfo | None) -> dict[str, int]:
        """事件时间：有 source 时围绕该帧时间，否则用合成时间轴（1/1000 从 0 开始）。"""
        if source is not None:
            time_base = source.time_base
            frame_time_ms = source.timestamp_ms
            start_time_ms = max(0, frame_time_ms - duration_ms // 2)
            fps = (
                source.frame_rate.avg_num / source.frame_rate.avg_den
                if source.frame_rate.avg_num > 0
                else 30.0
            )
            base_frame = source.native_frame_index
        else:
            time_base = TimeBase(num=1, den=1000)
            start_time_ms = 0
            fps = 30.0
            base_frame = 0
        end_time_ms = start_time_ms + duration_ms
        duration_frames = max(round(duration_ms / 1000 * fps), 1)
        start_frame = max(0, base_frame - duration_frames // 2)
        return {
            "start_time_ms": start_time_ms,
            "end_time_ms": end_time_ms,
            "start_pts": ms_to_pts(start_time_ms, time_base),
            "end_pts": ms_to_pts(end_time_ms, time_base),
            "start_frame": start_frame,
            "end_frame": start_frame + duration_frames,
            "duration_frames": duration_frames,
        }


def _normalize_bbox(
    xyxy: tuple[int, int, int, int],
    size: tuple[int, int],
) -> tuple[float, float, float, float]:
    width, height = size
    x0, y0, x1, y1 = xyxy
    return (x0 / width, y0 / height, x1 / width, y1 / height)
