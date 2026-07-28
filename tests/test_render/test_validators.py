"""Tests for MLT XML validation via melt."""
from pathlib import Path
import shutil

import pytest

from open_edit.render.emitter import emit_timeline, EmitterConfig
from open_edit.render.validators import validate_mlt_loads
from open_edit.ir.apply import apply_operation
from open_edit.ir.types import AddClipOp, Timeline


pytestmark = pytest.mark.skipif(
    not shutil.which("melt"), reason="melt not installed"
)


TESTDATA = Path(__file__).parent.parent / "testdata" / "raw_videos"


def test_validate_mlt_loads_returns_true_for_valid_xml() -> None:
    timeline = Timeline()
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=2.0,
    )
    timeline = apply_operation(timeline, op)
    xml = emit_timeline(
        timeline,
        EmitterConfig(),
        asset_paths={"abc": str(TESTDATA / "clip_a.mp4")},
    )
    ok, err = validate_mlt_loads(xml)
    assert ok is True, f"melt rejected XML: {err}"


def test_validate_mlt_loads_returns_false_for_broken_xml() -> None:
    ok, err = validate_mlt_loads("<not-mlt>this is not valid mlt</not-mlt>")
    assert ok is False


def test_validate_mlt_loads_returns_false_for_empty() -> None:
    ok, err = validate_mlt_loads("")
    assert ok is False
