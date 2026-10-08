"""Windows MCP portability: sandbox defaults, pathsep, melt, encoder."""
from __future__ import annotations

from unittest.mock import patch

from open_edit.render.encoder import resolve_backend
from open_edit.render.melt_runner import MeltRunner
from open_edit.render.profiles import RenderProfile


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
