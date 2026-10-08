"""Stable audio controls and emitted property contracts, with real MLT evidence."""

import array
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from lxml import etree

from open_edit.ir.derive import derive_timeline
from open_edit.ir.types import AddClipOp, Project
from open_edit.kernel.studio_service import commit_studio
from open_edit.render.emitter import EmitterConfig, emit_timeline
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


def seed(root):
    source = root / "tone.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:r=24:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=2",
            "-af",
            "pan=stereo|c0=c0|c1=c0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    asset = AssetStore(root / ".open_edit/assets").ingest(str(source), transcribe=False)
    store = EditGraphStore(root / ".open_edit/edit_graph.db")
    store.append(
        AddClipOp(
            author="user", clip_id="c", asset_hash=asset.asset_hash,
            track_id="v", position_sec=0, out_point_sec=2
        )
    )
    return store, asset


def test_track_keyframe_controls_validate_and_survive_history(tmp_path):
    store, _ = seed(tmp_path)
    commit_studio(
        tmp_path,
        expected_revision=store.graph_revision(),
        changes=[],
        ops=[
            {
                "kind": "add_effect",
                "target_kind": "track",
                "target_id": "v",
                "effect_type": "gain",
                "effect_id": "g",
                "params": {"gain": 0},
            },
            {
                "kind": "set_keyframe",
                "effect_id": "g",
                "param": "gain",
                "keyframes": [[0, 0, "linear"], [1, -6, "linear"]],
            },
        ],
    )
    def derive():
        return derive_timeline(Project(name="audio", edit_graph=store.load_all()))
    assert derive().tracks[0].effects[0].keyframes["gain"] == [
        (0.0, 0.0, "linear"),
        (1.0, -6.0, "linear"),
    ]
    before = store.graph_revision()
    for keys in (
        [[0, 0, "linear"], [0, 1, "linear"]],
        [[0, 99, "linear"]],
        [[0, 1, "unknown"]],
        [[3, 0, "linear"]],
    ):
        with pytest.raises(ValueError):
            commit_studio(
                tmp_path,
                expected_revision=before,
                changes=[],
                ops=[
                    {"kind": "set_keyframe", "effect_id": "g", "param": "gain", "keyframes": keys}
                ],
            )
    assert store.graph_revision() == before
    store.history_step("undo", before)
    assert not derive().tracks[0].effects
    store.history_step("redo", store.graph_revision())
    assert derive().tracks[0].effects[0].keyframes["gain"][-1][1] == -6


def test_audio_parameter_mapping_and_explicit_fade_ranges(tmp_path):
    store, _ = seed(tmp_path)
    commit_studio(
        tmp_path,
        expected_revision=store.graph_revision(),
        changes=[],
        ops=[
            {"kind": "trim_clip", "clip_id": "c", "new_in_point_sec": 0.5, "new_out_point_sec": 2},
            *[
                {
                    "kind": "add_effect",
                    "target_kind": "clip",
                    "target_id": "c",
                    "effect_type": kind,
                    "effect_id": kind,
                    "params": params,
                }
                for kind, params in [
                    ("panner", {"start": -1, "end": 1}),
                    ("eq", {"frequency": 440, "gain": -12, "bandwidth": 1}),
                    ("audio_fade_in", {"duration": 0.5}),
                    ("audio_fade_out", {"duration": 0.5}),
                ]
            ],
        ],
    )
    timeline = derive_timeline(Project(name="audio", edit_graph=store.load_all()))
    xml = etree.fromstring(
        emit_timeline(
            timeline,
            EmitterConfig(
                profile={"frame_rate_num": 24, "frame_rate_den": 1, "width": 320, "height": 180}
            ),
        ).encode()
    )

    def props(id):
        return {p.get("name"): p.text for p in xml.xpath(f'.//filter[@id="{id}"]/property')}

    assert props("panner") == {"channel": "-1", "start": "0.0", "end": "1.0"}
    assert props("eq")["av.frequency"] == "440" and props("eq")["av.gain"] == "-12"
    assert props("audio_fade_in")["level"] == "12=-80;24=0"
    assert props("audio_fade_out")["level"] == "12=0;36=0;48=-80"


@pytest.mark.browser
def test_actual_mlt_gain_fades_pan_and_eq(tmp_path, monkeypatch):
    if not shutil.which("melt"):
        pytest.skip("Actual MLT is required")
    store, asset = seed(tmp_path)
    base = derive_timeline(Project(name="audio", edit_graph=store.load_all()))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")

    def render(kind=None, params=None):
        timeline = base.model_copy(deep=True)
        if kind:
            from open_edit.ir.types import Effect

            timeline.tracks[0].clips[0].effects.append(
                Effect(effect_id="effect", effect_type=kind, params=params)
            )
        xml = tmp_path / f"{kind or 'base'}.mlt"
        xml.write_text(
            emit_timeline(
                timeline,
                EmitterConfig(
                    profile={"frame_rate_num": 24, "frame_rate_den": 1, "width": 320, "height": 180}
                ),
                {asset.asset_hash: asset.stored_path},
            )
        )
        out = tmp_path / f"{kind or 'base'}.wav"
        result = subprocess.run(
            [
                "melt",
                str(xml),
                "-consumer",
                f"avformat:{out}",
                "video_off=1",
                "f=wav",
                "acodec=pcm_s16le",
                "ar=48000",
                "ac=2",
                "real_time=-1",
            ],
            capture_output=True,
            timeout=60,
            env=os.environ,
        )
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        return out

    def rms(path, start=0.8, duration=0.15):
        data = subprocess.check_output(
            [
                "ffmpeg",
                "-v",
                "error",
                "-ss",
                str(start),
                "-t",
                str(duration),
                "-i",
                str(path),
                "-f",
                "f32le",
                "-ac",
                "2",
                "-",
            ]
        )
        samples = array.array("f", data)
        return [
            sum(v * v for v in samples[channel::2]) / max(1, len(samples) // 2)
            for channel in (0, 1)
        ]

    baseline = render()
    level = rms(baseline)[0]
    gain = rms(render("gain", {"gain": -6}))[0] / level
    assert 0.2 < gain < 0.3
    pan = rms(render("panner", {"start": -1, "end": -1}))
    assert pan[0] > 0.1 * level and pan[1] < 0.01 * pan[0]
    eq = rms(render("eq", {"frequency": 440, "gain": -12, "bandwidth": 1}))[0] / level
    assert eq < 0.15
    fade_in = render("audio_fade_in", {"duration": 0.5})
    assert rms(fade_in, 0.1)[0] < 0.1 * level and rms(fade_in, 0.8)[0] > 0.8 * level
    fade_out = render("audio_fade_out", {"duration": 0.5})
    assert rms(fade_out, 1.8)[0] < 0.1 * level and rms(fade_out, 0.8)[0] > 0.8 * level
    artifacts = Path("tests/browser/artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "studio-audio-controls.json").write_text(
        json.dumps(
            {"gain_power_ratio": gain, "pan_power": pan, "eq_power_ratio": eq, "fades_passed": True}
        )
    )
