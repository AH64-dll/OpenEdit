"""Tests for the render orchestrator (melt + cache + QC)."""
import shutil
from pathlib import Path

import pytest

from open_edit.render.orchestrator import (
    RenderResult,
    render_project,
)


TESTDATA = Path(__file__).parent.parent / "testdata" / "raw_videos"


def _has_melt() -> bool:
    return shutil.which("melt") is not None


pytestmark = pytest.mark.skipif(
    not _has_melt(), reason="melt not installed"
)


def test_render_project_returns_error_when_no_ops(tmp_path: Path) -> None:
    result = render_project(
        project_id="nonexistent",
        project_dir=tmp_path,
        workdir=tmp_path,
    )
    assert result.ok is False
    assert "no ops" in (result.error or "").lower() or "empty" in (result.error or "").lower()


def test_render_result_has_required_fields() -> None:
    """RenderResult is a Pydantic model with the spec's fields."""
    r = RenderResult(ok=True, output_path="/tmp/out.mp4", mode="proxy", duration_sec=1.0, elapsed_sec=0.5)
    assert r.ok is True
    assert r.output_path == "/tmp/out.mp4"
    assert r.mode == "proxy"
    assert r.duration_sec == 1.0
    assert r.elapsed_sec == 0.5
