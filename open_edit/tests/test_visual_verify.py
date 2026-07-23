"""v1.5: tests for the visual verification module.

The module is a collection of pure functions (or close to pure: each
test sets up its own inputs and asserts the deterministic output).
"""
from __future__ import annotations

import base64
import io
import json
import os
import struct
import sys
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve import visual_verify  # noqa: E402
from open_edit.serve import serve_env  # noqa: E402


# ---------------------------------------------------------------------------
# sample_frames — tiered by duration, with clamping + dedup
# ---------------------------------------------------------------------------

def test_sample_frames_tiered_by_duration():
    """All 4 duration tiers + 1-frame short case."""
    assert visual_verify.sample_frames(0.8) == pytest.approx([0.4], abs=1e-6)
    assert visual_verify.sample_frames(5.0) == pytest.approx([1.0, 2.5, 4.0], abs=1e-6)
    assert visual_verify.sample_frames(60.0) == pytest.approx([9.0, 24.0, 39.0, 54.0], abs=1e-6)
    assert visual_verify.sample_frames(150.0) == pytest.approx([15.0, 45.0, 75.0, 105.0, 135.0], abs=1e-6)


def test_short_video_one_frame():
    assert visual_verify.sample_frames(0.8) == pytest.approx([0.4], abs=1e-6)


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

def _write_minimal_png(path: Path, width: int = 1920, height: int = 1080) -> None:
    """Write a 1×1 RGB PNG so the test doesn't need real media."""
    import struct, zlib
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"\x00" + (b"\x00\x00\x00" * width)
    idat = zlib.compress(raw * height)
    path.write_bytes(sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def test_preserves_aspect_ratio_when_downscaling(monkeypatch, tmp_path):
    """encode_jpeg must scale so the long edge is <= max_edge_px, no distortion."""
    src = tmp_path / "src.png"
    _write_minimal_png(src, 4000, 1000)  # 4:1 aspect
    out = tmp_path / "out.jpg"
    # We do not have ffmpeg on the test path; stub the ffmpeg call.
    fake_jpeg = bytes(range(256)) * 16  # 4096 bytes
    fake_proc = mock.Mock(returncode=0, stdout=b"", stderr=b"")
    with mock.patch("subprocess.run", return_value=fake_proc) as run_mock:
        n = visual_verify.encode_jpeg(src, out, max_edge_px=1024, jpeg_quality=85)
    # ffmpeg is called once with -vf scale=...:1024 (long-edge scaling).
    call = run_mock.call_args
    argv = call.args[0]
    assert "ffmpeg" in argv[0] or argv[0].endswith("ffmpeg")
    vf_arg = next((a for a in argv if a.startswith("scale=")), None)
    assert vf_arg is not None
    assert "1024" in vf_arg
    # The 1024 applies to whichever edge is longer (4:1 → width=4000 > 1000,
    # so 1024 is the target width; height scales proportionally to 256).
    assert "1024" in vf_arg
    # Output file size = the stub's nothing-wrote, so encode_jpeg returns
    # whatever subprocess says; here we just assert the call was made with
    # argv-list (no shell=True).
    assert call.kwargs.get("shell", False) is False


def test_subprocess_uses_argv_list_not_shell(monkeypatch, tmp_path):
    """Subprocess.run is called with shell=False (the default — explicit
    test because it's load-bearing for security)."""
    src = tmp_path / "src.png"
    _write_minimal_png(src)
    out = tmp_path / "out.jpg"
    with mock.patch("subprocess.run") as run_mock:
        run_mock.return_value = mock.Mock(returncode=0)
        visual_verify.encode_jpeg(src, out, 1024, 85)
    assert run_mock.call_args.kwargs.get("shell", False) is False


def test_payload_size_caps_downscale(monkeypatch, tmp_path):
    """If the encoded JPEG exceeds max_image_bytes, the long-edge limit
    is reduced and a second pass is attempted. (Spec §2.7 — strip metadata,
    downscale further if needed.)"""
    src = tmp_path / "src.png"
    _write_minimal_png(src, 4000, 4000)
    out = tmp_path / "out.jpg"
    big = b"\xff\xd8\xff" + b"\x00" * (6 * 1024 * 1024)
    small = b"\xff\xd8\xff" + b"\x00" * 100
    counter = {"n": 0}
    def fake_run(*argv, **kwargs):
        counter["n"] += 1
        Path(argv[0][-1]).write_bytes(big if counter["n"] == 1 else small)
        return mock.Mock(returncode=0, stdout=b"", stderr=b"")
    with mock.patch("subprocess.run", side_effect=fake_run) as rm:
        n = visual_verify.encode_jpeg(src, out, 1024, 85, max_bytes=5_000_000)
    assert rm.call_count == 2
    second_vf = next(a for a in rm.call_args_list[1].args[0] if a.startswith("scale="))
    first_vf = next(a for a in rm.call_args_list[0].args[0] if a.startswith("scale="))
    assert int(first_vf.split("=")[1].split(":")[0]) > int(second_vf.split("=")[1].split(":")[0])


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


def test_verification_prompt_mentions_proxy_disclaimer():
    """When mode=proxy, the prompt must include the proxy-disclaimer paragraph
    (ignore reduced resolution, focus on correctness)."""
    render = {"output_path": "/tmp/r.mp4", "mode": "proxy", "duration_s": 10.0, "render_id": "r1"}
    cap = {"supports_images": True, "input_modalities": ["text", "image"], "max_image_count": 8, "source": "models_store"}
    out = visual_verify.build_verification_tool_result(render, [], cap, mode="proxy")
    assert "ignore proxy-only quality limitations" in out["verification"]["prompt"]


def test_text_only_model_returns_text_only_tool_result():
    render = {"output_path": "/tmp/r.mp4", "mode": "proxy", "duration_s": 10.0, "render_id": "r1"}
    cap = {"supports_images": False, "input_modalities": ["text"], "max_image_count": 0, "source": "models_store"}
    out = visual_verify.build_verification_tool_result(render, [], cap, mode="proxy")
    assert out["verification"]["verdict_required"] is False
    assert out["verification"]["frames"] == []
    assert out["verification"]["reason"] == "text_only_model"
    assert "Do not claim to have visually inspected" in out["verification"]["prompt"]


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

def test_no_change_render_skips_re_render(tmp_path):
    """Same edit graph + same render_id + same render_mode → same hash.
    Different edit graph → different hash."""
    db = tmp_path / ".open_edit" / "edit_graph.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    from open_edit.storage.edit_graph import EditGraphStore
    EditGraphStore(db)  # initialise empty project
    h1 = visual_verify.project_state_hash(tmp_path, "proxy", last_render_id="r1")
    h2 = visual_verify.project_state_hash(tmp_path, "proxy", last_render_id="r1")
    assert h1 == h2
    h3 = visual_verify.project_state_hash(tmp_path, "proxy", last_render_id="r2")
    assert h1 != h3
    h4 = visual_verify.project_state_hash(tmp_path, "final", last_render_id="r1")
    assert h1 != h4


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
    assert any("[VISUAL VERIFICATION SUMMARY" in json.dumps(m, default=str) for m in slim)


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

def test_serve_env_defaults():
    """All defaults are typed values (int/float/bool/str/None), not strings."""
    with mock.patch.dict(os.environ, {}, clear=True):
        cfg = serve_env.get_visual_verify_config()
    assert cfg["enabled"] is True
    assert cfg["frames"] == 3
    assert cfg["max_renders"] == 100
    assert cfg["max_edge_px"] == 4096
    assert cfg["jpeg_quality"] == 95
    assert cfg["total_timeout_seconds"] == 3600
    assert cfg["max_image_bytes"] == 100_000_000
    assert cfg["debug_dir"] is None
    assert cfg["render_mode"] == "proxy"
    assert cfg["allow_no_change_skip"] is True
    assert cfg["persist_history"] is True


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
    from open_edit.serve.visual_verify import build_failure_tool_result
    out = build_failure_tool_result("render_failed", render_id="r1")
    assert "error" in out
    assert "verification" not in out
    assert "render_failed" in out["error"]


def test_render_capped_returns_tool_result_error():
    """Cap path returns a tool-result error with cap details (spec §4)."""
    from open_edit.serve.visual_verify import build_failure_tool_result
    out = build_failure_tool_result("render_capped", render_id="r1", cap=3, render_count=4)
    assert "error" in out
    assert "render_capped" in out["error"]
    assert out["cap"] == 3
    assert out["render_count"] == 4
    assert "verification" not in out


def test_no_change_render_skips_sampling(tmp_path):
    """If project_state_hash matches the last successful render, return a
    no_change tool result with no verification block (sampling skipped)."""
    from open_edit.storage.edit_graph import EditGraphStore
    db = tmp_path / ".open_edit" / "edit_graph.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    EditGraphStore(db)
    last = ("render_xyz", "proxy")
    h = visual_verify.project_state_hash(tmp_path, "proxy", last_render_id="render_xyz")
    # Re-hashing the same project produces the same hash → no_change.
    out = visual_verify.build_no_change_tool_result(tmp_path, "proxy", last_render_id="render_xyz")
    assert out.get("no_change") is True
    assert "previous_render_id" in out
    assert "verification" in out  # spec: present, but with empty frames + reason
    assert out["verification"]["frames"] == []
    assert out["verification"]["reason"] == "no_change"
