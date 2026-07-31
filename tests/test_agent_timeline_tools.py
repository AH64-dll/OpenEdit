"""Functional coverage for the seven TOOL_TABLE timeline operations."""
from __future__ import annotations

from pathlib import Path

from open_edit.agent.tools.pyagent_timeline_ops import (
    add_clip,
    apply_silence_gaps,
    change_clip_speed,
    remove_clip,
    replace_clip_source,
    set_audio_gain,
    trim_clip,
)
from open_edit.agent.tools._helpers import load_project
from open_edit.ir.derive import derive_timeline
from open_edit.ir.types import (
    AddClipOp,
    ChangeClipSpeedOp,
    RemoveClipOp,
    ReplaceClipSourceOp,
    SetAudioGainOp,
    TrimClipOp,
)
from open_edit.storage.edit_graph import EditGraphStore


def _db(project: Path) -> EditGraphStore:
    return EditGraphStore(project / ".open_edit" / "edit_graph.db")


def _add(project: Path, *, out: float = 10.0) -> str:
    result = add_clip(
        {"asset_hash": "asset-a", "out_point_sec": out, "project_id": "p"},
        str(project),
    )
    assert result["status"] == "ok", result
    return result["clip_id"]


def test_timeline_tools_append_ops_and_reload(tmp_path: Path) -> None:
    clip_id = _add(tmp_path)
    assert trim_clip(
        {"clip_id": clip_id, "in_point_sec": 1, "out_point_sec": 8},
        str(tmp_path),
    )["status"] == "ok"
    assert replace_clip_source(
        {"clip_id": clip_id, "new_asset_hash": "asset-b"}, str(tmp_path)
    )["status"] == "ok"
    assert change_clip_speed(
        {"clip_id": clip_id, "rate": 1.5}, str(tmp_path)
    )["status"] == "ok"
    assert set_audio_gain(
        {"clip_id": clip_id, "gain_db": -6}, str(tmp_path)
    )["status"] == "ok"

    ops = _db(tmp_path).load_all()
    assert isinstance(ops[0], AddClipOp)
    assert any(isinstance(op, TrimClipOp) for op in ops)
    assert any(isinstance(op, ReplaceClipSourceOp) for op in ops)
    assert any(isinstance(op, ChangeClipSpeedOp) for op in ops)
    assert any(isinstance(op, SetAudioGainOp) for op in ops)
    assert derive_timeline(load_project(tmp_path)).tracks


def test_remove_clip_persists_and_disappears_from_derived_timeline(tmp_path: Path) -> None:
    clip_id = _add(tmp_path)
    result = remove_clip({"clip_id": clip_id}, str(tmp_path))
    assert result["status"] == "ok"
    assert any(isinstance(op, RemoveClipOp) for op in _db(tmp_path).load_all())
    timeline = derive_timeline(load_project(tmp_path))
    assert all(c.clip_id != clip_id for track in timeline.tracks for c in track.clips)


def test_apply_silence_gaps_replaces_clip_with_keep_segments(tmp_path: Path) -> None:
    clip_id = _add(tmp_path, out=10.0)
    result = apply_silence_gaps(
        {"clip_id": clip_id, "gaps": [[2.0, 4.0], [7.0, 8.0]]},
        str(tmp_path),
    )
    assert result["status"] == "ok", result
    assert result["keep_count"] == 3
    ops = _db(tmp_path).load_all()
    assert sum(isinstance(op, RemoveClipOp) for op in ops) == 1
    assert len(result["new_clip_ids"]) == 3
    timeline = derive_timeline(load_project(tmp_path))
    clips = [c for track in timeline.tracks for c in track.clips]
    assert clip_id not in {c.clip_id for c in clips}
    assert {c.clip_id for c in clips} == set(result["new_clip_ids"])
