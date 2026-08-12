"""本地 HTTP 测试源：采集框架全链路。"""

from __future__ import annotations

import contextlib
import functools
import io
import json
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from tests.helpers import make_synthetic_video

REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECT_CONFIG = REPO_ROOT / "configs" / "ingest" / "collect.json"


def _authorized_registry(tmp_path: Path, source_id: str = "test-src") -> Path:
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "version": "1",
                "sources": [
                    {
                        "source_id": source_id,
                        "platform": "bilibili",
                        "license_status": "authorized",
                        "allowed_to_download": True,
                        "allowed_for_derivative_work": True,
                        "allowed_for_ml_training": True,
                        "allowed_to_redistribute": False,
                        "authorization_reference": "测试合同-2026-001",
                        "authorization_start_at": "2026-01-01",
                        "authorization_expire_at": "2026-12-31",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_collect_end_to_end(tmp_path: Path) -> None:
    from subtitle_dataset.cli import main

    if shutil.which("ffmpeg") is None:
        return
    server_dir = tmp_path / "server"
    (server_dir / "videos").mkdir(parents=True)
    video = server_dir / "videos" / "v001.mp4"
    make_synthetic_video(video)
    (server_dir / "manifest.json").write_text(
        json.dumps(
            {"items": [{"item_id": "v001", "title": "测试视频", "url": "videos/v001.mp4"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(server_dir))
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    except OSError as exc:
        pytest.skip(f"环境不允许本地 socket: {exc}")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{httpd.server_address[1]}"
        registry = _authorized_registry(tmp_path)
        outdir = tmp_path / "out"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exit_code = main(
                [
                    "collect",
                    "--source-id",
                    "test-src",
                    "--adapter",
                    "local-http",
                    "--base-url",
                    base_url,
                    "--outdir",
                    str(outdir),
                    "--registry",
                    str(registry),
                    "--config",
                    str(COLLECT_CONFIG),
                ]
            )
        assert exit_code == 0
        downloaded = outdir / "raw" / "test-src" / "v001.mp4"
        assert downloaded.exists()
        state = json.loads((outdir / "collected.json").read_text(encoding="utf-8"))
        assert len(state["items"]) == 1
        assert state["items"][0]["sha256"]
        assert json.loads((outdir / "failures.json").read_text(encoding="utf-8")) == []

        # 第二次运行幂等：跳过，不重复下载
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exit_code = main(
                [
                    "collect",
                    "--source-id",
                    "test-src",
                    "--adapter",
                    "local-http",
                    "--base-url",
                    base_url,
                    "--outdir",
                    str(outdir),
                    "--registry",
                    str(registry),
                    "--config",
                    str(COLLECT_CONFIG),
                ]
            )
        assert exit_code == 0
        assert "跳过重复 1" in buffer.getvalue()

        # 删除条目
        assert (
            main(
                [
                    "collect-delete",
                    "--source-id",
                    "test-src",
                    "--item-id",
                    "v001",
                    "--outdir",
                    str(outdir),
                    "--registry",
                    str(registry),
                ]
            )
            == 0
        )
        assert not downloaded.exists()
    finally:
        httpd.shutdown()
        httpd.server_close()
