"""Windows MCP portability: sandbox defaults, pathsep, melt, encoder."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from open_edit.agent.sandbox import (
    DevSubprocessBackend,
    get_sandbox_backend,
    run_render,
)
from open_edit.render.encoder import resolve_backend
from open_edit.render.melt_runner import MeltRunner
from open_edit.render.profiles import RenderProfile


def test_windows_default_sandbox_backend_is_dev(monkeypatch):
    monkeypatch.delenv("OPEN_EDIT_SANDBOX_BACKEND", raising=False)
    with patch("open_edit.agent.sandbox.backends.sys.platform", "win32"):
        backend = get_sandbox_backend()
    assert isinstance(backend, DevSubprocessBackend)
    assert backend.name == "dev"


def test_windows_explicit_bwrap_raises(monkeypatch):
    monkeypatch.setenv("OPEN_EDIT_SANDBOX_BACKEND", "bwrap")
    with patch("open_edit.agent.sandbox.backends.sys.platform", "win32"):
        with pytest.raises(ValueError, match="not supported on Windows"):
            get_sandbox_backend()


def test_windows_run_render_unsupported(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("open_edit.agent.sandbox.bridge.sys.platform", "win32"):
        result = run_render("print(1)", tmp_path, out)
    assert result.ok is False
    assert result.detail == "render_sandbox_unsupported_on_windows"


def test_build_melt_command_skips_nice_on_windows(tmp_path):
    profile = RenderProfile(
        name="proxy", width=1280, height=720,
        frame_rate_num=30, frame_rate_den=1, vcodec="libx264", acodec="aac",
    )
    xml = tmp_path / "t.mlt"
    out = tmp_path / "o.mp4"
    with patch("open_edit.render.melt_runner.os.name", "nt"):
        cmd = MeltRunner(melt_bin="melt").build_command(xml, out, profile)
    assert cmd[0] == "melt"
    assert "nice" not in cmd


def test_build_melt_command_uses_nice_on_posix(tmp_path):
    profile = RenderProfile(
        name="proxy", width=1280, height=720,
        frame_rate_num=30, frame_rate_den=1, vcodec="libx264", acodec="aac",
    )
    xml = tmp_path / "t.mlt"
    out = tmp_path / "o.mp4"
    with patch("open_edit.render.melt_runner.os.name", "posix"):
        cmd = MeltRunner(melt_bin="melt", nice_level=10).build_command(xml, out, profile)
    assert cmd[:3] == ["nice", "-n", "10"]


def test_resolve_backend_defaults_gpu_when_unset(monkeypatch):
    """GPU is the default on all platforms; NVENC/AMF/QSV/VAAPI probed at encode time."""
    monkeypatch.delenv("OPEN_EDIT_RENDER_BACKEND", raising=False)
    assert resolve_backend() == "gpu"


def test_diagnostics_sandbox_dev_on_windows(monkeypatch):
    monkeypatch.delenv("OPEN_EDIT_SANDBOX_BACKEND", raising=False)
    with patch("open_edit.serve.diagnostics.sys.platform", "win32"):
        from open_edit.serve.diagnostics import _sandbox_backend
        assert _sandbox_backend() == "dev"
