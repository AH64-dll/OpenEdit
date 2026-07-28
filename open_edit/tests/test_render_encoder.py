"""Tests for encoder backend selection."""
from __future__ import annotations

from open_edit.render.encoder import (
    apply_profile_vcodec,
    ffmpeg_video_args,
    resolve_backend,
    resolve_vcodec,
)


def test_resolve_backend_defaults_to_gpu(monkeypatch):
    monkeypatch.delenv("OPEN_EDIT_RENDER_BACKEND", raising=False)
    assert resolve_backend() == "gpu"
    assert resolve_backend(None) == "gpu"


def test_resolve_backend_cpu_explicit(monkeypatch):
    monkeypatch.setenv("OPEN_EDIT_RENDER_BACKEND", "gpu")
    assert resolve_backend("cpu") == "cpu"


def test_resolve_backend_env_cpu(monkeypatch):
    monkeypatch.setenv("OPEN_EDIT_RENDER_BACKEND", "cpu")
    assert resolve_backend() == "cpu"


def test_resolve_vcodec_cpu_is_libx264():
    vcodec, extra = resolve_vcodec("cpu")
    assert vcodec == "libx264"
    assert "-crf" in extra


def test_apply_profile_vcodec_cpu():
    assert apply_profile_vcodec("h264_nvenc", "cpu") == "libx264"


def test_ffmpeg_video_args_cpu():
    args = ffmpeg_video_args("cpu")
    assert args[0] == "-c:v"
    assert args[1] == "libx264"
