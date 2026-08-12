"""簇级数据集划分（§8.2/§8.3）：簇不可拆分、种子可复现、分组上限约束。"""

from __future__ import annotations

import random
from collections.abc import Sequence

from pydantic import BaseModel, Field, model_validator

from subtitle_dataset.contracts import Split

from .models import ContentCluster


class SplitConfig(BaseModel):
    ratios: dict[str, float]
    seed: int = 0
    group_limits: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> SplitConfig:
        valid_keys = {split.value for split in Split}
        invalid = set(self.ratios) - valid_keys
        if invalid:
            raise ValueError(f"ratios 含未知 split: {sorted(invalid)}")
        if not self.ratios:
            raise ValueError("ratios 不能为空")
        if any(value <= 0 for value in self.ratios.values()):
            raise ValueError("ratios 必须全部为正")
        if abs(sum(self.ratios.values()) - 1.0) > 1e-6:
            raise ValueError(f"ratios 之和需为 1，实际 {sum(self.ratios.values())}")
        for dimension, limit in self.group_limits.items():
            if not 0.0 < limit <= 1.0:
                raise ValueError(f"group_limits[{dimension}] 需在 (0, 1] 内")
        return self


class SplitAssignment(BaseModel):
    seed: int
    assignments: dict[str, Split]
    cluster_counts: dict[str, int]
    item_counts: dict[str, int]
    group_shares: dict[str, dict[str, dict[str, float]]]
    warnings: list[str]


class SplitAllocator:
    """贪心分配：优先放入相对目标占比最缺的 split，并尽量满足分组上限。"""

    def __init__(self, config: SplitConfig) -> None:
        self._config = config

    def allocate(self, clusters: Sequence[ContentCluster]) -> SplitAssignment:
        total_items = sum(len(cluster.items) for cluster in clusters)
        rng = random.Random(self._config.seed)
        ordered = list(clusters)
        rng.shuffle(ordered)
        configured_splits = [Split(value) for value in self._config.ratios]

        assignments: dict[str, Split] = {}
        item_counts = {split.value: 0 for split in configured_splits}
        cluster_counts = {split.value: 0 for split in configured_splits}
        group_counts: dict[tuple[str, str, str], int] = {}
        warnings: list[str] = []

        for cluster in ordered:
            size = len(cluster.items)
            candidates = sorted(
                configured_splits,
                key=lambda split: (
                    self._config.ratios[split.value]
                    - (item_counts[split.value] / total_items if total_items else 0.0)
                ),
                reverse=True,
            )
            chosen: Split | None = None
            for split in candidates:
                if self._fits(cluster, split, item_counts, group_counts):
                    chosen = split
                    break
            if chosen is None:
                chosen = candidates[0]
                warnings.append(
                    f"簇 {cluster.cluster_id} 无法满足分组上限约束，放入 {chosen.value}"
                )
            assignments[cluster.cluster_id] = chosen
            item_counts[chosen.value] += size
            cluster_counts[chosen.value] += 1
            for dimension, key in self._group_keys(cluster).items():
                group_counts[(chosen.value, dimension, key)] = (
                    group_counts.get((chosen.value, dimension, key), 0) + size
                )

        group_shares = self._compute_group_shares(group_counts, item_counts)
        for (split_value, dimension, key), count in group_counts.items():
            total = item_counts[split_value]
            if total and self._config.group_limits.get(dimension, 1.0) < count / total:
                warnings.append(
                    f"{dimension}={key} 在 {split_value} 占比 {count / total:.2%} 超过上限"
                )
        return SplitAssignment(
            seed=self._config.seed,
            assignments=assignments,
            cluster_counts=cluster_counts,
            item_counts=item_counts,
            group_shares=group_shares,
            warnings=warnings,
        )

    def _fits(
        self,
        cluster: ContentCluster,
        split: Split,
        item_counts: dict[str, int],
        group_counts: dict[tuple[str, str, str], int],
    ) -> bool:
        size = len(cluster.items)
        current_total = item_counts[split.value]
        if current_total == 0:
            return True
        new_total = current_total + size
        for dimension, limit in self._config.group_limits.items():
            key = self._group_keys(cluster).get(dimension)
            if key is None:
                continue
            current = group_counts.get((split.value, dimension, key), 0)
            if (current + size) / new_total > limit:
                return False
        return True

    def _group_keys(self, cluster: ContentCluster) -> dict[str, str]:
        first = cluster.items[0] if cluster.items else None
        keys: dict[str, str] = {}
        if first is not None:
            if first.platform:
                keys["platform"] = first.platform
            if first.creator_id:
                keys["creator"] = first.creator_id
            if first.group_id:
                keys["video"] = first.group_id
        keys["cluster"] = cluster.cluster_id
        return keys

    def _compute_group_shares(
        self,
        group_counts: dict[tuple[str, str, str], int],
        item_counts: dict[str, int],
    ) -> dict[str, dict[str, dict[str, float]]]:
        shares: dict[str, dict[str, dict[str, float]]] = {}
        for (split_value, dimension, key), count in group_counts.items():
            total = item_counts[split_value]
            if not total:
                continue
            shares.setdefault(dimension, {}).setdefault(split_value, {})[key] = count / total
        return shares
