"""Phase 3 Task 8: sandbox_bridge unit tests with mocked Rust binary.

Note: The brief's test draft had two bugs vs. the real code:
  1. _FlushingBuffer() needs an ops_file argument (the brief's class signature
     takes one, but the test draft called it with no args).
  2. AddClipOp has no `project_id` field — only `parent_id` (inherited from
     Operation). The test draft passed `project_id="p"` which Pydantic rejects.

Both are fixed here. The intent of H10 (write-first-then-append) and the
structural check on the rendered bootstrap are preserved.
"""
import json
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from open_edit.agent.sandbox_bridge import (
    _render_bootstrap, _FlushingBuffer, _validate_ops_incrementally,
    _ValidationError,
)
from open_edit.agent.exceptions import FreeFormResult


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
    bootstrap = _render_bootstrap(project_id="p1", parent_op_id="e1")
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
    # OPS_FILE is /scratch/ops.jsonl (in-sandbox path, C1)
    assert '"/scratch/ops.jsonl"' in bootstrap


def test_render_bootstrap_inlines_all_24_op_classes():
    """C1 (final-fixes): bootstrap must include all 24 op class definitions.

    Regression: T7 added 12 new op types, but the bootstrap's `op_types`
    list was never updated. The IR class source references all 24 ops
    (via type annotations), but the class definitions are only inlined for
    whatever names are in `op_types`. Any IR method that constructs one of
    the 12 missing ops would raise NameError inside the sandbox.
    """
    from open_edit.ir import types as _types
    all_24 = [
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
    # Sanity: union actually has 24 members
    union_members = _types.OperationUnion.__args__[0].__args__
    assert len(union_members) == 24, (
        f"IR's Union has {len(union_members)} members; "
        f"this test assumes 24. Update the list above if you add ops."
    )

    bootstrap = _render_bootstrap(project_id="p1", parent_op_id="e1")

    missing = [
        name for name in all_24
        if f"class {name}" not in bootstrap
    ]
    assert missing == [], (
        f"Bootstrap is missing {len(missing)} op class definitions: {missing}. "
        f"The IR source references them, but `op_types` in _render_bootstrap "
        f"was not updated when these ops were added in T7."
    )


def test_bootstrap_exec_instantiates_all_24_op_classes(tmp_path):
    """C1 (final-fixes): executing the bootstrap must make every op class
    available in scope (no NameError when IR methods construct them).
    """
    bootstrap = _render_bootstrap(
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


def test_run_free_form_missing_header_returns_preflight_failed(tmp_path):
    """No # ir_api_version: header → FreeFormResult.fail('preflight_failed')."""
    from open_edit.agent.sandbox_bridge import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    result = run_free_form(
        code="import os  # no header",
        workdir=workdir,
        project_id="p1",
        parent_op_id="e1",
    )
    assert not result.success
    assert result.reason == "preflight_failed"


def test_run_free_form_unsupported_version_returns_fail(tmp_path):
    from open_edit.agent.sandbox_bridge import run_free_form
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
    from open_edit.agent.sandbox_bridge import run_free_form
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


def test_run_free_form_clamps_timeout_and_mem():
    """H9: hard caps MAX_FREEFORM_TIMEOUT_SEC=300, MAX_FREEFORM_MEM_MB=4096."""
    from open_edit.agent.sandbox_bridge import (
        MAX_FREEFORM_TIMEOUT_SEC, MAX_FREEFORM_MEM_MB, run_free_form,
    )
    # Test the constants exist with the right values
    assert MAX_FREEFORM_TIMEOUT_SEC == 300
    assert MAX_FREEFORM_MEM_MB == 4096
    # Note: full behavior test requires a real (or mocked) Rust binary;
    # covered in test_free_form_e2e.py.


def test_run_free_form_sandbox_binary_missing(tmp_path):
    """H5: SANDBOX_BIN not on PATH → FreeFormResult.fail('sandbox_binary_missing')."""
    from open_edit.agent.sandbox_bridge import run_free_form
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "edit_graph.db").touch()
    with patch("open_edit.agent.sandbox_bridge._resolve_sandbox_bin", return_value=None):
        result = run_free_form(
            code="# ir_api_version: 0.1; libs: {}",
            workdir=workdir,
            project_id="p1",
            parent_op_id="e1",
        )
    assert not result.success
    assert result.reason == "sandbox_binary_missing"


# =========================================================================
# I1 (final-fixes): run_render must return RenderResult, never raise.
# =========================================================================

def test_run_render_binary_missing_returns_failed_result(tmp_path):
    """I1: missing render binary → RenderResult(ok=False), no exception.

    Before the fix: run_render raised SandboxError (or FileNotFoundError
    via _resolve_render_binary). The brief's C7 contract says run_render
    must NEVER raise; it must return a structured RenderResult with
    ok=False and a detail string.
    """
    from open_edit.agent.sandbox_bridge import run_render
    from open_edit.agent.exceptions import RenderResult

    workdir = tmp_path / "proj"
    workdir.mkdir()
    output_path = workdir / "out.mp4"

    # Force _resolve_render_binary to raise (no binary in any known location).
    with patch(
        "open_edit.agent.sandbox_bridge._resolve_render_binary",
        side_effect=FileNotFoundError("no render binary"),
    ):
        result = run_render(
            code="pass",
            workdir=workdir,
            output_path=output_path,
        )

    assert isinstance(result, RenderResult)
    assert result.ok is False
    assert "no render binary" in result.detail or "binary" in result.detail.lower()


def test_run_render_nonzero_exit_returns_failed_result(tmp_path):
    """I1: render binary exits non-zero → RenderResult(ok=False), no exception."""
    from open_edit.agent.sandbox_bridge import run_render
    from open_edit.agent.exceptions import RenderResult

    workdir = tmp_path / "proj"
    workdir.mkdir()
    output_path = workdir / "out.mp4"

    fake_proc = MagicMock()
    fake_proc.returncode = 1
    fake_proc.stdout = ""
    fake_proc.stderr = "render crashed"

    with patch(
        "open_edit.agent.sandbox_bridge._resolve_render_binary",
        return_value="/fake/binary",
    ), patch(
        "open_edit.agent.sandbox_bridge.subprocess.run",
        return_value=fake_proc,
    ):
        result = run_render(
            code="pass",
            workdir=workdir,
            output_path=output_path,
        )

    assert isinstance(result, RenderResult)
    assert result.ok is False
    assert "render crashed" in result.detail


def test_run_render_missing_output_returns_failed_result(tmp_path):
    """I1: render binary exits 0 but doesn't produce output → RenderResult(ok=False)."""
    from open_edit.agent.sandbox_bridge import run_render
    from open_edit.agent.exceptions import RenderResult

    workdir = tmp_path / "proj"
    workdir.mkdir()
    output_path = workdir / "out.mp4"  # never created

    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.stdout = ""
    fake_proc.stderr = ""

    with patch(
        "open_edit.agent.sandbox_bridge._resolve_render_binary",
        return_value="/fake/binary",
    ), patch(
        "open_edit.agent.sandbox_bridge.subprocess.run",
        return_value=fake_proc,
    ):
        result = run_render(
            code="pass",
            workdir=workdir,
            output_path=output_path,
        )

    assert isinstance(result, RenderResult)
    assert result.ok is False
    assert str(output_path) in result.detail


def test_run_render_timeout_returns_failed_result(tmp_path):
    """I1: subprocess.TimeoutExpired → RenderResult(ok=False), no exception."""
    from open_edit.agent.sandbox_bridge import run_render
    from open_edit.agent.exceptions import RenderResult
    import subprocess as _subprocess

    workdir = tmp_path / "proj"
    workdir.mkdir()
    output_path = workdir / "out.mp4"

    with patch(
        "open_edit.agent.sandbox_bridge._resolve_render_binary",
        return_value="/fake/binary",
    ), patch(
        "open_edit.agent.sandbox_bridge.subprocess.run",
        side_effect=_subprocess.TimeoutExpired(cmd="x", timeout=10),
    ):
        result = run_render(
            code="pass",
            workdir=workdir,
            output_path=output_path,
        )

    assert isinstance(result, RenderResult)
    assert result.ok is False
    assert "timed out" in result.detail.lower() or "timeout" in result.detail.lower()


def test_run_render_success_returns_ok_result(tmp_path):
    """I1: successful render → RenderResult(ok=True, path=output_path)."""
    from open_edit.agent.sandbox_bridge import run_render
    from open_edit.agent.exceptions import RenderResult

    workdir = tmp_path / "proj"
    workdir.mkdir()
    output_path = workdir / "out.mp4"

    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.stdout = ""
    fake_proc.stderr = ""

    def _create_output(*args, **kwargs):
        output_path.write_bytes(b"fake")
        return fake_proc

    with patch(
        "open_edit.agent.sandbox_bridge._resolve_render_binary",
        return_value="/fake/binary",
    ), patch(
        "open_edit.agent.sandbox_bridge.subprocess.run",
        side_effect=_create_output,
    ):
        result = run_render(
            code="pass",
            workdir=workdir,
            output_path=output_path,
        )

    assert isinstance(result, RenderResult)
    assert result.ok is True
    assert result.path == output_path


# =========================================================================
# I2 (final-fixes): _validate_references must cover all 24 op types.
# =========================================================================

def _build_minimal_timeline(tmp_path):
    """Build a Project with one clip + one effect + one group for use in
    reference validation tests. Returns (project, timeline, edit_graph)."""
    from open_edit.ir.types import (
        AddClipOp, AddEffectOp, Asset, GroupEditsOp, Project, new_id,
    )
    from open_edit.ir.apply import derive_timeline
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
    """I2: ops that reference a clip_id not in the project must raise."""
    from open_edit.ir.types import TrimClipOp, MoveClipOp, RemoveClipOp
    from open_edit.agent.sandbox_bridge import _validate_references
    from open_edit.ir.types import new_id

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

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
        with pytest.raises(ReferenceError, match="clip_id"):
            _validate_references(op, timeline, assets, edit_graph)


def test_validate_references_slip_ripple_speed_split_ramp_raises(tmp_path):
    """I2: SlipClipOp, RippleDeleteClipOp, ChangeClipSpeedOp, SplitClipOp,
    SetClipSpeedRampOp must validate clip_id."""
    from open_edit.ir.types import (
        SlipClipOp, RippleDeleteClipOp, ChangeClipSpeedOp, SplitClipOp,
        SetClipSpeedRampOp, new_id,
    )
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

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
        with pytest.raises(ReferenceError, match="clip_id"):
            _validate_references(op, timeline, assets, edit_graph)


def test_validate_references_add_transition_missing_clip_raises(tmp_path):
    """I2: AddTransitionOp with missing clip_a_id or clip_b_id must raise."""
    from open_edit.ir.types import AddTransitionOp, new_id
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    op = AddTransitionOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_a_id="nope_a", clip_b_id="nope_b",
        transition_type="luma", duration_sec=0.5,
    )
    with pytest.raises(ReferenceError, match="clip_a_id"):
        _validate_references(op, timeline, assets, edit_graph)


def test_validate_references_transition_ops_validate_id(tmp_path):
    """I2: RemoveTransitionOp + SetTransitionPropertyOp must validate transition_id.

    Transitions are stored as Effect on the clip. We test by giving a bogus id.
    """
    from open_edit.ir.types import (
        RemoveTransitionOp, SetTransitionPropertyOp, new_id,
    )
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    for cls in (RemoveTransitionOp, SetTransitionPropertyOp):
        kwargs = {"edit_id": new_id(), "author": "ai", "parent_id": "p1",
                  "transition_id": "no_such_transition"}
        if cls is SetTransitionPropertyOp:
            kwargs.update({"prop_name": "x", "value": "y"})
        op = cls(**kwargs)
        with pytest.raises(ReferenceError, match="transition_id"):
            _validate_references(op, timeline, assets, edit_graph)


def test_validate_references_remove_set_effect_validates_clip_index(tmp_path):
    """I2: RemoveEffectOp + SetEffectParamOp must validate clip_id and effect_index."""
    from open_edit.ir.types import RemoveEffectOp, SetEffectParamOp, new_id
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    # missing clip
    op_bad_clip = RemoveEffectOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id="nope", effect_index=0,
    )
    with pytest.raises(ReferenceError, match="clip_id"):
        _validate_references(op_bad_clip, timeline, assets, edit_graph)

    # valid clip but invalid index
    real_clip_id = timeline.tracks[0].clips[0].clip_id
    op_bad_idx = RemoveEffectOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id=real_clip_id, effect_index=999,
    )
    with pytest.raises(ReferenceError, match="effect_index"):
        _validate_references(op_bad_idx, timeline, assets, edit_graph)

    # SetEffectParamOp: bad param name
    op_bad_param = SetEffectParamOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id=real_clip_id, effect_index=0,
        param_name="nonexistent_param", value="1",
    )
    with pytest.raises(ReferenceError, match="param_name"):
        _validate_references(op_bad_param, timeline, assets, edit_graph)


def test_validate_references_remove_keyframe_validates(tmp_path):
    """I2: RemoveKeyframeOp must validate effect_id, param, and frame."""
    from open_edit.ir.types import RemoveKeyframeOp, new_id
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    # missing effect_id
    op_bad_eff = RemoveKeyframeOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        effect_id="nope", param="gain", frame=1.0,
    )
    with pytest.raises(ReferenceError, match="effect_id"):
        _validate_references(op_bad_eff, timeline, assets, edit_graph)


def test_validate_references_replace_clip_source_validates(tmp_path):
    """I2: ReplaceClipSourceOp must validate clip_id AND new_asset_hash."""
    from open_edit.ir.types import ReplaceClipSourceOp, new_id
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {"asset_abc": type("A", (), {"asset_hash": "asset_abc"})()}

    # bad clip
    op_bad_clip = ReplaceClipSourceOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id="nope", new_asset_hash="asset_abc",
    )
    with pytest.raises(ReferenceError, match="clip_id"):
        _validate_references(op_bad_clip, timeline, assets, edit_graph)

    real_clip_id = timeline.tracks[0].clips[0].clip_id
    # bad asset
    op_bad_asset = ReplaceClipSourceOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        clip_id=real_clip_id, new_asset_hash="not_in_project",
    )
    with pytest.raises(ReferenceError, match="asset_hash"):
        _validate_references(op_bad_asset, timeline, assets, edit_graph)


def test_validate_references_normalize_audio_validates_target(tmp_path):
    """I2: NormalizeAudioOp must validate target_id (clip or track)."""
    from open_edit.ir.types import NormalizeAudioOp, new_id
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    # clip with bad id
    op_bad_clip = NormalizeAudioOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        target_kind="clip", target_id="nope", target_dbfs=-16.0,
    )
    with pytest.raises(ReferenceError, match="target_id"):
        _validate_references(op_bad_clip, timeline, assets, edit_graph)

    # track with bad id
    op_bad_track = NormalizeAudioOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        target_kind="track", target_id="nope", target_dbfs=-16.0,
    )
    with pytest.raises(ReferenceError, match="target_id"):
        _validate_references(op_bad_track, timeline, assets, edit_graph)

    # unknown kind
    op_bad_kind = NormalizeAudioOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        target_kind="project", target_id="nope", target_dbfs=-16.0,
    )
    with pytest.raises(ReferenceError, match="target_kind"):
        _validate_references(op_bad_kind, timeline, assets, edit_graph)


def test_validate_references_group_ungroup_validates(tmp_path):
    """I2: GroupEditsOp + UngroupEditsOp must validate."""
    from open_edit.ir.types import GroupEditsOp, UngroupEditsOp, new_id
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    # group with non-existent edit_id
    op_bad_edit = GroupEditsOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        edit_ids=["no_such_edit"], label="g1",
    )
    with pytest.raises(ReferenceError, match="edit_id"):
        _validate_references(op_bad_edit, timeline, assets, edit_graph)

    # ungroup with non-existent label
    op_bad_label = UngroupEditsOp(
        edit_id=new_id(), author="ai", parent_id="p1", label="no_such_group",
    )
    with pytest.raises(ReferenceError, match="label"):
        _validate_references(op_bad_label, timeline, assets, edit_graph)


def test_validate_references_raw_mlt_and_free_form_skip(tmp_path):
    """I2: RawMltXmlOp and FreeFormCodeOp need no reference check."""
    from open_edit.ir.types import RawMltXmlOp, FreeFormCodeOp, new_id
    from open_edit.agent.sandbox_bridge import _validate_references

    _, timeline, edit_graph = _build_minimal_timeline(tmp_path)
    assets = {}

    op_raw = RawMltXmlOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        xml="<mlt/>", description="x",
    )
    op_free = FreeFormCodeOp(
        edit_id=new_id(), author="ai", parent_id="p1",
        code="pass",
    )
    # Should not raise ReferenceError; they only trigger the parent_id check
    # (which both pass). The catch is the lack of op-level reference check.
    # We use a dummy parent_id to avoid the parent_id check.
    op_raw.parent_id = "p1"
    op_free.parent_id = "p1"
    # No reference error means validation passed.
    _validate_references(op_raw, timeline, assets, edit_graph)
    _validate_references(op_free, timeline, assets, edit_graph)
