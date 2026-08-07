
"""Ingest auto-enqueue hook for source-proxy generation."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from open_edit.storage.assets import AssetStore, source_proxy_auto_enqueue_enabled


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required",
)


def _make_video(path: Path, *, width: int = 1280, height: int = 720) -> Path:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i",
            f"testsrc=size={width}x{height}:rate=24:duration=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return path


def _enqueue_mock():
    return mock.Mock()


def test_auto_enqueue_defaults_on() -> None:
    assert source_proxy_auto_enqueue_enabled() is True


def test_auto_enqueue_off_via_env(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_EDIT_SOURCE_PROXY_AUTO", "0")
    assert source_proxy_auto_enqueue_enabled() is False


def test_ingest_enqueues_proxy_job_for_high_res_video(
    tmp_path: Path, monkeypatch,
) -> None:
    enqueue = _enqueue_mock()
    monkeypatch.setattr(
        "open_edit.kernel.asset_proxy_jobs.DEFAULT_ASSET_PROXY_JOB_SERVICE",
        enqueue,
    )
    source = _make_video(tmp_path / "source.mp4")
    store = AssetStore(tmp_path / ".open_edit" / "assets")

    asset = store.ingest(str(source), transcribe=False)

    enqueue.enqueue.assert_called_once()
    call = enqueue.enqueue.call_args
    assert call.args[2] == asset.asset_hash
    assert call.kwargs["profile"].name == "source_proxy_360_v1"
    assert str(tmp_path) in str(call.args[1])


def test_ingest_skips_enqueue_when_disabled(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_EDIT_SOURCE_PROXY_AUTO", "0")
    enqueue = _enqueue_mock()
    monkeypatch.setattr(
        "open_edit.kernel.asset_proxy_jobs.DEFAULT_ASSET_PROXY_JOB_SERVICE",
        enqueue,
    )
    source = _make_video(tmp_path / "source.mp4")
    store = AssetStore(tmp_path / ".open_edit" / "assets")

    store.ingest(str(source), transcribe=False)

    enqueue.enqueue.assert_not_called()


def test_ingest_skips_enqueue_for_small_video(tmp_path: Path) -> None:
    enqueue = _enqueue_mock()
    with mock.patch(
        "open_edit.kernel.asset_proxy_jobs.DEFAULT_ASSET_PROXY_JOB_SERVICE",
        enqueue,
    ):
        source = _make_video(tmp_path / "small.mp4", width=320, height=240)
        store = AssetStore(tmp_path / ".open_edit" / "assets")
        store.ingest(str(source), transcribe=False)

    enqueue.enqueue.assert_not_called()


def test_ingest_never_fails_when_enqueue_raises(tmp_path: Path) -> None:
    enqueue = mock.Mock()
    enqueue.enqueue.side_effect = RuntimeError("queue down")
    with mock.patch(
        "open_edit.kernel.asset_proxy_jobs.DEFAULT_ASSET_PROXY_JOB_SERVICE",
        enqueue,
    ):
        source = _make_video(tmp_path / "source.mp4")
        store = AssetStore(tmp_path / ".open_edit" / "assets")
        asset = store.ingest(str(source), transcribe=False)

    assert asset.asset_hash
    assert asset.type == "video"
