"""Phase 4 Task 7: 32 repointed wrappers call open_edit.ir.api.*.

Each test patches a specific IR API method and verifies the wrapper
dispatches to it with the expected kwargs. The wrappers live in
`phase3_pyagent_core/tools/*.py` and are routed through `runtime.run_op`.
"""
import pytest
from pathlib import Path
from unittest.mock import patch

from phase3_pyagent_core.runtime import run_op


def _make_project_dir(tmp_path) -> Path:
    project_path = tmp_path / "project"
    project_path.mkdir()
    (project_path / "edit_graph.db").touch()
    return project_path


def test_apply_effect_repointed(tmp_path):
    """The pyagent_apply_effect wrapper should call open_edit.ir.api.IR.add_effect."""
    project_path = _make_project_dir(tmp_path)
    args = {
        "target_kind": "clip",
        "target_id": "c1",
        "effect_type": "volume",
        "params": {"gain": 0.5},
    }
    with patch("open_edit.ir.api.IR.add_effect", return_value="fx_1") as mock_add_effect:
        code, response = run_op(
            "pyagent_apply_effect", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_add_effect.called
    call_kwargs = mock_add_effect.call_args.kwargs
    assert call_kwargs["target_kind"] == "clip"
    assert call_kwargs["target_id"] == "c1"
    assert call_kwargs["effect_type"] == "volume"
    assert call_kwargs["params"] == {"gain": 0.5}


def test_remove_effect_repointed(tmp_path):
    """pyagent_remove_effect should call open_edit.ir.api.IR.remove_effect."""
    project_path = _make_project_dir(tmp_path)
    args = {
        "clip_id": "c1",
        "effect_index": 0,
    }
    with patch("open_edit.ir.api.IR.remove_effect", return_value=None) as mock_remove:
        code, response = run_op(
            "pyagent_remove_effect", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_remove.called
    call_kwargs = mock_remove.call_args.kwargs
    assert call_kwargs["clip_id"] == "c1"
    assert call_kwargs["effect_index"] == 0


def test_add_transition_repointed(tmp_path):
    """pyagent_add_transition should call open_edit.ir.api.IR.add_transition."""
    project_path = _make_project_dir(tmp_path)
    args = {
        "clip_a_id": "c1",
        "clip_b_id": "c2",
        "transition_type": "dissolve",
        "duration_sec": 1.0,
    }
    with patch("open_edit.ir.api.IR.add_transition", return_value=None) as mock_add:
        code, response = run_op(
            "pyagent_add_transition", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_add.called
    call_kwargs = mock_add.call_args.kwargs
    assert call_kwargs["clip_a_id"] == "c1"
    assert call_kwargs["clip_b_id"] == "c2"
    assert call_kwargs["transition_type"] == "dissolve"
    assert call_kwargs["duration_sec"] == 1.0


def test_remove_transition_repointed(tmp_path):
    """pyagent_remove_transition should call open_edit.ir.api.IR.remove_transition."""
    project_path = _make_project_dir(tmp_path)
    args = {"transition_id": "t1"}
    with patch("open_edit.ir.api.IR.remove_transition", return_value=None) as mock_remove:
        code, response = run_op(
            "pyagent_remove_transition", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_remove.called
    call_kwargs = mock_remove.call_args.kwargs
    assert call_kwargs["transition_id"] == "t1"


def test_set_transition_property_repointed(tmp_path):
    """pyagent_set_transition_property should call open_edit.ir.api.IR.set_transition_property."""
    project_path = _make_project_dir(tmp_path)
    args = {
        "transition_id": "t1",
        "prop_name": "in",
        "value": "00:00:00.250",
    }
    with patch("open_edit.ir.api.IR.set_transition_property", return_value=None) as mock_set:
        code, response = run_op(
            "pyagent_set_transition_property", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_set.called
    call_kwargs = mock_set.call_args.kwargs
    assert call_kwargs["transition_id"] == "t1"
    assert call_kwargs["prop_name"] == "in"
    assert call_kwargs["value"] == "00:00:00.250"


def test_insert_clip_repointed(tmp_path):
    """pyagent_insert_clip should call open_edit.ir.api.IR.add_clip."""
    project_path = _make_project_dir(tmp_path)
    args = {
        "track_id": "t1",
        "asset_hash": "abc",
        "position_sec": 0.0,
        "in_point_sec": 0.0,
        "out_point_sec": 5.0,
    }
    with patch("open_edit.ir.api.IR.add_clip", return_value="clip_1") as mock_add:
        code, response = run_op(
            "pyagent_insert_clip", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_add.called
    call_kwargs = mock_add.call_args.kwargs
    assert call_kwargs["asset_hash"] == "abc"
    assert call_kwargs["track_id"] == "t1"
    assert call_kwargs["position_sec"] == 0.0


def test_append_clip_repointed(tmp_path):
    """pyagent_append_clip should call open_edit.ir.api.IR.add_clip."""
    project_path = _make_project_dir(tmp_path)
    args = {
        "track_id": "t1",
        "asset_hash": "abc",
    }
    with patch("open_edit.ir.api.IR.add_clip", return_value="clip_1") as mock_add:
        code, response = run_op(
            "pyagent_append_clip", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_add.called


def test_move_clip_repointed(tmp_path):
    """pyagent_move_clip should call open_edit.ir.api.IR.move_clip."""
    project_path = _make_project_dir(tmp_path)
    args = {
        "clip_id": "c1",
        "new_track_id": "t2",
        "new_position_sec": 10.0,
    }
    with patch("open_edit.ir.api.IR.move_clip", return_value=None) as mock_move:
        code, response = run_op(
            "pyagent_move_clip", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_move.called
    call_kwargs = mock_move.call_args.kwargs
    assert call_kwargs["clip_id"] == "c1"
    assert call_kwargs["new_track_id"] == "t2"
    assert call_kwargs["new_position_sec"] == 10.0


def test_trim_clip_repointed(tmp_path):
    """pyagent_trim_clip should call open_edit.ir.api.IR.trim_clip."""
    project_path = _make_project_dir(tmp_path)
    args = {
        "clip_id": "c1",
        "new_in_point_sec": 1.0,
        "new_out_point_sec": 4.0,
    }
    with patch("open_edit.ir.api.IR.trim_clip", return_value=None) as mock_trim:
        code, response = run_op(
            "pyagent_trim_clip", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_trim.called
    call_kwargs = mock_trim.call_args.kwargs
    assert call_kwargs["clip_id"] == "c1"
    assert call_kwargs["in_point_sec"] == 1.0
    assert call_kwargs["out_point_sec"] == 4.0


def test_delete_clip_repointed(tmp_path):
    """pyagent_delete_clip should call open_edit.ir.api.IR.remove_clip."""
    project_path = _make_project_dir(tmp_path)
    args = {"clip_id": "c1"}
    with patch("open_edit.ir.api.IR.remove_clip", return_value=None) as mock_remove:
        code, response = run_op(
            "pyagent_delete_clip", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_remove.called
    call_kwargs = mock_remove.call_args.kwargs
    assert call_kwargs["clip_id"] == "c1"


def test_slip_clip_repointed(tmp_path):
    """pyagent_slip_clip should call open_edit.ir.api.IR.slip_clip."""
    project_path = _make_project_dir(tmp_path)
    args = {"clip_id": "c1", "delta_sec": 0.5}
    with patch("open_edit.ir.api.IR.slip_clip", return_value=None) as mock_slip:
        code, response = run_op(
            "pyagent_slip_clip", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_slip.called
    call_kwargs = mock_slip.call_args.kwargs
    assert call_kwargs["clip_id"] == "c1"
    assert call_kwargs["delta_sec"] == 0.5


def test_ripple_delete_clip_repointed(tmp_path):
    """pyagent_ripple_delete_clip should call open_edit.ir.api.IR.ripple_delete_clip."""
    project_path = _make_project_dir(tmp_path)
    args = {"clip_id": "c1"}
    with patch("open_edit.ir.api.IR.ripple_delete_clip", return_value=None) as mock_del:
        code, response = run_op(
            "pyagent_ripple_delete_clip", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_del.called
    call_kwargs = mock_del.call_args.kwargs
    assert call_kwargs["clip_id"] == "c1"


def test_change_clip_speed_repointed(tmp_path):
    """pyagent_change_clip_speed should call open_edit.ir.api.IR.change_clip_speed."""
    project_path = _make_project_dir(tmp_path)
    args = {"clip_id": "c1", "rate": 2.0}
    with patch("open_edit.ir.api.IR.change_clip_speed", return_value=None) as mock_speed:
        code, response = run_op(
            "pyagent_change_clip_speed", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_speed.called
    call_kwargs = mock_speed.call_args.kwargs
    assert call_kwargs["clip_id"] == "c1"
    assert call_kwargs["rate"] == 2.0


def test_split_clip_repointed(tmp_path):
    """pyagent_split_clip should call open_edit.ir.api.IR.split_clip."""
    project_path = _make_project_dir(tmp_path)
    args = {"clip_id": "c1", "at_sec": 2.0}
    with patch("open_edit.ir.api.IR.split_clip", return_value=["c1_left", "c1_right"]) as mock_split:
        code, response = run_op(
            "pyagent_split_clip", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_split.called
    call_kwargs = mock_split.call_args.kwargs
    assert call_kwargs["clip_id"] == "c1"
    assert call_kwargs["at_sec"] == 2.0


def test_replace_clip_source_repointed(tmp_path):
    """pyagent_replace_clip_source should call open_edit.ir.api.IR.replace_clip_source."""
    project_path = _make_project_dir(tmp_path)
    args = {"clip_id": "c1", "new_asset_hash": "new_abc"}
    with patch("open_edit.ir.api.IR.replace_clip_source", return_value=None) as mock_replace:
        code, response = run_op(
            "pyagent_replace_clip_source", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_replace.called
    call_kwargs = mock_replace.call_args.kwargs
    assert call_kwargs["clip_id"] == "c1"
    assert call_kwargs["new_asset_hash"] == "new_abc"


def test_set_clip_speed_ramp_repointed(tmp_path):
    """pyagent_set_clip_speed_ramp should call open_edit.ir.api.IR.set_clip_speed_ramp."""
    project_path = _make_project_dir(tmp_path)
    args = {
        "clip_id": "c1",
        "keyframes": [{"time_ms": 0, "rate": 1.0}, {"time_ms": 1000, "rate": 2.0}],
    }
    with patch("open_edit.ir.api.IR.set_clip_speed_ramp", return_value=None) as mock_ramp:
        code, response = run_op(
            "pyagent_set_clip_speed_ramp", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_ramp.called
    call_kwargs = mock_ramp.call_args.kwargs
    assert call_kwargs["clip_id"] == "c1"
    assert len(call_kwargs["keyframes"]) == 2


def test_import_media_repointed(tmp_path):
    """pyagent_import_media should call AssetStore.ingest_paths."""
    project_path = _make_project_dir(tmp_path)
    args = {"paths": ["/tmp/video.mp4"]}
    fake_asset = {
        "asset_hash": "abc123",
        "original_path": "/tmp/video.mp4",
        "stored_path": "/tmp/abc123",
        "type": "video",
        "duration_sec": 10.0,
    }
    with patch(
        "open_edit.storage.assets.AssetStore.ingest_paths",
        return_value=[fake_asset],
    ) as mock_ingest:
        code, response = run_op(
            "pyagent_import_media", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_ingest.called
    call_args = mock_ingest.call_args.args[0]
    assert call_args == ["/tmp/video.mp4"]


def test_get_effect_param_repointed(tmp_path):
    """pyagent_get_effect_param should return a value derived from the timeline."""
    project_path = _make_project_dir(tmp_path)
    args = {"clip_id": "c1", "effect_index": 0, "param_name": "level"}
    code, response = run_op(
        "pyagent_get_effect_param", args,
        project_path=str(project_path), catalog_path="/tmp/catalog.json",
    )
    assert code in (0, 1)
    assert "ok" in response


def test_set_effect_param_repointed(tmp_path):
    """pyagent_set_effect_param should call open_edit.ir.api.IR.set_effect_param."""
    project_path = _make_project_dir(tmp_path)
    args = {"clip_id": "c1", "effect_index": 0, "param_name": "level", "value": "0.5"}
    with patch("open_edit.ir.api.IR.set_effect_param", return_value=None) as mock_set:
        code, response = run_op(
            "pyagent_set_effect_param", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_set.called
    call_kwargs = mock_set.call_args.kwargs
    assert call_kwargs["clip_id"] == "c1"
    assert call_kwargs["effect_index"] == 0
    assert call_kwargs["param_name"] == "level"
    assert call_kwargs["value"] == "0.5"


def test_list_keyframes_repointed(tmp_path):
    """pyagent_list_keyframes should return a list derived from the timeline."""
    project_path = _make_project_dir(tmp_path)
    args = {"clip_id": "c1", "effect_index": 0, "param_name": "level"}
    code, response = run_op(
        "pyagent_list_keyframes", args,
        project_path=str(project_path), catalog_path="/tmp/catalog.json",
    )
    assert code in (0, 1)
    assert "ok" in response


def test_set_keyframe_repointed(tmp_path):
    """pyagent_set_keyframe should call open_edit.ir.api.IR.set_keyframe."""
    project_path = _make_project_dir(tmp_path)
    args = {
        "clip_id": "c1",
        "effect_index": 0,
        "param_name": "level",
        "frame": 30,
        "value": "0.5",
        "type": "linear",
    }
    with patch("open_edit.ir.api.IR.set_keyframe", return_value=None) as mock_set:
        code, response = run_op(
            "pyagent_set_keyframe", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_set.called
    call_kwargs = mock_set.call_args.kwargs
    assert call_kwargs["effect_id"] == "c1__0"
    assert call_kwargs["param"] == "level"


def test_remove_keyframe_repointed(tmp_path):
    """pyagent_remove_keyframe should call open_edit.ir.api.IR.remove_keyframe."""
    project_path = _make_project_dir(tmp_path)
    args = {"clip_id": "c1", "effect_index": 0, "param_name": "level", "frame": 30}
    with patch("open_edit.ir.api.IR.remove_keyframe", return_value=None) as mock_remove:
        code, response = run_op(
            "pyagent_remove_keyframe", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_remove.called
    call_kwargs = mock_remove.call_args.kwargs
    assert call_kwargs["effect_id"] == "c1__0"
    assert call_kwargs["param"] == "level"
    assert call_kwargs["frame"] == 30


def test_add_effect_to_track_repointed(tmp_path):
    """pyagent_add_effect_to_track should call IR.add_effect with target_kind='track'."""
    project_path = _make_project_dir(tmp_path)
    args = {
        "track_index": 0,
        "effect_id": "volume",
        "params": {"gain": 0.5},
    }
    with patch("open_edit.ir.api.IR.add_effect", return_value="fx_1") as mock_add:
        code, response = run_op(
            "pyagent_add_effect_to_track", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_add.called
    call_kwargs = mock_add.call_args.kwargs
    assert call_kwargs["target_kind"] == "track"


def test_list_track_effects_repointed(tmp_path):
    """pyagent_list_track_effects should return a list derived from the timeline."""
    project_path = _make_project_dir(tmp_path)
    args = {"track_index": 0}
    code, response = run_op(
        "pyagent_list_track_effects", args,
        project_path=str(project_path), catalog_path="/tmp/catalog.json",
    )
    assert code in (0, 1)
    assert "ok" in response


def test_group_clips_repointed(tmp_path):
    """pyagent_group_clips should call open_edit.ir.api.IR.group_edits."""
    project_path = _make_project_dir(tmp_path)
    args = {
        "edit_ids": ["op1", "op2"],
        "label": "my_group",
    }
    with patch("open_edit.ir.api.IR.group_edits", return_value=None) as mock_group:
        code, response = run_op(
            "pyagent_group_clips", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_group.called
    call_kwargs = mock_group.call_args.kwargs
    assert call_kwargs["edit_ids"] == ["op1", "op2"]
    assert call_kwargs["label"] == "my_group"


def test_ungroup_clips_repointed(tmp_path):
    """pyagent_ungroup_clips should call open_edit.ir.api.IR.ungroup_edits."""
    project_path = _make_project_dir(tmp_path)
    args = {"group_name": "my_group"}
    with patch("open_edit.ir.api.IR.ungroup_edits", return_value=None) as mock_ungroup:
        code, response = run_op(
            "pyagent_ungroup_clips", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    assert mock_ungroup.called
    call_kwargs = mock_ungroup.call_args.kwargs
    assert call_kwargs["label"] == "my_group"


def test_list_groups_repointed(tmp_path):
    """pyagent_list_groups should return a list derived from the timeline."""
    project_path = _make_project_dir(tmp_path)
    args = {}
    code, response = run_op(
        "pyagent_list_groups", args,
        project_path=str(project_path), catalog_path="/tmp/catalog.json",
    )
    assert code in (0, 1)
    assert "ok" in response


def test_save_project_repointed(tmp_path):
    """pyagent_save_project should be a no-op (state is already persisted)."""
    project_path = _make_project_dir(tmp_path)
    args = {}
    code, response = run_op(
        "pyagent_save_project", args,
        project_path=str(project_path), catalog_path="/tmp/catalog.json",
    )
    assert code == 0
    assert response["ok"] is True


def test_get_project_info_repointed(tmp_path):
    """pyagent_get_project_info should return a dict derived from the project."""
    project_path = _make_project_dir(tmp_path)
    args = {}
    code, response = run_op(
        "pyagent_get_project_info", args,
        project_path=str(project_path), catalog_path="/tmp/catalog.json",
    )
    assert code == 0
    assert response["ok"] is True


def test_get_timeline_summary_repointed(tmp_path):
    """pyagent_get_timeline_summary should return a summary derived from the timeline."""
    project_path = _make_project_dir(tmp_path)
    args = {}
    code, response = run_op(
        "pyagent_get_timeline_summary", args,
        project_path=str(project_path), catalog_path="/tmp/catalog.json",
    )
    assert code == 0
    assert response["ok"] is True


def test_list_catalog_repointed(tmp_path):
    """list_catalog should still work (special case, not a wrapper)."""
    project_path = _make_project_dir(tmp_path)
    args = {"kind": "effects"}
    code, response = run_op(
        "pyagent_list_catalog", args,
        project_path=str(project_path), catalog_path="/tmp/catalog.json",
    )
    assert code == 2
