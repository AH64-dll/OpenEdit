"""An enabled EQ on an MLT without avfilter audio must reach the successful RenderResult."""
from pathlib import Path

from open_edit.ir.types import Effect
from open_edit.render import mlt_capability, orchestrator
from open_edit.render.melt_runner import PipeResult
from tests.test_render.test_orchestrator import _make_project


def test_eq_warning_survives_successful_render_result(tmp_path: Path, monkeypatch) -> None:
    def fake_run_pipe(cmds, *, timeout_s):
        output_path = Path(cmds.ffmpeg_cmd[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"MP4")
        return PipeResult(
            0,
            0,
            0,
            "",
            audio_elapsed_sec=0.1,
            melt_elapsed_sec=0.2,
            ffmpeg_elapsed_sec=0.3,
        )

    real_derive = orchestrator.derive_or_load_timeline

    def derive_with_eq(*args, **kwargs):
        timeline = real_derive(*args, **kwargs)
        for track in timeline.tracks:
            for clip in track.clips:
                clip.effects.append(
                    Effect(effect_id="eq", effect_type="eq", params={"gain": -12}, enabled=True)
                )
        return timeline

    monkeypatch.setattr(mlt_capability, "mlt_audio_avfilter_supported", lambda: False)
    monkeypatch.setattr(orchestrator, "derive_or_load_timeline", derive_with_eq)
    monkeypatch.setattr(orchestrator, "run_pipe", fake_run_pipe)
    monkeypatch.setattr(orchestrator, "_gpu_decode_available", lambda: False)
    monkeypatch.setattr(
        orchestrator.shutil,
        "which",
        lambda name: "/usr/bin/melt" if name == "melt" else None,
    )
    monkeypatch.setattr(
        orchestrator,
        "repair_render_output",
        lambda *args, **kwargs: {"ok": True, "changed": False},
    )

    project_dir = _make_project(tmp_path, name="eq-warning")
    result = orchestrator.render_project(
        "eq-warning",
        project_dir,
        tmp_path / "work",
        mode="proxy",
    )

    assert result.ok is True, result.error
    assert len(result.warnings) == 1
    assert "Audio EQ needs MLT 7.28" in result.warnings[0]
    assert "without EQ" in result.warnings[0]
    assert result.diagnostics["warnings"] == result.warnings
