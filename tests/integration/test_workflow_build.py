"""工作流构建端到端：幂等、恢复、重建、CLI。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from tests.helpers import make_synthetic_video

from subtitle_dataset.contracts import StageStatus
from subtitle_dataset.workflows import load_run, run_build
from subtitle_dataset.workflows.build import WorkflowConfig


@pytest.fixture()
def workflow_config(tmp_path: Path) -> WorkflowConfig:
    if shutil.which("ffmpeg") is None:
        pytest.skip("缺少 ffmpeg")
    video = tmp_path / "test.mp4"
    make_synthetic_video(video)
    return WorkflowConfig(
        dataset_version="v1",
        seed=123,
        video_path=str(video),
        n_events=2,
        ingest_config_path="configs/ingest/default.json",
        sampling_config_path="configs/sampling/default.json",
    )


def test_workflow_build_idempotent_and_force(
    workflow_config: WorkflowConfig, tmp_path: Path
) -> None:
    outdir = tmp_path / "build"
    first = run_build(workflow_config, outdir)
    assert first.status is StageStatus.DONE
    assert set(first.stages) == {"ingest", "generate", "export"}
    assert all(stage.status is StageStatus.DONE for stage in first.stages.values())
    assert (outdir / "frames" / "manifest.json").exists()
    assert (outdir / "samples" / "manifest.json").exists()
    assert (outdir / "parquet" / "samples.parquet").exists()
    assert (outdir / "workflow.json").exists()

    manifest_path = outdir / "samples" / "manifest.json"
    mtime_before = manifest_path.stat().st_mtime
    second = run_build(workflow_config, outdir)
    assert second.run_id == first.run_id
    assert manifest_path.stat().st_mtime == mtime_before  # 幂等：跳过不重写

    run_build(workflow_config, outdir, force=True)
    assert manifest_path.stat().st_mtime != mtime_before  # force 重写

    state = load_run(outdir)
    assert state is not None
    assert state.code_version
    assert state.dependency_versions["pydantic"]
    assert state.stage_config_hashes["ingest"]


def test_workflow_cli(workflow_config: WorkflowConfig, tmp_path: Path) -> None:
    from subtitle_dataset.cli import main

    config_path = tmp_path / "workflow.json"
    config_path.write_text(workflow_config.model_dump_json(indent=2), encoding="utf-8")
    outdir = tmp_path / "cli_build"
    assert (
        main(
            [
                "workflow",
                "run",
                "--config",
                str(config_path),
                "--outdir",
                str(outdir),
            ]
        )
        == 0
    )
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        assert main(["workflow", "status", "--outdir", str(outdir)]) == 0
    status = json.loads(buffer.getvalue())
    assert status["status"] == "done"
    assert status["stages"]["ingest"]["status"] == "done"
