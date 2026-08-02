from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
from open_edit.ir.types import Clip, Timeline, Track
from open_edit.qc.black_frames import BlackFramesResult, BlackSpan
from open_edit.qc.frozen_frames import FrozenFramesResult, FrozenSpan
from open_edit.render import source_repair as mod


def test_collect_source_baseline_maps_asset_spans_to_timeline(
    tmp_path: Path, monkeypatch,
) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"source")
    timeline = Timeline(
        duration_sec=5.0,
        tracks=[Track(
            track_id="v1",
            kind="video",
            clips=[Clip(
                clip_id="clip-1",
                asset_hash="asset-1",
                track_id="v1",
                track_kind="video",
                position_sec=2.0,
                in_point_sec=1.0,
                out_point_sec=4.0,
            )],
        )],
    )
    monkeypatch.setattr(
        mod, "list_black_frames",
        lambda *args, **kwargs: BlackFramesResult(
            ok=True, in_sec=0.0, out_sec=0.0, threshold=0.1, min_sec=0.5,
            spans=[BlackSpan(start_sec=1.5, end_sec=2.0, duration_sec=0.5)],
        ),
    )
    monkeypatch.setattr(
        mod, "list_frozen_frames",
        lambda *args, **kwargs: FrozenFramesResult(
            ok=True, min_sec=1.0, noise_db=-50.0,
            spans=[FrozenSpan(start_sec=2.5, end_sec=3.0, duration_sec=0.5)],
        ),
    )

    baseline = mod.collect_source_baseline(
        timeline, {"asset-1": str(source)},
    )

    assert baseline["source_hashes"]["asset-1"] == hashlib.sha256(b"source").hexdigest()
    assert baseline["black_frames"][0]["start_sec"] == 2.5
    assert baseline["black_frames"][0]["end_sec"] == 3.0
    assert baseline["black_frames"][0]["source_known"] is True
    assert baseline["frozen_frames"][0]["start_sec"] == 3.5


def test_repair_frame_sequence_replaces_black_and_interpolates_frozen() -> None:
    frames = [
        bytes((0, 0, 255)),
        bytes((0, 0, 0)),
        bytes((0, 0, 0)),
        bytes((255, 0, 0)),
    ]
    repaired = mod.repair_frame_sequence(
        frames,
        fps=1.0,
        black_spans=[{"start_sec": 1.0, "end_sec": 2.0}],
        frozen_spans=[{"start_sec": 2.0, "end_sec": 3.0}],
    )

    assert repaired[1] == frames[0]
    assert repaired[2] not in {frames[0], frames[3]}
    assert repaired[0] == frames[0]
    assert repaired[3] == frames[3]


def test_render_repair_preserves_overlay_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Source repair must not overwrite a burned overlay interval."""
    rendered = tmp_path / "rendered.mp4"
    rendered.write_bytes(b"rendered")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        mod,
        "list_black_frames",
        lambda *args, **kwargs: BlackFramesResult(
            ok=True, in_sec=0.0, out_sec=4.0, threshold=0.1, min_sec=0.5,
            spans=[BlackSpan(start_sec=0.0, end_sec=4.0, duration_sec=4.0)],
        ),
    )
    monkeypatch.setattr(
        mod,
        "list_frozen_frames",
        lambda *args, **kwargs: FrozenFramesResult(
            ok=True, min_sec=1.0, noise_db=-50.0, spans=[],
        ),
    )
    monkeypatch.setattr(mod, "_video_layout", lambda path: (2, 2, 10.0))

    def fake_repair_stream(input_path, output_path, **kwargs):
        captured["spans"] = kwargs["spans"]
        Path(output_path).write_bytes(b"repaired")

    monkeypatch.setattr(mod, "_repair_stream", fake_repair_stream)

    result = mod.repair_render_output(
        rendered,
        tmp_path / "repaired.mp4",
        source_baseline={
            "black_frames": [{
                "start_sec": 0.0, "end_sec": 4.0, "duration_sec": 4.0,
            }],
        },
        protected_spans=[(1.0, 2.0)],
    )

    assert result["ok"] is True, result
    assert result["repaired_black_spans"] == [
        {"start_sec": 0.0, "end_sec": 1.0, "duration_sec": 1.0},
        {"start_sec": 2.0, "end_sec": 4.0, "duration_sec": 2.0},
    ]
    assert captured["spans"] == [(0, 10, "black"), (20, 40, "black")]


def test_render_repair_leaves_source_frozen_spans_untouched_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Low-motion source content must not be replaced by invented blends."""
    rendered = tmp_path / "rendered.mp4"
    rendered.write_bytes(b"rendered")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        mod,
        "list_black_frames",
        lambda *args, **kwargs: BlackFramesResult(
            ok=True, in_sec=0.0, out_sec=2.0, threshold=0.1, min_sec=0.5,
            spans=[],
        ),
    )
    monkeypatch.setattr(
        mod,
        "list_frozen_frames",
        lambda *args, **kwargs: FrozenFramesResult(
            ok=True, min_sec=1.0, noise_db=-50.0,
            spans=[FrozenSpan(start_sec=0.0, end_sec=2.0, duration_sec=2.0)],
        ),
    )
    monkeypatch.setattr(mod, "_video_layout", lambda path: (2, 2, 10.0))

    def fail_if_called(*args, **kwargs):
        captured["called"] = True

    monkeypatch.setattr(mod, "_repair_stream", fail_if_called)

    result = mod.repair_render_output(
        rendered,
        tmp_path / "repaired.mp4",
        source_baseline={
            "frozen_frames": [{
                "start_sec": 0.0, "end_sec": 2.0, "duration_sec": 2.0,
            }],
        },
    )

    assert result["ok"] is True, result
    assert result["changed"] is False
    assert result["output_path"] == str(rendered)
    assert result["repaired_frozen_spans"] == []
    assert "called" not in captured


def test_render_repair_skips_clean_source_spans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clean output should not trigger a full RGB repair pass."""
    rendered = tmp_path / "rendered.mp4"
    rendered.write_bytes(b"rendered")

    monkeypatch.setattr(
        mod,
        "list_black_frames",
        lambda *args, **kwargs: BlackFramesResult(
            ok=True, in_sec=0.0, out_sec=4.0, threshold=0.1, min_sec=0.5,
            spans=[],
        ),
    )
    monkeypatch.setattr(
        mod,
        "list_frozen_frames",
        lambda *args, **kwargs: FrozenFramesResult(
            ok=True, min_sec=1.0, noise_db=-50.0, spans=[],
        ),
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("clean output should not be re-encoded")

    monkeypatch.setattr(mod, "_repair_stream", fail_if_called)

    result = mod.repair_render_output(
        rendered,
        tmp_path / "repaired.mp4",
        source_baseline={
            "black_frames": [{
                "start_sec": 0.0, "end_sec": 4.0, "duration_sec": 4.0,
            }],
        },
    )

    assert result["ok"] is True
    assert result["changed"] is False
    assert result["output_path"] == str(rendered)


def test_render_repair_short_circuits_without_source_baseline_spans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered = tmp_path / "rendered.mp4"
    rendered.write_bytes(b"rendered")

    def fail_if_detected(*args, **kwargs):
        raise AssertionError("detectors should not run without source spans")

    monkeypatch.setattr(mod, "list_black_frames", fail_if_detected)
    monkeypatch.setattr(mod, "list_frozen_frames", fail_if_detected)

    result = mod.repair_render_output(
        rendered,
        tmp_path / "repaired.mp4",
        source_baseline={"source_hashes": {"asset-1": "hash"}},
    )

    assert result["ok"] is True
    assert result["changed"] is False
    assert result["reason"] == "no_source_baseline_spans"
    assert result["output_path"] == str(rendered)


def test_source_repair_helpers_never_mutate_source_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"immutable source bytes")
    before = hashlib.sha256(source.read_bytes()).hexdigest()

    mod.repair_frame_sequence(
        [b"\x00\x00\x00", b"\xff\x00\x00"],
        fps=30.0,
        black_spans=[],
        frozen_spans=[],
    )

    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg/ffprobe not installed",
)
def test_render_repair_leaves_unlisted_spans_configurable(tmp_path: Path) -> None:
    """Render-only repair should not rewrite spans without source intent."""
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i",
            (
                "color=c=red:s=32x32:d=0.5[r];"
                "color=c=black:s=32x32:d=0.5[b];"
                "color=c=blue:s=32x32:d=0.5[bl];"
                "color=c=green:s=32x32:d=1.0[g];"
                "[r][b][bl][g]concat=n=4:v=1:a=0"
            ),
            "-r", "10", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(source),
        ],
        check=True,
    )

    result = mod.repair_render_output(
        source, tmp_path / "untouched.mp4", source_baseline={},
    )

    assert result["ok"] is True, result
    assert result["changed"] is False
    assert result["output_path"] == str(source)
    assert not (tmp_path / "untouched.mp4").exists()


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg/ffprobe not installed",
)
def test_render_only_repair_rewrites_output_not_source(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i",
            (
                "color=c=red:s=32x32:d=0.5[r];"
                "color=c=black:s=32x32:d=0.5[b];"
                "color=c=blue:s=32x32:d=0.5[bl];"
                "color=c=green:s=32x32:d=1.0[g];"
                "color=c=yellow:s=32x32:d=0.5[y];"
                "[r][b][bl][g][y]concat=n=5:v=1:a=0"
            ),
            "-r", "10", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(source),
        ],
        check=True,
    )
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    output = tmp_path / "repaired.mp4"

    result = mod.repair_render_output(
        source, output,
        source_baseline={
            "source_hashes": {"source": before},
            "black_frames": [{"start_sec": 0.5, "end_sec": 1.0}],
            "frozen_frames": [{"start_sec": 1.5, "end_sec": 2.5}],
        },
    )

    assert result["ok"] is True, result
    assert result["changed"] is True
    assert output.is_file()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert not mod.list_black_frames(str(output)).spans
