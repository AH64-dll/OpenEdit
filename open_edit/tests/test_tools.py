"""Tests for all 13 agent tools + 1 virtual tool."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from open_edit.agent.tools import (
    add_marker,
    analyze_narrative,
    generate_visual_for_segment,
    get_pending_notes,
    get_style_profile,
    import_asset,
    list_assets,
    place_sfx,
    propose_silence_cuts,
    run_python,
    search_assets,
    select_music,
    set_pinned_value,
)
from open_edit.serve.tool_executor import (
    ToolNotFound,
    execute_tool,
    execute_trigger_render,
)


# ============================================================================
# add_marker
# ============================================================================

def test_add_marker_happy_path(tmp_path: Path):
    args = {"project_id": "proj-1", "t_start": 10.0, "t_end": 12.0, "text": "check this"}
    result = add_marker(args, str(tmp_path))
    assert result["status"] == "ok"
    assert "note_id" in result


def test_add_marker_missing_project_id(tmp_path: Path):
    args = {"t_start": 10.0}
    result = add_marker(args, str(tmp_path))
    assert result["status"] == "error"


def test_add_marker_missing_t_start(tmp_path: Path):
    args = {"project_id": "proj-1"}
    result = add_marker(args, str(tmp_path))
    assert result["status"] == "error"


# ============================================================================
# analyze_narrative
# ============================================================================

def test_analyze_narrative_missing_asset_hash(tmp_path: Path):
    result = analyze_narrative({}, str(tmp_path))
    assert result["status"] == "error"
    assert "asset_hash" in result["error"]


def test_analyze_narrative_asset_not_found(tmp_path: Path):
    args = {"asset_hash": "nonexistent"}
    result = analyze_narrative(args, str(tmp_path))
    assert result["status"] == "error"
    assert "not found" in result["error"]


# ============================================================================
# generate_visual_for_segment
# ============================================================================

def test_generate_visual_for_segment_missing_asset_hash(tmp_path: Path):
    result = generate_visual_for_segment({}, str(tmp_path))
    assert result["status"] == "error"


def test_generate_visual_for_segment_asset_not_found(tmp_path: Path):
    args = {"asset_hash": "nonexistent", "beat_type": "hook", "template": "title_card", "project_id": "p1"}
    result = generate_visual_for_segment(args, str(tmp_path))
    assert result["status"] == "error"
    assert "not found" in result["error"]


# ============================================================================
# get_pending_notes
# ============================================================================

def test_get_pending_notes_happy_path(tmp_path: Path):
    args = {"project_id": "proj-1"}
    result = get_pending_notes(args, str(tmp_path))
    assert "notes" in result


def test_get_pending_notes_summary_only(tmp_path: Path):
    args = {"project_id": "proj-1", "summary_only": True}
    result = get_pending_notes(args, str(tmp_path))
    assert "notes" in result


def test_get_pending_notes_missing_project_id(tmp_path: Path):
    result = get_pending_notes({}, str(tmp_path))
    assert result["status"] == "error"


# ============================================================================
# get_style_profile
# ============================================================================

def test_get_style_profile_happy_path(tmp_path: Path):
    with mock.patch("open_edit.style.retrieve.get_slice", return_value={"corrections": {}}):
        result = get_style_profile({"op_type": "AddClipOp"}, str(tmp_path))
        assert isinstance(result, dict)


def test_get_style_profile_missing_op_type(tmp_path: Path):
    result = get_style_profile({}, str(tmp_path))
    assert result["status"] == "error"


# ============================================================================
# place_sfx
# ============================================================================

def test_place_sfx_missing_asset_hash(tmp_path: Path):
    result = place_sfx({}, str(tmp_path))
    assert result["status"] == "error"


def test_place_sfx_asset_not_found(tmp_path: Path):
    args = {"asset_hash": "nonexistent"}
    result = place_sfx(args, str(tmp_path))
    assert result["status"] == "error"
    assert "not found" in result["error"]


# ============================================================================
# propose_silence_cuts
# ============================================================================

def test_propose_silence_cuts_missing_asset_hash(tmp_path: Path):
    result = propose_silence_cuts({}, str(tmp_path))
    assert result["status"] == "error"


def test_propose_silence_cuts_asset_not_found(tmp_path: Path):
    args = {"asset_hash": "nonexistent"}
    result = propose_silence_cuts(args, str(tmp_path))
    assert result["status"] == "error"
    assert "not found" in result["error"]


# ============================================================================
# run_python
# ============================================================================

def test_run_python_missing_code(tmp_path: Path):
    result = run_python({}, str(tmp_path))
    assert result["status"] == "error"


def test_run_python_missing_project_id(tmp_path: Path):
    result = run_python({"code": "pass"}, str(tmp_path))
    assert result["status"] == "error"


def test_run_python_happy_path(tmp_path: Path):
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()

    captured = {}

    def fake_run_free_form(**kwargs):
        captured.update(kwargs)
        from open_edit.agent.exceptions import FreeFormResult
        return FreeFormResult.ok(ops=[], duration_s=0.0)

    args = {
        "code": "# ir_api_version: 0.1; libs: {}\npass\n",
        "project_id": "p1",
    }
    with mock.patch(
        "open_edit.agent.tools.pyagent_run_python.run_free_form",
        side_effect=fake_run_free_form,
    ):
        result = run_python(args, project_path=str(workdir))

    assert result["status"] == "ok"


# ============================================================================
# search_assets
# ============================================================================

def test_search_assets_missing_query(tmp_path: Path):
    result = search_assets({"kind": "video"}, str(tmp_path))
    assert "error" in result
    assert "query" in result["error"]


def test_search_assets_invalid_kind(tmp_path: Path):
    result = search_assets({"query": "test", "kind": "invalid"}, str(tmp_path))
    assert "error" in result
    assert "kind" in result["error"]


def test_search_assets_happy_path(tmp_path: Path):
    with mock.patch(
        "open_edit.agent.tools.pyagent_search_assets._pexels_api_key",
        return_value="test-key",
    ), mock.patch(
        "open_edit.agent.tools.pyagent_search_assets._http_get_json",
        return_value={"videos": []},
    ):
        result = search_assets({"query": "test", "kind": "video"}, str(tmp_path))
        assert "results" in result


# ============================================================================
# select_music
# ============================================================================

def test_select_music_missing_asset_hash(tmp_path: Path):
    result = select_music({}, str(tmp_path))
    assert result["status"] == "error"


def test_select_music_asset_not_found(tmp_path: Path):
    args = {"asset_hash": "nonexistent"}
    result = select_music(args, str(tmp_path))
    assert result["status"] == "error"
    assert "not found" in result["error"]


# ============================================================================
# set_pinned_value
# ============================================================================

def test_set_pinned_value_happy_path(tmp_path: Path):
    with mock.patch("open_edit.agent.tools.pyagent_set_pinned_value.set_pinned") as m:
        result = set_pinned_value({"key": "test_key", "value": "test_val"}, str(tmp_path))
        assert result["status"] == "ok"
        m.assert_called_once_with("test_key", "test_val")


def test_set_pinned_value_missing_key(tmp_path: Path):
    result = set_pinned_value({"value": "test_val"}, str(tmp_path))
    assert result["status"] == "error"


# ============================================================================
# import_asset
# ============================================================================

def test_import_asset_missing_both_args(tmp_path: Path):
    result = import_asset({"project_id": "x"}, str(tmp_path))
    assert "error" in result
    assert "result_id" in result["error"] or "source_url" in result["error"]


def test_import_asset_non_https_url(tmp_path: Path):
    result = import_asset({"source_url": "http://example.com/x.mp4", "project_id": "x"}, str(tmp_path))
    assert "error" in result
    assert "https" in result["error"].lower()


def test_import_asset_unknown_result_id(tmp_path: Path):
    from open_edit.agent.tools import pyagent_import_asset as mod

    cache = tmp_path / "empty_cache"
    with mock.patch.object(mod, "_SEARCH_RESULT_CACHE_DIR", cache):
        result = import_asset({"result_id": "nonexistent", "project_id": "x"}, str(tmp_path))
    assert "error" in result
    assert "not found" in result["error"].lower()


# ============================================================================
# list_assets
# ============================================================================

def test_list_assets_empty_project(tmp_path: Path):
    result = list_assets({}, str(tmp_path))
    assert result == {"assets": []}


def test_list_assets_with_assets(tmp_path: Path):
    assets_root = tmp_path / ".open_edit" / "assets" / "ab"
    assets_root.mkdir(parents=True)
    sidecar = {
        "asset_hash": "abc123",
        "original_path": "/tmp/clip.mp4",
        "duration_sec": 42.5,
        "type": "video",
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "codec": "h264",
        "has_audio": True,
    }
    (assets_root / "abc123.meta.json").write_text(json.dumps(sidecar))
    result = list_assets({}, str(tmp_path))
    assert len(result["assets"]) == 1
    assert result["assets"][0]["hash"] == "abc123"


# ============================================================================
# execute_tool
# ============================================================================

def test_execute_tool_dispatches_to_module(tmp_path: Path):
    result = execute_tool(name="list_assets", args={}, project_path=tmp_path)
    assert isinstance(result, dict)
    assert "assets" in result


def test_execute_tool_unknown_raises(tmp_path: Path):
    with pytest.raises(ToolNotFound) as exc:
        execute_tool(name="definitely_not_a_tool", args={}, project_path=tmp_path)
    assert "definitely_not_a_tool" in str(exc.value)


# ============================================================================
# execute_trigger_render
# ============================================================================

@pytest.mark.asyncio
async def test_execute_trigger_render_subprocess_fails(tmp_path: Path):
    proc = mock.AsyncMock()
    proc.returncode = 1
    proc.communicate.return_value = (b"", b"boom")
    with mock.patch("asyncio.create_subprocess_exec", return_value=proc), \
         pytest.raises((ValueError, KeyError, RuntimeError)) as exc:
        await execute_trigger_render(args={}, project_path=tmp_path)
    assert "open_edit render" in str(exc.value)


@pytest.mark.asyncio
async def test_execute_trigger_render_missing_args_defaults_to_proxy(tmp_path: Path):
    proc = mock.AsyncMock()
    proc.returncode = 0
    proc.communicate.return_value = (b"/tmp/output.mp4\n", b"")
    with mock.patch("asyncio.create_subprocess_exec", return_value=proc), \
         mock.patch("open_edit.serve.tool_executor._probe_duration", return_value=5.0):
        result = await execute_trigger_render(args={}, project_path=tmp_path)
    assert result["mode"] == "proxy"
    assert result["render_id"].startswith("render_")
