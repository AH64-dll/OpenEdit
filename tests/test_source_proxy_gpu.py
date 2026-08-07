
"""Source-proxy GPU encoder preference (transparent NVENC upgrade)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from open_edit.render import source_proxy
from open_edit.render.source_proxy import (
    DEFAULT_SOURCE_PROXY_PROFILE,
    _resolve_encoder,
    generate_asset_proxy,
)
from open_edit.storage.assets import AssetStore


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required",
)


def _make_source(tmp_path: Path) -> str:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i",
            f"testsrc=size=1280x720:rate=24:duration=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(tmp_path / "source.mp4"),
        ],
        capture_output=True, text=True, check=True,
    )
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    return store.ingest(str(tmp_path / "source.mp4"), transcribe=False).asset_hash


def test_resolve_encoder_prefers_nvenc_when_probe_passes(monkeypatch) -> None:
    monkeypatch.setattr(source_proxy, "_probe_nvenc", lambda: True)
    vcodec, flags = _resolve_encoder(DEFAULT_SOURCE_PROXY_PROFILE)
    assert vcodec == "h264_nvenc"
    assert "-rc" in flags and "constqp" in flags
    assert "-cq" in flags
    assert "-crf" not in flags


def test_resolve_encoder_falls_back_to_libx264_when_probe_fails(monkeypatch) -> None:
    monkeypatch.setattr(source_proxy, "_probe_nvenc", lambda: False)
    vcodec, flags = _resolve_encoder(DEFAULT_SOURCE_PROXY_PROFILE)
    assert vcodec == "libx264"
    assert "-crf" in flags
    assert flags[flags.index("-preset") + 1] == DEFAULT_SOURCE_PROXY_PROFILE.preset


def test_resolve_encoder_respects_gpu_disable_env(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_EDIT_SOURCE_PROXY_GPU", "0")
    # Even a passing probe must not enable GPU when the env says no.
    monkeypatch.setattr(source_proxy, "_probe_nvenc", lambda: True)
    vcodec, _ = _resolve_encoder(DEFAULT_SOURCE_PROXY_PROFILE)
    assert vcodec == "libx264"


def test_generate_asset_proxy_uses_nvenc_command_and_reports_encoder(
    tmp_path: Path, monkeypatch,
) -> None:
    asset_hash = _make_source(tmp_path)
    monkeypatch.setattr(source_proxy, "_probe_nvenc", lambda: True)
    captured: dict = {}

    def fake_run(command, *args, **kwargs):
        captured["command"] = list(command)
        # The last element is the temp output path; write bytes so the
        # CAS store accepts it without a real encode.
        Path(command[-1]).write_bytes(b"fake proxy bytes")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(source_proxy.subprocess, "run", fake_run)

    result = generate_asset_proxy(tmp_path, asset_hash)

    assert result.status == "ready"
    assert result.encoder == "h264_nvenc"
    cmd = captured["command"]
    assert cmd[cmd.index("-c:v") + 1] == "h264_nvenc"
    assert "-cq" in cmd
    assert "-crf" not in cmd


def test_generate_asset_proxy_falls_back_to_libx264_command(
    tmp_path: Path, monkeypatch,
) -> None:
    asset_hash = _make_source(tmp_path)
    monkeypatch.setattr(source_proxy, "_probe_nvenc", lambda: False)
    captured: dict = {}

    def fake_run(command, *args, **kwargs):
        captured["command"] = list(command)
        Path(command[-1]).write_bytes(b"fake proxy bytes")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(source_proxy.subprocess, "run", fake_run)

    result = generate_asset_proxy(tmp_path, asset_hash)

    assert result.status == "ready"
    assert result.encoder == "libx264"
    cmd = captured["command"]
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert "-crf" in cmd
    assert "-cq" not in cmd


def test_generate_asset_proxy_profile_contract_unchanged_with_gpu(
    tmp_path: Path, monkeypatch,
) -> None:
    """The sidecar profile name must stay the default even on the GPU path."""
    asset_hash = _make_source(tmp_path)
    monkeypatch.setattr(source_proxy, "_probe_nvenc", lambda: True)

    def fake_run(command, *args, **kwargs):
        Path(command[-1]).write_bytes(b"fake proxy bytes")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(source_proxy.subprocess, "run", fake_run)
    result = generate_asset_proxy(tmp_path, asset_hash)

    store = AssetStore(tmp_path / ".open_edit" / "assets")
    linked = store.get(asset_hash)
    assert result.status == "ready"
    assert linked is not None
    assert linked.proxy_profile == DEFAULT_SOURCE_PROXY_PROFILE.name
    assert linked.proxy_status == "ready"
