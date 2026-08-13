"""工作流运行器：幂等重跑、失败恢复、强制重建（§15）。"""

from __future__ import annotations

import importlib.metadata
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from subtitle_dataset.contracts import StageStatus, canonical_dumps, sha256_hex

REPO_ROOT = Path(__file__).resolve().parents[3]


def code_version() -> str:
    """优先用 git 短哈希，否则用包版本。"""
    try:
        rev = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        ).stdout.strip()
        if rev:
            return f"git-{rev}"
    except OSError:
        pass
    return "unknown"


def dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in ("pydantic", "pillow", "pyarrow", "numpy", "fonttools"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "unknown"
    return versions


class StageRun(BaseModel):
    name: str
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    config_sha256: str | None = None
    outputs: list[str] = Field(default_factory=list)
    error: str | None = None


class RunState(BaseModel):
    run_id: str
    dataset_version: str
    code_version: str
    dependency_versions: dict[str, str]
    seed: int
    input_sha256: str
    stage_config_hashes: dict[str, str]
    stages: dict[str, StageRun] = Field(default_factory=dict)
    status: StageStatus = StageStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


def compute_run_id(
    *,
    dataset_version: str,
    seed: int,
    input_sha256: str,
    stage_config_hashes: dict[str, str],
    code_version: str,
    n_events: int,
) -> str:
    payload = canonical_dumps(
        {
            "dataset_version": dataset_version,
            "seed": seed,
            "input_sha256": input_sha256,
            "stage_config_hashes": stage_config_hashes,
            "code_version": code_version,
            "n_events": n_events,
        }
    )
    return sha256_hex(payload)


def load_run(outdir: Path) -> RunState | None:
    path = outdir / "workflow.json"
    if not path.exists():
        return None
    return RunState.model_validate_json(path.read_text(encoding="utf-8"))


def save_run(state: RunState, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "workflow.json").write_text(
        state.model_dump_json(indent=2),
        encoding="utf-8",
    )


@dataclass
class StageContext:
    outdir: Path
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: list[Path] = field(default_factory=list)


class WorkflowRunner:
    """按阶段顺序执行；DONE 阶段跳过（幂等），FAILED/PENDING 继续（恢复）。"""

    def __init__(self, outdir: Path, state: RunState) -> None:
        self._outdir = outdir
        self._state = state
        self._inputs: dict[str, Any] = {}

    def execute(
        self,
        stages: Sequence[tuple[str, Callable[[StageContext], None], str]],
        *,
        force: bool = False,
    ) -> RunState:
        for name, func, config_hash in stages:
            stage = self._state.stages.get(name) or StageRun(name=name)
            self._state.stages[name] = stage
            stage.config_sha256 = config_hash
            if stage.status is StageStatus.DONE and not force:
                continue
            stage.status = StageStatus.RUNNING
            stage.started_at = datetime.now(UTC)
            stage.error = None
            try:
                context = StageContext(outdir=self._outdir, inputs=self._inputs)
                func(context)
                stage.status = StageStatus.DONE
                stage.outputs = [str(path) for path in context.outputs]
                stage.finished_at = datetime.now(UTC)
                self._inputs = context.inputs
                save_run(self._state, self._outdir)
            except Exception as exc:  # noqa: BLE001 - 阶段失败由状态机接管
                stage.status = StageStatus.FAILED
                stage.error = f"{type(exc).__name__}: {exc}"
                stage.finished_at = datetime.now(UTC)
                self._state.status = StageStatus.FAILED
                save_run(self._state, self._outdir)
                raise
        self._state.status = StageStatus.DONE
        self._state.finished_at = datetime.now(UTC)
        save_run(self._state, self._outdir)
        return self._state
