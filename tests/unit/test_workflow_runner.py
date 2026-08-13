"""工作流运行器：run_id 确定性、失败恢复、强制重建。"""

from __future__ import annotations

from pathlib import Path

import pytest

from subtitle_dataset.contracts import StageStatus
from subtitle_dataset.workflows import (
    RunState,
    StageContext,
    WorkflowRunner,
    compute_run_id,
    load_run,
)


def _run_id(**overrides: object) -> str:
    base: dict[str, object] = {
        "dataset_version": "v1",
        "seed": 1,
        "input_sha256": "a" * 64,
        "stage_config_hashes": {"ingest": "b" * 64},
        "code_version": "git-abc",
        "n_events": 3,
    }
    base.update(overrides)
    return compute_run_id(**base)  # type: ignore[arg-type]


def _state(run_id: str) -> RunState:
    return RunState(
        run_id=run_id,
        dataset_version="v1",
        code_version="git-abc",
        dependency_versions={"pydantic": "2"},
        seed=1,
        input_sha256="a" * 64,
        stage_config_hashes={"a": "x", "b": "y"},
    )


def test_run_id_deterministic_and_sensitive_to_inputs() -> None:
    assert _run_id() == _run_id()
    assert _run_id(seed=2) != _run_id()
    assert _run_id(input_sha256="b" * 64) != _run_id()
    assert _run_id(code_version="git-def") != _run_id()


def test_resume_after_failure_skips_done_stages(tmp_path: Path) -> None:
    calls: list[str] = []
    attempts = {"b": 0}

    def stage_a(ctx: StageContext) -> None:
        calls.append("a")

    def stage_b(ctx: StageContext) -> None:
        calls.append("b")
        attempts["b"] += 1
        if attempts["b"] == 1:
            raise RuntimeError("boom")

    outdir = tmp_path / "out"
    state = _state("run-1")
    runner = WorkflowRunner(outdir, state)
    with pytest.raises(RuntimeError, match="boom"):
        runner.execute([("a", stage_a, "x"), ("b", stage_b, "y")])
    assert state.stages["a"].status is StageStatus.DONE
    assert state.stages["b"].status is StageStatus.FAILED
    assert state.status is StageStatus.FAILED

    loaded = load_run(outdir)
    assert loaded is not None
    resumed = WorkflowRunner(outdir, loaded)
    final = resumed.execute([("a", stage_a, "x"), ("b", stage_b, "y")])
    assert calls.count("a") == 1  # 第二次 a 被跳过
    assert attempts["b"] == 2  # b 重跑并成功
    assert final.status is StageStatus.DONE


def test_force_reruns_done_stages(tmp_path: Path) -> None:
    calls: list[str] = []

    def stage_a(ctx: StageContext) -> None:
        calls.append("a")

    outdir = tmp_path / "out"
    WorkflowRunner(outdir, _state("run-1")).execute([("a", stage_a, "x")])
    loaded = load_run(outdir)
    assert loaded is not None
    WorkflowRunner(outdir, loaded).execute([("a", stage_a, "x")], force=True)
    assert calls.count("a") == 2


def test_run_state_roundtrip(tmp_path: Path) -> None:
    from subtitle_dataset.workflows import StageRun

    state = _state("run-2")
    state.stages["a"] = StageRun(name="a", status=StageStatus.DONE)
    from subtitle_dataset.workflows.runner import save_run

    save_run(state, tmp_path)
    reloaded = load_run(tmp_path)
    assert reloaded is not None
    assert reloaded.run_id == "run-2"
    assert reloaded.stages["a"].status is StageStatus.DONE
