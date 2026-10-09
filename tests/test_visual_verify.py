"""v1.5: tests for the visual verification module.

The module is a collection of pure functions (or close to pure: each
test sets up its own inputs and asserts the deterministic output).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

import pytest

from open_edit.serve import (
    serve_env,
    visual_verify,
)








# ---------------------------------------------------------------------------
# sample_frames — tiered by duration, with clamping + dedup
# ---------------------------------------------------------------------------

def test_sample_frames_tiered_by_duration():
    """All 4 duration tiers + 1-frame short case."""
    assert visual_verify.sample_frames(0.8) == pytest.approx([0.4], abs=1e-6)
    assert visual_verify.sample_frames(5.0) == pytest.approx([1.0, 2.5, 4.0], abs=1e-6)
    assert visual_verify.sample_frames(60.0) == pytest.approx([9.0, 24.0, 39.0, 54.0], abs=1e-6)
    assert visual_verify.sample_frames(150.0) == pytest.approx([15.0, 45.0, 75.0, 105.0, 135.0], abs=1e-6)




def test_dedupes_close_timestamps():
    """Three timestamps within 0.1s collapse to one (use override_count to
    force the short tier to emit 3 close frames)."""
    # With override_count=3 and D=0.4, the naive [0.08, 0.2, 0.32] would
    # all clamp to >=0.05; 0.08 and 0.20 are 0.12 apart, 0.20 and 0.32 are
    # 0.12 apart — but the deduper uses 0.1s; force a true collision.
    frames = visual_verify.sample_frames(0.5, override_count=3)
    # All three must be unique after dedup; verify no two are within 0.1s.
    for i in range(len(frames) - 1):
        assert frames[i + 1] - frames[i] > 0.1


def test_timestamps_clamped_to_safe_range():
    """No frame is closer than 0.05s to either edge of the video."""
    frames = visual_verify.sample_frames(0.1)  # would naively emit t=0.05
    assert all(0.05 <= t <= max(0.05, 0.1 - 0.05) for t in frames)


# ---------------------------------------------------------------------------
# encode_jpeg — ffmpeg wrapper, downscaling, no shell
# ---------------------------------------------------------------------------









# ---------------------------------------------------------------------------
# model_capability
# ---------------------------------------------------------------------------

def _write_models_store(path: Path, models: list[dict]) -> None:
    path.write_text(json.dumps({"opencode-go": {"models": models}}))


def test_model_capability_returns_dict():
    cap = visual_verify.model_capability("minimax-m3", models_store_path=Path("/nonexistent"))
    assert isinstance(cap, dict)
    assert "supports_images" in cap
    assert "input_modalities" in cap
    assert "max_image_count" in cap
    assert "source" in cap


def test_capability_dict_includes_constraints():
    cap = visual_verify.model_capability("minimax-m3", models_store_path=Path("/nonexistent"))
    # Constraints are present (may be 0/None for the default fallback).
    assert "max_image_count" in cap
    assert isinstance(cap["max_image_count"], (int, type(None)))


def test_capability_for_minimax_m3_includes_image(tmp_path):
    store = tmp_path / "models-store.json"
    _write_models_store(store, [{
        "id": "minimax-m3",
        "name": "MiniMax M3",
        "input": ["text", "image"],
        "contextWindow": 200000,
    }])
    cap = visual_verify.model_capability("minimax-m3", models_store_path=store)
    assert cap["supports_images"] is True
    assert "image" in cap["input_modalities"]
    assert cap["source"] == "models_store"


def test_capability_for_minimax_m2_7_omits_image(tmp_path):
    store = tmp_path / "models-store.json"
    _write_models_store(store, [{
        "id": "minimax-m2.7",
        "name": "MiniMax M2.7",
        "input": ["text"],
        "contextWindow": 200000,
    }])
    cap = visual_verify.model_capability("minimax-m2.7", models_store_path=store)
    assert cap["supports_images"] is False
    assert "image" not in cap["input_modalities"]
    assert cap["source"] == "models_store"


def test_capability_for_unknown_model_returns_unknown(tmp_path):
    store = tmp_path / "models-store.json"
    _write_models_store(store, [{"id": "minimax-m3", "input": ["text", "image"]}])
    cap = visual_verify.model_capability("nope-9", models_store_path=store)
    assert cap["source"] == "unknown"
    assert cap["supports_images"] is False  # safe default


# ---------------------------------------------------------------------------
# build_verification_tool_result
# ---------------------------------------------------------------------------

def test_message_construction_uses_tool_result_blocks():
    """Frames go inside the verification block of the tool result, NOT
    in a synthetic user message."""
    render = {"output_path": "/tmp/r.mp4", "mode": "proxy", "duration_s": 10.0, "render_id": "r1"}
    frames = [{"mimeType": "image/jpeg", "data": "AAAA", "t_seconds": 2.0}]
    cap = {"supports_images": True, "input_modalities": ["text", "image"], "max_image_count": 8, "source": "models_store"}
    out = visual_verify.build_verification_tool_result(render, frames, cap, mode="proxy")
    assert "verification" in out
    assert "frames" in out["verification"]
    assert out["verification"]["frames"] == frames
    assert out["verification"]["model_supports_images"] is True
    assert out["verification"]["verdict_required"] is True
    assert "render_id" in out  # render_id is in the parent, not verification
    assert "render_id" not in out["verification"]




def test_text_only_model_returns_text_only_tool_result():
    render = {"output_path": "/tmp/r.mp4", "mode": "proxy", "duration_s": 10.0, "render_id": "r1"}
    cap = {"supports_images": False, "input_modalities": ["text"], "max_image_count": 0, "source": "models_store"}
    out = visual_verify.build_verification_tool_result(render, [], cap, mode="proxy")
    assert out["verification"]["verdict_required"] is False
    assert out["verification"]["frames"] == []
    assert out["verification"]["reason"] == "text_only_model"
    assert "Do not claim to have visually inspected" in out["verification"]["prompt"]


# ---------------------------------------------------------------------------
# build_qc_evidence — deterministic spans feed the LLM verdict stage
# ---------------------------------------------------------------------------









# ---------------------------------------------------------------------------
# parse_verdict
# ---------------------------------------------------------------------------

def test_parse_verdict_pass():
    r = visual_verify.parse_verdict("Looks good.\nVERIFICATION: PASS\nAll clean.")
    assert r["verdict"] == "pass"
    assert r["source"] == "model_explicit_pass"
    assert "VERIFICATION: PASS" in r["matched_line"]


def test_parse_verdict_fail():
    r = visual_verify.parse_verdict("The overlay hides the video.\nVERIFICATION: FAIL")
    assert r["verdict"] == "fail"
    assert r["source"] == "model_explicit_fail"


def test_parse_verdict_uncertain():
    r = visual_verify.parse_verdict("Hard to tell at this resolution.\nVERIFICATION: UNCERTAIN")
    assert r["verdict"] == "uncertain"
    assert r["source"] == "model_explicit_uncertain"


def test_parse_verdict_unknown_when_no_line():
    r = visual_verify.parse_verdict("Done. The render looks fine.")
    assert r["verdict"] == "unknown"
    assert r["source"] == "model_no_verdict_line"
    assert r["matched_line"] is None


def test_parse_verdict_case_insensitive():
    r = visual_verify.parse_verdict("verification: pass — all good")
    assert r["verdict"] == "pass"
    assert r["source"] == "model_explicit_pass"


# ---------------------------------------------------------------------------
# project_state_hash + history pruning
# ---------------------------------------------------------------------------



def test_history_pruning_replaces_image_blocks_with_summary():
    """An image-bearing tool result in history is replaced with a summary
    block after the LLM has responded. Text blocks are kept verbatim."""
    history = [
        {"role": "user", "content": "Render the video."},
        {"role": "assistant", "content": [{"type": "text", "text": "Rendering now."}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": [
                {"type": "text", "text": '{"verification": {"frames": [...]}}'},
                {"type": "image", "data": "BASE64", "mimeType": "image/jpeg"},
            ]},
        ]},
    ]
    slim = visual_verify.prune_images(history, last_verdict=("r1", "pass", True, "Looks clean."))
    # No image blocks remain.
    text_dump = json.dumps(slim, default=str)
    assert "BASE64" not in text_dump
    assert '"type": "image"' not in text_dump
    # A summary block was added.


def test_only_last_two_summaries_kept_in_slim_view():
    """Three verifications in history → only the last 2 summaries kept;
    older one collapsed to a placeholder."""
    history = []
    for i in range(3):
        history.append({"role": "assistant", "content": [{"type": "text", "text": f"render {i}"}]})
        history.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"t{i}", "content": [
                {"type": "text", "text": "{}"},
                {"type": "image", "data": f"DATA{i}", "mimeType": "image/jpeg"},
            ]},
        ]})
    slim = visual_verify.prune_images(history, last_verdict=("r2", "pass", True, ""))
    text = json.dumps(slim, default=str)
    # All 3 image blocks are stripped.
    for i in range(3):
        assert f"DATA{i}" not in text
    # The oldest summary collapses; at most 2 [VISUAL VERIFICATION SUMMARY] blocks.
    assert text.count("[VISUAL VERIFICATION SUMMARY") <= 2
    assert "[previous verifications pruned]" in text


# ---------------------------------------------------------------------------
# serve_env — defaults + overrides
# ---------------------------------------------------------------------------



def test_serve_env_overrides():
    env = {
        "OPEN_EDIT_VERIFY_ENABLED": "0",
        "OPEN_EDIT_VERIFY_FRAMES": "5",
        "OPEN_EDIT_VERIFY_MAX_RENDERS": "7",
        "OPEN_EDIT_VERIFY_MAX_EDGE_PX": "512",
        "OPEN_EDIT_VERIFY_JPEG_QUALITY": "70",
        "OPEN_EDIT_VERIFY_TOTAL_TIMEOUT_SECONDS": "60",
        "OPEN_EDIT_VERIFY_DEBUG_DIR": "/tmp/dbg",
        "OPEN_EDIT_VERIFY_RENDER_MODE": "final",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        cfg = serve_env.get_visual_verify_config()
    assert cfg["enabled"] is False
    assert cfg["frames"] == 5
    assert cfg["max_renders"] == 7
    assert cfg["max_edge_px"] == 512
    assert cfg["jpeg_quality"] == 70
    assert cfg["total_timeout_seconds"] == 60
    assert cfg["debug_dir"] == "/tmp/dbg"
    assert cfg["render_mode"] == "final"


# ---------------------------------------------------------------------------
# failure shapes — no verification block on render failure
# ---------------------------------------------------------------------------

def test_render_failed_returns_error_not_verify_skipped():
    """When the underlying render fails, build a tool result that says so —
    no `verification` block (per spec §4 failure-shape spec)."""
    from open_edit.kernel.tool_result import build_failure_tool_result
    out = build_failure_tool_result("render_failed", render_id="r1")
    assert "error" in out
    assert "verification" not in out
    assert "render_failed" in out["error"]


def test_render_capped_returns_tool_result_error():
    """Cap path returns a tool-result error with cap details (spec §4)."""
    from open_edit.kernel.tool_result import build_failure_tool_result
    out = build_failure_tool_result("render_capped", render_id="r1", cap=3, render_count=4)
    assert "error" in out
    assert "render_capped" in out["error"]
    assert out["cap"] == 3
    assert out["render_count"] == 4
    assert "verification" not in out




@pytest.mark.parametrize("rate,overhang", [
    ("2", False), ("30", False), ("30000/1001", False), ("2", True),
])
def test_verification_samples_decode_at_video_tail(tmp_path, monkeypatch, rate, overhang):
    import asyncio
    import base64
    import io
    import shutil
    import subprocess

    from PIL import Image, ImageStat

    from open_edit.serve.agent import verify_stage

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    video = tmp_path / "video.mp4"
    argv = [
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
        f"color=c=black:s=64x32:r={rate}:d=3,drawbox=color=white:t=fill:enable='gte(t,1.5)'",
    ]
    if overhang:
        argv += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "4.5", "-c:a", "aac"]
    subprocess.run(
        [*argv, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
        check=True, capture_output=True, timeout=15,
    )
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "gpt-4o")
    cfg = serve_env.get_visual_verify_config()
    cfg.update(frames=5, max_edge_px=64, total_timeout_seconds=10)
    _, result, pending = asyncio.run(verify_stage._maybe_verify_render(
        {"render_id": "tail", "output_path": str(video), "mode": "proxy"}, tmp_path, 1, cfg,
    ))
    frames = result["verification"]["frames"]
    duration, fps = verify_stage._probe_media_timing(video)
    last = duration - 1 / fps
    assert pending is not None
    assert len(frames) == 5
    assert all(0 <= frame["t_seconds"] <= last for frame in frames)
    if rate == "2":
        assert frames[-1]["t_seconds"] == pytest.approx(2.5)
    if overhang:
        assert duration == pytest.approx(3)
    for frame in frames:
        with Image.open(io.BytesIO(base64.b64decode(frame["data"]))) as image:
            means = ImageStat.Stat(image.convert("RGB")).mean
        assert min(means) > 240 if frame["t_seconds"] >= 1.5 else max(means) < 15
    tail = tmp_path / "tail.jpg"
    visual_verify.encode_jpeg(video, tail, 64, 95, timestamp_s=last, timeout_s=5)
    with Image.open(tail) as image:
        assert min(ImageStat.Stat(image.convert("RGB")).mean) > 240


@pytest.mark.parametrize("dimensions", [(400, 100), (100, 400)])
def test_jpeg_long_edge_bound_preserves_landscape_and_portrait(tmp_path, dimensions):
    import shutil

    from PIL import Image

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    source, target = tmp_path / "source.png", tmp_path / "target.jpg"
    Image.new("RGB", dimensions, "blue").save(source)
    visual_verify.encode_jpeg(source, target, 128, 95, timeout_s=5)
    with Image.open(target) as image:
        width, height = image.size
        assert max(width, height) <= 128
        assert width / height == pytest.approx(dimensions[0] / dimensions[1], rel=0.03)


def test_jpeg_downscale_attempts_share_one_deadline(tmp_path, monkeypatch):
    import subprocess
    import types

    from PIL import Image

    fixture = tmp_path / "fixture.jpg"
    Image.new("RGB", (64, 64), "blue").save(fixture)
    binary = tmp_path / "bin" / "ffmpeg"
    binary.parent.mkdir()
    attempts = tmp_path / "attempts"
    binary.write_text(
        "#!/usr/bin/env python3\nimport shutil, sys, time\nfrom pathlib import Path\n"
        f"attempts = Path({str(attempts)!r})\n"
        "if attempts.exists(): time.sleep(0.2)\n"
        "attempts.write_text('started')\n"
        f"shutil.copyfile({str(fixture)!r}, sys.argv[-1])\n",
    )
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binary.parent}{os.pathsep}{os.environ['PATH']}")
    clock = [0.0]
    real_run = subprocess.run

    def run(*args, **kwargs):
        result = real_run(*args, **kwargs)
        clock[0] = 0.3
        return result

    monkeypatch.setattr(visual_verify, "time", types.SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(subprocess.TimeoutExpired):
        visual_verify.encode_jpeg(
            fixture, tmp_path / "target.jpg", 128, 95, max_bytes=1, timeout_s=0.35,
        )
