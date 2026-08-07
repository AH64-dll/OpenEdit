"""Functional invocation coverage for every callable in ``TOOL_TABLE``.

The focused tool tests assert detailed behavior for each family.  This file
keeps the registry honest: every current table entry is invoked through the
same callable that kernel dispatch uses, with a meaningful success or domain
error asserted for that invocation.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from open_edit.agent.tools import TOOL_TABLE
from open_edit.agent.tools.pyagent_search_assets import _cache_clear
from open_edit.agent.exceptions import FreeFormResult
from open_edit.storage.edit_graph import EditGraphStore


EXPECTED_TOOL_NAMES = {
    "add_marker",
    "analyze_narrative",
    "capture_style_hint",
    "generate_remotion_composition",
    "generate_visual_for_segment",
    "get_pending_notes",
    "get_silence_gaps",
    "get_style_profile",
    "get_timeline_view",
    "get_transcript_packed",
    "import_asset",
    "ingest_local",
    "init_remotion_project",
    "list_assets",
    "place_sfx",
    "propose_silence_cuts",
    "run_python",
    "run_script",
    "search_assets",
    "select_music",
    "set_pinned_value",
    "write_remotion_composition",
    "add_clip",
    "add_hyperframes_overlay",
    "trim_clip",
    "replace_clip_source",
    "change_clip_speed",
    "remove_clip",
    "set_audio_gain",
    "apply_silence_gaps",
    "auto_color_grade",
}


def _graph(project: Path) -> EditGraphStore:
    """Create the real SQLite graph used by mutation-oriented tools."""
    return EditGraphStore(project / ".open_edit" / "edit_graph.db")


def _asset() -> SimpleNamespace:
    return SimpleNamespace(
        asset_hash="asset-a",
        alignment=[{"word": "hello"}],
        stored_path="/tmp/asset-a.mp4",
    )


def _segment() -> SimpleNamespace:
    return SimpleNamespace(
        beat_type="hook",
        model_dump=lambda: {"beat_type": "hook"},
    )


def _configure_style_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_dir = tmp_path / ".open-edit"
    config_dir.mkdir(parents=True, exist_ok=True)
    profile = config_dir / "style_profile.json"
    profile.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr("open_edit.style.aggregate.get_config_dir", lambda: config_dir)
    monkeypatch.setattr("open_edit.style.aggregate.get_profile_path", lambda: profile)
    monkeypatch.setattr("open_edit.style.retrieve.get_profile_path", lambda: profile)
    return profile


def test_tool_table_is_the_expected_27_callable_surface() -> None:
    assert set(TOOL_TABLE) == EXPECTED_TOOL_NAMES
    assert all(callable(fn) for fn in TOOL_TABLE.values())


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOL_NAMES))
def test_every_tool_table_callable_has_functional_invocation(
    name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invoke each registry entry through ``TOOL_TABLE[name]``.

    Expensive/network-backed engines are replaced at their narrow seam, while
    SQLite graph and notes mutations remain real wherever the wrapper owns
    persistence.
    """
    fn = TOOL_TABLE[name]
    project = tmp_path / "project"
    project.mkdir()

    if name == "add_marker":
        result = fn(
            {"project_id": "project-1", "t_start": 1.0, "text": "review"},
            str(project),
        )
        assert result["note_id"]

    elif name == "get_pending_notes":
        result = fn({"project_id": "project-1"}, str(project))
        assert result["notes"] == []

    elif name == "get_style_profile":
        _configure_style_profile(tmp_path, monkeypatch)
        result = fn({"op_type": "AddClipOp"}, str(project))
        assert isinstance(result["profile"], dict)

    elif name == "set_pinned_value":
        profile = _configure_style_profile(tmp_path, monkeypatch)
        result = fn({"key": "aspect_ratio", "value": "9:16"}, str(project))
        assert json.loads(profile.read_text(encoding="utf-8"))["pinned"]["aspect_ratio"] == "9:16"

    elif name == "capture_style_hint":
        profile = _configure_style_profile(tmp_path, monkeypatch)
        result = fn(
            {
                "hint": "prefer vertical framing",
                "category": "export",
                "key": "aspect_ratio",
                "value": "9:16",
                "confirmed": True,
            },
            str(project),
        )
        assert json.loads(profile.read_text(encoding="utf-8"))["hints"]

    elif name == "list_assets":
        result = fn({}, str(project))
        assert result["assets"] == []

    elif name == "ingest_local":
        media = project / "clip.mp4"
        media.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        asset = SimpleNamespace(
            asset_hash="abc123",
            duration_sec=1.0,
            type="video",
            has_audio=True,
            alignment=[],
        )
        store = MagicMock()
        store.ingest.return_value = asset
        with patch(
            "open_edit.agent.tools.pyagent_ingest_local.get_asset_store",
            return_value=store,
        ):
            result = fn(
                {"paths": [str(media)], "transcribe": False},
                str(project),
            )
        store.ingest.assert_called_once_with(str(media.resolve()), transcribe=False)

    elif name == "import_asset":
        cache = tmp_path / "search-cache"
        monkeypatch.setattr(
            "open_edit.agent.tools.pyagent_import_asset._SEARCH_RESULT_CACHE_DIR",
            cache,
        )
        result = fn(
            {"result_id": "missing-search-result", "project_id": "project-1"},
            str(project),
        )
        assert "missing-search-result" in result["error"]

    elif name == "search_assets":
        monkeypatch.delenv("OPEN_EDIT_PEXELS_API_KEY", raising=False)
        monkeypatch.delenv("OPEN_EDIT_FREESOUND_API_KEY", raising=False)
        monkeypatch.delenv("OPEN_EDIT_OPENVERSE_API_KEY", raising=False)
        _cache_clear()
        with patch(
            "open_edit.agent.tools.pyagent_search_assets._http_get_json",
            return_value={"results": []},
        ):
            result = fn(
                    {
                        "query": "rain",
                        "kind": "video",
                        "license": "cc0",
                        "limit": 1,
                    },
                str(project),
            )
        _cache_clear()
        assert result["source"] == "openverse"

    elif name in {"run_python", "run_script"}:
        _graph(project)
        with patch(
            "open_edit.agent.tools.pyagent_run_python.run_free_form",
            return_value=FreeFormResult.ok(ops=[], duration_s=0.0),
        ):
            result = fn({"code": "pass"}, str(project))
        assert result["ops_appended"] == 0

    elif name == "analyze_narrative":
        with (
            patch(
                "open_edit.agent.tools.pyagent_analyze_narrative.get_asset_or_error",
                return_value=(_asset(), None),
            ),
            patch(
                "open_edit.agent.skills.narrative_analyzer.analyze",
                return_value=[_segment()],
            ),
        ):
            result = fn({"asset_hash": "asset-a"}, str(project))
        assert result["segments"] == [{"beat_type": "hook"}]

    elif name == "get_transcript_packed":
        with (
            patch(
                "open_edit.agent.tools.pyagent_get_transcript_packed.get_asset_or_error",
                return_value=(_asset(), None),
            ),
            patch(
                "open_edit.agent.tools.pyagent_get_transcript_packed.pack_transcript",
                return_value="hello",
            ),
        ):
            result = fn({"asset_hash": "asset-a"}, str(project))
        assert result["transcript_packed"] == "hello"

    elif name == "propose_silence_cuts":
        with (
            patch(
                "open_edit.agent.tools.pyagent_propose_silence_cuts.get_asset_or_error",
                return_value=(_asset(), None),
            ),
            patch(
                "open_edit.agent.skills.silence_cutter.propose_cuts",
                return_value=[{"t_start": 1.0, "t_end": 2.0, "suggested_kind": "trim"}],
            ),
        ):
            result = fn({"asset_hash": "asset-a"}, str(project))
        assert result["gaps"][0]["t_start"] == 1.0

    elif name == "select_music":
        with (
            patch(
                "open_edit.agent.tools.pyagent_select_music.get_asset_or_error",
                return_value=(_asset(), None),
            ),
            patch(
                "open_edit.agent.skills.narrative_analyzer.analyze",
                return_value=[_segment()],
            ),
            patch(
                "open_edit.agent.skills.music_selector.select",
                return_value=[],
            ),
        ):
            result = fn({"asset_hash": "asset-a"}, str(project))
        assert result["ops"] == []

    elif name == "place_sfx":
        with (
            patch(
                "open_edit.agent.tools.pyagent_place_sfx.get_asset_or_error",
                return_value=(_asset(), None),
            ),
            patch(
                "open_edit.agent.skills.narrative_analyzer.analyze",
                return_value=[_segment()],
            ),
            patch(
                "open_edit.agent.skills.sfx_placer.place",
                return_value=[],
            ),
        ):
            result = fn({"asset_hash": "asset-a"}, str(project))
        assert result["ops"] == []

    elif name == "generate_visual_for_segment":
        operation = SimpleNamespace(model_dump=lambda: {"kind": "add_clip"})
        with (
            patch(
                "open_edit.agent.tools.pyagent_generate_visual_for_segment.get_asset_or_error",
                return_value=(_asset(), None),
            ),
            patch(
                "open_edit.agent.skills.narrative_analyzer.analyze",
                return_value=[_segment()],
            ),
            patch(
                "open_edit.agent.skills.motion_graphics.engine.generate_visual",
                return_value=operation,
            ),
        ):
            result = fn(
                {
                    "asset_hash": "asset-a",
                    "beat_type": "hook",
                    "template": "title_card",
                    "project_id": "project-1",
                },
                str(project),
            )
        assert result["op"] == {"kind": "add_clip"}

    elif name == "init_remotion_project":
        result = fn({}, str(project))
        assert Path(result["remotion_root"]).is_dir()

    elif name == "write_remotion_composition":
        fn_init = TOOL_TABLE["init_remotion_project"]
        fn_init({}, str(project))
        result = fn(
            {
                "relative_path": "src/compositions/Cover.tsx",
                "source": "export const Cover = () => null;\n",
            },
            str(project),
        )
        assert Path(result["path"]).is_file()

    elif name == "generate_remotion_composition":
        fn_init = TOOL_TABLE["init_remotion_project"]
        fn_init({}, str(project))
        _graph(project)
        result = fn(
            {
                "composition_id": "Cover",
                "entry_point": "src/index.ts",
                "duration_sec": 2,
                "props": {"text": "hello"},
            },
            str(project),
        )
        assert result["clip_id"]

    elif name == "add_hyperframes_overlay":
        template = project / "title.html"
        template.write_text("<div>title</div>", encoding="utf-8")
        _graph(project)
        result = fn(
            {
                "template_path": "title.html",
                "position_sec": 0.0,
                "duration_sec": 2.0,
            },
            str(project),
        )
        assert result["engine"] == "hyperframes"

    elif name == "add_clip":
        _graph(project)
        result = fn(
            {"asset_hash": "asset-a", "out_point_sec": 10.0},
            str(project),
        )
        assert result["clip_id"]

    elif name == "auto_color_grade":
        # graph exists but no clips -> structured error, wrapper callable
        _graph(project)
        result = fn({"preset": "auto"}, str(project))
        assert result["status"] == "error"

    elif name in {"get_silence_gaps", "get_timeline_view"}:
        # missing asset -> structured error, wrapper callable
        result = fn({"asset_hash": "missing"}, str(project))
        assert result["status"] == "error"

    elif name in {
        "trim_clip",
        "replace_clip_source",
        "change_clip_speed",
        "remove_clip",
        "set_audio_gain",
        "apply_silence_gaps",
    }:
        _graph(project)
        added = TOOL_TABLE["add_clip"](
            {"asset_hash": "asset-a", "out_point_sec": 10.0},
            str(project),
        )
        clip_id = added["clip_id"]
        if name == "trim_clip":
            result = fn(
                {"clip_id": clip_id, "in_point_sec": 1.0, "out_point_sec": 8.0},
                str(project),
            )
        elif name == "replace_clip_source":
            result = fn(
                {"clip_id": clip_id, "new_asset_hash": "asset-b"},
                str(project),
            )
        elif name == "change_clip_speed":
            result = fn({"clip_id": clip_id, "rate": 1.5}, str(project))
        elif name == "remove_clip":
            result = fn({"clip_id": clip_id}, str(project))
        elif name == "set_audio_gain":
            result = fn({"clip_id": clip_id, "gain_db": -6.0}, str(project))
        else:
            result = fn(
                {"clip_id": clip_id, "gaps": [[2.0, 4.0], [7.0, 8.0]]},
                str(project),
            )
        assert result["kind"] == name

    else:  # pragma: no cover - the exact registry assertion guards this
        pytest.fail(f"no functional invocation case for {name}")

    assert result["status"] == (
        "error"
        if name in ("import_asset", "auto_color_grade", "get_silence_gaps", "get_timeline_view")
        else "ok"
    ), result
