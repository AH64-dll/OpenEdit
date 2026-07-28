"""Phase 4.5 W7: motion graphics templated skill."""
import pytest
from open_edit.agent.skills.motion_graphics.engine import (
    generate_visual, MotionTemplateParams,
)
from open_edit.agent.skills.narrative_analyzer import NarrativeSegment


def test_motion_template_params_pydantic():
    p = MotionTemplateParams(
        text="Welcome",
        background_color="#000000",
        text_color="#FFFFFF",
        animation_speed=1.0,
    )
    assert p.text == "Welcome"


def test_generate_visual_emits_code(tmp_path, monkeypatch):
    """Mock the render sandbox; verify the code is generated and run."""
    fake_output = tmp_path / "rendered.mp4"
    fake_output.write_bytes(b"fake mp4")
    monkeypatch.setattr(
        "open_edit.agent.skills.motion_graphics.engine.run_render",
        lambda **kwargs: type("R", (), {"path": fake_output, "ok": True})(),
    )

    # AssetStore.ingest_paths calls ffprobe, which would fail on a 9-byte
    # stub. Mock it to return a deterministic Asset so the test exercises
    # the engine's wiring without depending on real media decoding.
    from open_edit.ir.types import Asset
    fake_asset = Asset(
        asset_hash="fakehash",
        original_path=str(fake_output),
        stored_path=str(fake_output),
        type="video",
        duration_sec=3.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=False,
    )
    monkeypatch.setattr(
        "open_edit.storage.assets.AssetStore.ingest_paths",
        lambda self, paths: [fake_asset],
    )

    segment = NarrativeSegment(
        beat_type="hook", t_start=0.0, t_end=3.0, text="Welcome",
    )
    op = generate_visual(
        segment=segment,
        template="hook_fade_text",
        params={
            "text": "Welcome",
            "background_color": "#000",
            "text_color": "#FFF",
            "animation_speed": 1.0,
        },
        project_id="p1",
        workdir=tmp_path,
    )
    assert op.kind == "add_clip"
    assert op.track_id == "video_graphics"
    assert op.asset_hash == "fakehash"
    assert op.position_sec == 0.0
    assert op.out_point_sec == 3.0


def test_all_seven_beat_templates_exist():
    """The 7 spec beat types each have a template function in the
    templates package, named ``<beat>_fade_text`` (or appropriate
    variant) and importable by getattr on the templates package.
    """
    from open_edit.agent.skills.motion_graphics import templates
    expected = {
        "hook": "hook_fade_text",
        "turn": "turn_slide_text",
        "scope": "scope_zoom_text",
        "mechanism": "mechanism_diagram",
        "cost": "cost_warning",
        "tease": "tease_glimpse",
        "button": "button_cta",
    }
    for beat, name in expected.items():
        fn = getattr(templates, name, None)
        assert fn is not None, f"missing template function {name} for beat {beat}"
        # Each template function takes (params, duration_s) and returns str.
        params = MotionTemplateParams(text="x", background_color="#000")
        code = fn(params, 1.0)
        assert isinstance(code, str)
        assert len(code) > 0


def test_generate_visual_unknown_template_raises(tmp_path, monkeypatch):
    """Unknown template names raise ValueError before any rendering."""
    segment = NarrativeSegment(
        beat_type="hook", t_start=0.0, t_end=3.0, text="x",
    )
    with pytest.raises(ValueError, match="Unknown template"):
        generate_visual(
            segment=segment,
            template="does_not_exist",
            params={"text": "x"},
            project_id="p1",
            workdir=tmp_path,
        )
