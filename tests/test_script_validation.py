"""Script bootstrap, preflight, and edit validation regression tests."""
import ast
import json

import pytest

from open_edit.agent.script_runner.bootstrap import BOOTSTRAP_SCHEMA_VERSION, render_bootstrap
from open_edit.agent.script_runner.staging import (
    _FlushingBuffer,
    _load_assets_via_store,
)
from open_edit.ir.types import Asset
from open_edit.storage.edit_graph import EditGraphStore


def test_flushing_buffer_writes_first_then_appends(tmp_path):
    """H10: write first, then append; failed write raises."""
    ops_file = tmp_path / "ops.jsonl"
    buf = _FlushingBuffer(ops_file)
    from open_edit.ir.types import AddClipOp, new_id
    op = AddClipOp(
        edit_id=new_id(), author="ai", parent_id="e",
        clip_id="c1", asset_hash="abc", track_id="t1", position_sec=0.0,
    )
    buf.append(op)
    assert ops_file.exists()
    assert len(buf) == 1
    # Each line is a valid JSON op
    parsed = json.loads(ops_file.read_text().strip())
    assert parsed["kind"] == "add_clip"
    assert parsed["clip_id"] == "c1"

def test_render_bootstrap_is_self_contained():
    """C2: bootstrap does NOT `import open_edit`."""
    bootstrap = render_bootstrap(project_id="p1", parent_op_id="e1")
    # The bootstrap should inline the IR class; no `from open_edit` import
    # for IR/op models (the imports block only has typing/pydantic/datetime).
    assert "from open_edit.ir.api import IR" not in bootstrap
    # The IR class should be inlined
    assert "class IR:" in bootstrap
    # The 12 op models should be inlined (at least the class names)
    for cls in ["AddClipOp", "TrimClipOp", "FreeFormCodeOp"]:
        assert f"class {cls}" in bootstrap
    # Project and parent IDs are injected
    assert "'p1'" in bootstrap
    assert "'e1'" in bootstrap
    # OPS_FILE is /scratch/ops.jsonl (in-sandbox path, C1); emitted via !r.
    assert "OPS_FILE = 'ops.jsonl'" in bootstrap

def test_render_bootstrap_schema_and_required_symbols_parse():
    """The generated source must remain executable and structurally complete."""
    bootstrap = render_bootstrap(project_id="p1", parent_op_id="e1")
    ast.parse(bootstrap)
    assert f"BOOTSTRAP_SCHEMA_VERSION = {BOOTSTRAP_SCHEMA_VERSION}" in bootstrap
    for name in (
        "IR",
        "_FlushingBuffer",
        "AddClipOp",
        "RemoveClipOp",
        "MoveClipOp",
        "TrimClipOp",
        "AddTransitionOp",
        "RemoveTransitionOp",
        "SetTransitionPropertyOp",
        "AddEffectOp",
        "RemoveEffectOp",
        "SetEffectParamOp",
        "SetKeyframeOp",
        "RemoveKeyframeOp",
        "SlipClipOp",
        "RippleDeleteClipOp",
        "ChangeClipSpeedOp",
        "SplitClipOp",
        "ReplaceClipSourceOp",
        "SetClipSpeedRampOp",
        "SetAudioGainOp",
        "NormalizeAudioOp",
        "GroupEditsOp",
        "UngroupEditsOp",
        "RawMltXmlOp",
        "FreeFormCodeOp",
        "AddHtmlOverlayOp",
        "RemoveHtmlOverlayOp",
        "AddRemotionCompositionOp",
        "RemoveRemotionCompositionOp",
    ):
        assert f"class {name}" in bootstrap

def test_render_bootstrap_inlines_all_op_classes():
    """C1 follow-up: bootstrap must inline a class definition for every op in OperationUnion.

    Self-enforcing: derives the expected set from `OperationUnion` itself via
    `typing.get_args`, not a hardcoded list. Adding a 25th op class to
    `OperationUnion` (and forgetting to add it to `op_types` in
    `render_bootstrap`) will fail this test with a clear
    "Missing op class definitions" message naming the missing op.
    """
    from typing import get_args

    from open_edit.ir.types import OperationUnion

    # OperationUnion is `Annotated[Union[...], Field(...)]`. Unwrap the
    # Annotated to get the Union, then get_args() to list all op classes.
    _op_union, _ = get_args(OperationUnion)
    op_classes = get_args(_op_union)  # tuple of all op classes
    expected_names = {cls.__name__ for cls in op_classes}

    bootstrap = render_bootstrap(project_id="p1", parent_op_id="e1")

    missing = sorted(
        name for name in expected_names
        if f"class {name}" not in bootstrap
    )
    assert not missing, (
        f"Missing op class definitions in bootstrap: {missing}. "
        f"Either add them to `op_types` in "
        f"open_edit/agent/script_runner/bootstrap.py:render_bootstrap, "
        f"or this is a regression of the C1 fix."
    )

def test_bootstrap_exec_instantiates_all_24_op_classes(tmp_path):
    """C1 (final-fixes): executing the bootstrap must make every op class
    available in scope (no NameError when IR methods construct them).
    """
    bootstrap = render_bootstrap(
        project_id="p1",
        parent_op_id="e1",
        originating_note_id="n1",
    )
    # Run the bootstrap in an isolated globals dict, like the Rust binary does
    g: dict = {"__name__": "__sandbox__", "__file__": "<bootstrap>"}
    exec(compile(bootstrap, "<bootstrap>", "exec"), g)

    # Every op class name must be reachable in the bootstrap's globals
    expected = [
        "AddClipOp", "RemoveClipOp", "MoveClipOp", "TrimClipOp",
        "AddTransitionOp", "RemoveTransitionOp", "SetTransitionPropertyOp",
        "AddEffectOp", "RemoveEffectOp", "SetEffectParamOp",
        "SetKeyframeOp", "RemoveKeyframeOp",
        "SlipClipOp", "RippleDeleteClipOp", "ChangeClipSpeedOp",
        "SplitClipOp", "ReplaceClipSourceOp", "SetClipSpeedRampOp",
        "SetAudioGainOp", "NormalizeAudioOp",
        "GroupEditsOp", "UngroupEditsOp",
        "RawMltXmlOp", "FreeFormCodeOp",
    ]
    for name in expected:
        assert name in g, f"{name} not in bootstrap scope after exec"

    motion = g['ObjectTrack'](clip_id='hero', asset_hash='a'*64, frames=[
        {'time_sec':0,'x':.1,'y':.2,'width':.3,'height':.4}])
    tracked = g['SetObjectTrackOp'](author='ai',object_id='target',clip_id='hero',track=motion)
    assert tracked.model_dump(mode='json')['track']['frames'][0]['x'] == .1
    with pytest.raises(ValueError):
        g['TrackFrame'](time_sec=0,x=.9,y=.2,width=.3,height=.4)

    # `ir` instance must be present and must accept a method that was added
    # in T7 (was NameError before the fix).
    assert "ir" in g
    # Wire a buffer; IR will append a SlipClipOp
    import json
    ops_file = tmp_path / "ops.jsonl"
    class _Buf(list):
        def append(self, op):
            super().append(op)
            with open(ops_file, "a") as f:
                f.write(op.model_dump_json() + "\n")
    g["_ops"] = _Buf()
    g["ir"] = g["IR"](
        g["_ops"],
        project_id="p1",
        parent_op_id="e1",
        originating_note_id="n1",
    )
    # Calling a T7 method must not raise NameError
    g["ir"].slip_clip(clip_id="c1", delta_sec=0.5)
    assert ops_file.exists()
    lines = [ln for ln in ops_file.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["kind"] == "slip_clip"
    assert parsed["parent_id"] == "e1"

def test_run_free_form_auto_injects_missing_header(tmp_path):
    """No ``# ir_api_version:`` header is auto-injected (not a preflight fail)."""
    from open_edit.agent.script_runner import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    result = run_free_form(
        code="import os  # no header",
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
    )
    assert result.reason != "preflight_failed"

def test_run_free_form_unsupported_version_returns_fail(tmp_path):
    from open_edit.agent.script_runner import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    result = run_free_form(
        code="# ir_api_version: 99.0; libs: {}",
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
    )
    assert not result.success
    assert result.reason == "ir_api_version_unsupported"

def test_run_free_form_unsupported_lib_returns_fail(tmp_path):
    from open_edit.agent.script_runner import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    result = run_free_form(
        code='# ir_api_version: 0.1; libs: {"numpy": "99.0"}',
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
    )
    assert not result.success
    assert result.reason == "lib_version_unsupported"

def test_run_free_form_rejects_non_positive_limits(tmp_path):
    """Malformed / non-positive timeout & mem_mb must never raise."""
    from open_edit.agent.script_runner import run_free_form

    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    for kwargs in (
        {"timeout": -1},
        {"timeout": 0},
        {"timeout": None},
        {"timeout": "nope"},
        {"timeout": 1.5},
        {"timeout": float("inf")},
        {"mem_mb": -5},
        {"mem_mb": None},
        {"mem_mb": 1.5},
        {"mem_mb": float("-inf")},
        {"cpu_sec": 0},
        {"cpu_sec": "nope"},
        {"cpu_sec": 1.5},
    ):
        result = run_free_form(
            code="# ir_api_version: 0.1; libs: {}",
            workdir=workdir,
            project_id="p1",
            parent_op_id="e1",
            **kwargs,
        )
        assert result.success is False
        assert result.reason == "invalid_argument"

def test_bootstrap_ops_file_uses_repr_for_hostile_paths():
    from open_edit.agent.script_runner.bootstrap import render_bootstrap

    src = render_bootstrap("p1", "e1", ops_file='/tmp/a"b/ops.jsonl')
    assert "OPS_FILE = '/tmp/a\"b/ops.jsonl'" in src
    compile(src, "<bootstrap>", "exec")

def _build_minimal_timeline(tmp_path):
    """Build a Project with one clip + one effect + one group for use in
    reference validation tests. Returns (project, timeline, edit_graph)."""
    from open_edit.ir.derive import derive_timeline
    from open_edit.ir.types import (
        AddClipOp,
        AddEffectOp,
        Asset,
        GroupEditsOp,
        Project,
        new_id,
    )
    from open_edit.storage.edit_graph import EditGraphStore

    workdir = tmp_path / "proj"
    workdir.mkdir()
    db_path = workdir / "edit_graph.db"
    EditGraphStore(db_path)  # creates the schema
    assets_dir = workdir / "assets"
    assets_dir.mkdir()

    a = Asset(
        asset_hash="asset_abc",
        original_path="x",
        stored_path="x",
        type="video",
    )
    assets = {"asset_abc": a}

    add_clip = AddClipOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        asset_hash="asset_abc", track_id="t1", position_sec=0.0,
        in_point_sec=0.0, out_point_sec=5.0,
    )
    add_effect = AddEffectOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        target_kind="clip", target_id=add_clip.clip_id,
        effect_type="blur", effect_id="effect_xyz",
    )
    group = GroupEditsOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        edit_ids=[add_clip.edit_id], label="group1",
    )

    edit_graph = [add_clip, add_effect, group]
    project = Project(
        project_id="p1", name="test",
        workdir=workdir, assets=assets, edit_graph=edit_graph,
    )
    timeline = derive_timeline(project)
    return project, timeline, edit_graph

def test_validate_references_missing_clip_op_raises(tmp_path):
    """I2: ops that reference a clip_id not in the project must be rejected."""
    from open_edit.ir.types import MoveClipOp, RemoveClipOp, TrimClipOp, new_id
    from open_edit.ir.validate import validate_op_references

    project, _, _ = _build_minimal_timeline(tmp_path)

    for cls in (TrimClipOp, MoveClipOp, RemoveClipOp):
        if cls is MoveClipOp:
            op = cls(
                edit_id=new_id(), author="ai", parent_id="p1",
                clip_id="no_such_clip", new_track_id="t2", new_position_sec=1.0,
            )
        else:
            op = cls(
                edit_id=new_id(), author="ai", parent_id="p1",
                clip_id="no_such_clip",
                **({"new_in_point_sec": 0.0, "new_out_point_sec": 1.0} if cls is TrimClipOp else {}),
            )
        errors = validate_op_references(op, project, strict=True)
        assert any("clip_id" in e for e in errors), f"{cls.__name__}: {errors}"

def test_validate_references_slip_ripple_speed_split_ramp_raises(tmp_path):
    """I2: SlipClipOp, RippleDeleteClipOp, ChangeClipSpeedOp, SplitClipOp,
    SetClipSpeedRampOp must validate clip_id."""
    from open_edit.ir.types import (
        ChangeClipSpeedOp,
        RippleDeleteClipOp,
        SetClipSpeedRampOp,
        SlipClipOp,
        SplitClipOp,
        new_id,
    )
    from open_edit.ir.validate import validate_op_references

    project, _, _ = _build_minimal_timeline(tmp_path)

    bad = {
        "slip": SlipClipOp(edit_id=new_id(), author="ai", parent_id="p1",
                            clip_id="nope", delta_sec=0.5),
        "ripple": RippleDeleteClipOp(edit_id=new_id(), author="ai", parent_id="p1",
                                      clip_id="nope"),
        "speed": ChangeClipSpeedOp(edit_id=new_id(), author="ai", parent_id="p1",
                                    clip_id="nope", rate=2.0),
        "split": SplitClipOp(edit_id=new_id(), author="ai", parent_id="p1",
                              clip_id="nope", at_sec=1.0),
        "ramp": SetClipSpeedRampOp(edit_id=new_id(), author="ai", parent_id="p1",
                                    clip_id="nope"),
    }
    for name, op in bad.items():
        errors = validate_op_references(op, project, strict=True)
        assert any("clip_id" in e for e in errors), f"{name}: {errors}"

def test_validate_references_add_transition_missing_clip_raises(tmp_path):
    """I2: AddTransitionOp with missing clip_a_id or clip_b_id must be rejected."""
    from open_edit.ir.types import AddTransitionOp, new_id
    from open_edit.ir.validate import validate_op_references

    project, _, _ = _build_minimal_timeline(tmp_path)

    op = AddTransitionOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_a_id="nope_a", clip_b_id="nope_b",
        transition_type="luma", duration_sec=0.5,
    )
    errors = validate_op_references(op, project, strict=True)
    assert any("clip_a_id" in e for e in errors)

def test_validate_references_transition_ops_validate_id(tmp_path):
    """I2: RemoveTransitionOp + SetTransitionPropertyOp must validate transition_id.

    Transitions are stored as Effect on the clip. We test by giving a bogus id.
    """
    from open_edit.ir.types import (
        RemoveTransitionOp,
        SetTransitionPropertyOp,
        new_id,
    )
    from open_edit.ir.validate import validate_op_references

    project, _, _ = _build_minimal_timeline(tmp_path)

    for cls in (RemoveTransitionOp, SetTransitionPropertyOp):
        kwargs = {"edit_id": new_id(), "author": "ai", "parent_id": "p1",
                  "transition_id": "no_such_transition"}
        if cls is SetTransitionPropertyOp:
            kwargs.update({"prop_name": "x", "value": "y"})
        op = cls(**kwargs)
        errors = validate_op_references(op, project, strict=True)
        assert any("transition_id" in e for e in errors), f"{cls.__name__}: {errors}"

def test_validate_references_remove_set_effect_validates_clip_index(tmp_path):
    """I2: RemoveEffectOp + SetEffectParamOp must validate clip_id, effect_index,
    and (for SetEffectParamOp) param_name."""
    from open_edit.ir.types import RemoveEffectOp, SetEffectParamOp, new_id
    from open_edit.ir.validate import validate_op_references

    project, timeline, _ = _build_minimal_timeline(tmp_path)

    # missing clip
    op_bad_clip = RemoveEffectOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id="nope", effect_index=0,
    )
    errors = validate_op_references(op_bad_clip, project, strict=True)
    assert any("clip_id" in e for e in errors)

    # valid clip but invalid index
    real_clip_id = timeline.tracks[0].clips[0].clip_id
    op_bad_idx = RemoveEffectOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id=real_clip_id, effect_index=999,
    )
    errors = validate_op_references(op_bad_idx, project, strict=True)
    assert any("effect_index" in e for e in errors)

    # SetEffectParamOp: bad param name
    op_bad_param = SetEffectParamOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id=real_clip_id, effect_index=0,
        param_name="nonexistent_param", value="1",
    )
    errors = validate_op_references(op_bad_param, project, strict=True)
    assert any("param_name" in e for e in errors)

def test_validate_references_remove_keyframe_validates(tmp_path):
    """I2: RemoveKeyframeOp must validate effect_id and the param on the effect."""
    from open_edit.ir.types import RemoveKeyframeOp, new_id
    from open_edit.ir.validate import validate_op_references

    project, _, _ = _build_minimal_timeline(tmp_path)

    # missing effect_id
    op_bad_eff = RemoveKeyframeOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        effect_id="nope", param="gain", frame=1.0,
    )
    errors = validate_op_references(op_bad_eff, project, strict=True)
    assert any("effect_id" in e for e in errors)

    # known effect but param never keyframed
    op_bad_param = RemoveKeyframeOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        effect_id="effect_xyz", param="gain", frame=1.0,
    )
    errors = validate_op_references(op_bad_param, project, strict=True)
    assert any("param" in e for e in errors), f"{errors}"

def test_validate_references_replace_clip_source_validates(tmp_path):
    """I2: ReplaceClipSourceOp must validate clip_id AND new_asset_hash."""
    from open_edit.ir.types import ReplaceClipSourceOp, new_id
    from open_edit.ir.validate import validate_op_references

    project, timeline, _ = _build_minimal_timeline(tmp_path)

    # bad clip
    op_bad_clip = ReplaceClipSourceOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id="nope", new_asset_hash="asset_abc",
    )
    errors = validate_op_references(op_bad_clip, project, strict=True)
    assert any("clip_id" in e for e in errors)

    real_clip_id = timeline.tracks[0].clips[0].clip_id
    # bad asset
    op_bad_asset = ReplaceClipSourceOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id=real_clip_id, new_asset_hash="not_in_project",
    )
    errors = validate_op_references(op_bad_asset, project, strict=True)
    assert any("asset_hash" in e for e in errors)

def test_validate_references_normalize_audio_validates_target(tmp_path):
    """I2: NormalizeAudioOp must validate target_id (clip or track)."""
    from open_edit.ir.types import NormalizeAudioOp, new_id
    from open_edit.ir.validate import validate_op_references

    project, _, _ = _build_minimal_timeline(tmp_path)

    # clip with bad id
    op_bad_clip = NormalizeAudioOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        target_kind="clip", target_id="nope", target_dbfs=-16.0,
    )
    errors = validate_op_references(op_bad_clip, project, strict=True)
    assert any("target_id" in e for e in errors)

    # track with bad id
    op_bad_track = NormalizeAudioOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        target_kind="track", target_id="nope", target_dbfs=-16.0,
    )
    errors = validate_op_references(op_bad_track, project, strict=True)
    assert any("target_id" in e for e in errors)

    # unknown kind
    op_bad_kind = NormalizeAudioOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        target_kind="project", target_id="nope", target_dbfs=-16.0,
    )
    errors = validate_op_references(op_bad_kind, project, strict=True)
    assert any("target_kind" in e for e in errors)

def test_validate_references_group_ungroup_validates(tmp_path):
    """I2: GroupEditsOp + UngroupEditsOp must validate."""
    from open_edit.ir.types import GroupEditsOp, UngroupEditsOp, new_id
    from open_edit.ir.validate import validate_op_references

    project, _, _ = _build_minimal_timeline(tmp_path)

    # group with non-existent edit_id
    op_bad_edit = GroupEditsOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        edit_ids=["no_such_edit"], label="g1",
    )
    errors = validate_op_references(op_bad_edit, project, strict=True)
    assert any("edit_id" in e for e in errors)

    # ungroup with non-existent label
    op_bad_label = UngroupEditsOp(
        edit_id=new_id(), author="ai", parent_id="p1", label="no_such_group",
    )
    errors = validate_op_references(op_bad_label, project, strict=True)
    assert any("label" in e for e in errors)

def test_validate_references_raw_mlt_and_free_form_skip(tmp_path):
    """I2: RawMltXmlOp and FreeFormCodeOp need no reference check — only the
    parent_id stamp check (which both pass)."""
    from open_edit.ir.types import FreeFormCodeOp, RawMltXmlOp, new_id
    from open_edit.ir.validate import validate_op_references

    project, _, _ = _build_minimal_timeline(tmp_path)

    op_raw = RawMltXmlOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        xml="<mlt/>", description="x",
    )
    op_free = FreeFormCodeOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        code="pass",
    )
    # No reference error means validation passed.
    assert validate_op_references(op_raw, project, strict=True) == []
    assert validate_op_references(op_free, project, strict=True) == []
    # Without the IR-stamped parent_id the op is rejected.
    op_raw.parent_id = None
    errors = validate_op_references(op_raw, project, strict=True)
    assert any("parent_id" in e for e in errors)

def test_validate_ops_incrementally_raises_via_op_validation_error(tmp_path):
    """Task 3.4: the sandbox surfaces reference failures as OpValidationError
    (the IR reference-error type), wrapped in the line-numbered
    _ValidationError — no bare ReferenceError."""
    from open_edit.agent.exceptions import _ValidationError
    from open_edit.agent.script_runner.staging import _validate_ops_incrementally
    from open_edit.ir.types import TrimClipOp, new_id
    from open_edit.ir.validate import OpValidationError

    workdir = tmp_path / "proj"
    workdir.mkdir()
    EditGraphStore(workdir / "edit_graph.db")
    (workdir / "assets").mkdir()

    ops_path = workdir / "ops.jsonl"
    op = TrimClipOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id="nope", new_in_point_sec=0.0, new_out_point_sec=1.0,
    )
    ops_path.write_text(op.model_dump_json() + "\n")

    with pytest.raises(_ValidationError) as exc_info:
        _validate_ops_incrementally(ops_path, workdir)
    assert isinstance(exc_info.value.__cause__, OpValidationError)
    assert "clip_id 'nope' not in project" in str(exc_info.value)

def test_validate_ops_incrementally_accepts_same_batch_chain(tmp_path):
    """C6: a batch op may reference a clip created by an EARLIER op in the
    SAME batch — validation runs against the growing working timeline, not
    just the stored graph."""
    from open_edit.agent.script_runner.staging import _validate_ops_incrementally
    from open_edit.ir.types import AddClipOp, TrimClipOp, new_id

    workdir = tmp_path / "proj"
    workdir.mkdir()
    EditGraphStore(workdir / "edit_graph.db")
    h = "ab" * 32
    assets_dir = workdir / "assets"
    (assets_dir / h[:2]).mkdir(parents=True)
    asset = Asset(
        asset_hash=h, original_path="/x.mp4", stored_path="/x",
        type="video", duration_sec=10.0,
    )
    (assets_dir / h[:2] / (h + ".meta.json")).write_text(asset.model_dump_json())

    first = AddClipOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        asset_hash=h, track_id="t1", position_sec=0.0,
        in_point_sec=0.0, out_point_sec=5.0,
    )
    second = AddClipOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        asset_hash=h, track_id="t1", position_sec=5.0,
        in_point_sec=0.0, out_point_sec=5.0,
    )
    trim = TrimClipOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id=second.clip_id, new_in_point_sec=0.0, new_out_point_sec=4.0,
    )

    ops_path = workdir / "ops.jsonl"
    ops_path.write_text(
        "\n".join(o.model_dump_json() for o in (first, second, trim)) + "\n"
    )

    ops, _ = _validate_ops_incrementally(ops_path, workdir)
    assert [type(o).__name__ for o in ops] == ["AddClipOp", "AddClipOp", "TrimClipOp"]

def test_load_assets_via_store_includes_unreferenced_assets(tmp_path):
    """An asset present on disk (ingested, not yet used by any add_clip) must
    still be visible to project.assets, otherwise the first clip for it can
    never validate (chicken-and-egg)."""
    workdir = tmp_path / "proj"
    workdir.mkdir()
    assets_dir = workdir / "assets"
    hh = "ab"
    (assets_dir / hh).mkdir(parents=True)
    h = "ab" * 32
    asset = Asset(
        asset_hash=h, original_path="/x.mp4", stored_path="/x",
        type="video", duration_sec=1.0, fps=30.0, width=1920, height=1080,
        codec="h264", has_audio=True,
    )
    (assets_dir / hh / (h + ".meta.json")).write_text(asset.model_dump_json())

    db = workdir / "edit_graph.db"
    store = EditGraphStore(db)  # empty edits table
    assets = _load_assets_via_store(store, workdir)
    assert h in assets
    assert assets[h].asset_hash == h
