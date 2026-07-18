from dataclasses import FrozenInstanceError
import pytest
from phase2_project_engine.types import (
    ProjectInfo, ClipSummary, TrackSummary,
    TransitionSummary, MarkerSummary, EffectSummary,
)


def test_project_info_is_frozen():
    info = ProjectInfo(
        name="x", fps=30.0, width=1920, height=1080,
        colorspace="709", track_count=4, duration_sec=10.0, path=None,
    )
    with pytest.raises(FrozenInstanceError):
        info.fps = 60.0  # type: ignore[misc]


def test_clip_summary_carries_source_id():
    c = ClipSummary(
        clip_id="1", track_index=0, start_sec=0.0, end_sec=2.0,
        source_id="42", source_path="/tmp/a.mp4", source_name="a.mp4",
        source_in_sec=0.0, source_out_sec=2.0, effects=(),
    )
    assert c.source_id == "42"
    assert c.effects == ()


def test_track_summary_kind_default_video():
    t = TrackSummary(index=0, kind="video", name="V1", clip_count=0)
    assert t.kind == "video"
    assert t.clip_count == 0


def test_effect_summary_dataclass():
    e = EffectSummary(
        effect_id="blur", clip_id="5",
        params={"gaussian_blur:radius": "2.0"},
    )
    assert e.effect_id == "blur"
    assert "gaussian_blur:radius" in e.params
