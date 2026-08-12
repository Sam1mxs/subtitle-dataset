"""采样-渲染-校验-重试闭环。"""

from __future__ import annotations

import random
from dataclasses import dataclass

from PIL import Image
from pydantic import BaseModel, Field

from subtitle_dataset.contracts import BuildInfo, SourceInfo, Split, Transform
from subtitle_dataset.filtering import (
    FilteringConfig,
    HeuristicTextRegionDetector,
    TextRegionDetector,
    assign_geometric_roles,
)
from subtitle_dataset.filtering.policy import check_frame_text_policy
from subtitle_dataset.qa import check_strict_pairing
from subtitle_dataset.rendering import PillowRenderer
from subtitle_dataset.rendering.config import RenderConfig, RenderStyle
from subtitle_dataset.rendering.renderer import RENDERER_VERSION

from .config import REPO_ROOT, SamplingConfig
from .durations import DurationSampler
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
    text_policy_ok: bool | None = None
    text_policy_reasons: list[str] = Field(default_factory=list)
    split: Split | None = None


@dataclass(frozen=True)
class GeneratedSample:
    record: GeneratedSampleRecord
    rendered: Image.Image
    alpha_mask: Image.Image
    inpaint_mask: Image.Image


class SampleSampler:
    """闭环入口：clean image + SamplingConfig → 一批严格配对的生成样本。

    每个样本使用独立的种子（``config.seed + index * 7919``），保证相同配置
    下无论批次大小如何都可复现。
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
        if transform is not None and tuple(transform.target_size) != clean.size:
            raise ValueError(
                f"transform.target_size {transform.target_size} 与 clean 尺寸 {clean.size} 不一致"
            )
        sample_seed = self._config.seed + index * 7919
        rng = random.Random(sample_seed)
        duration_ms = DurationSampler(self._config.durations, rng).sample()
        text_lines = TextSampler(self._corpus, self._config.single_line_prob, rng).sample()
        style_sampler = StyleSampler(self._config.style, rng)
        position_sampler = PositionSampler(self._config.position, rng)

        for _ in range(self._config.max_attempts):
            style = style_sampler.sample()
            center = position_sampler.sample()
            render_config = RenderConfig(
                text="\n".join(text_lines),
                style=style,
                center=center,
                inpaint_dilation_px=self._config.inpaint_dilation_px,
                require_ml_training_fonts=self._config.require_ml_training_fonts,
            )
            try:
                result = self._renderer.render(clean, render_config)
            except ValueError:
                # 越界或缺字等采样冲突：重新采样并重试
                continue

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
                decision = check_frame_text_policy(
                    boxes,
                    target,
                    self._config.text_policy,
                )
                if not decision.ok:
                    continue
                text_policy_ok = True
                text_policy_reasons: list[str] = []
            else:
                text_policy_ok = None
                text_policy_reasons = []
            _, y0, _, y1 = result.effect_bbox_xyxy
            center_y = (y0 + y1) / 2 / clean.height
            if not 0.60 <= center_y <= 0.90:
                continue

            record = GeneratedSampleRecord(
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
                pairing_ok=check.ok,
                max_abs_diff_outside_mask=check.max_abs_diff_outside_mask,
                source=source,
                transform=transform,
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
            )
            return GeneratedSample(
                record=record,
                rendered=result.rendered,
                alpha_mask=result.alpha_mask,
                inpaint_mask=result.inpaint_mask,
            )

        raise SamplingExhaustedError(
            f"样本 {index} 在 {self._config.max_attempts} 次尝试内未生成合法布局"
        )


def _normalize_bbox(
    xyxy: tuple[int, int, int, int],
    size: tuple[int, int],
) -> tuple[float, float, float, float]:
    width, height = size
    x0, y0, x1, y1 = xyxy
    return (x0 / width, y0 / height, x1 / width, y1 / height)
