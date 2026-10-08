"""Real subprocess end-to-end tests for free-form edits."""
import textwrap


def test_pyagent_run_python_50_lines(tmp_project_with_assets):
    """The design's "Done when" criterion: 50-line script -> 50 child ops."""
    from open_edit.agent.script_runner import run_free_form
    from open_edit.ir.types import AddClipOp
    code = textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        for i in range(50):
            ir.add_clip(
                asset_hash="abc123",
                track_id="video_main",
                position_sec=i * 2.0,
            )
    ''')
    result = run_free_form(
        code, tmp_project_with_assets.workdir,
        project_id=tmp_project_with_assets.project_id,
        parent_op_id="e1",
    )
    assert result.success, f"free-form failed: {result.reason}: {result.detail}"
    assert len(result.ops) == 50
    assert all(o.parent_id == "e1" for o in result.ops)
    assert all(isinstance(o, AddClipOp) for o in result.ops)
    assert [o.position_sec for o in result.ops] == [i * 2.0 for i in range(50)]


def test_chained_ops_succeed(tmp_project_with_assets):
    """L4: covers C6 -- `ir.add_clip(...)` returns cid, `ir.trim_clip(cid, ...)` works."""
    from open_edit.agent.script_runner import run_free_form
    from open_edit.ir.types import AddClipOp, TrimClipOp
    code = textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        cid = ir.add_clip(asset_hash="abc123", track_id="video_main", position_sec=0.0)
        ir.trim_clip(cid, in_point_sec=1.0, out_point_sec=2.0)
    ''')
    result = run_free_form(
        code, tmp_project_with_assets.workdir,
        project_id=tmp_project_with_assets.project_id,
        parent_op_id="e1",
    )
    assert result.success, f"free-form failed: {result.reason}: {result.detail}"
    assert len(result.ops) == 2
    assert isinstance(result.ops[0], AddClipOp)
    assert isinstance(result.ops[1], TrimClipOp)
    assert result.ops[1].clip_id == result.ops[0].clip_id


def test_free_form_then_render(tmp_project_with_assets):
    """L2: free-form + full render produces a non-empty mlt xml string."""
    from open_edit.agent.script_runner import run_free_form
    from open_edit.ir.derive import derive_timeline
    from open_edit.render.emitter import emit_timeline
    code = textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        for i in range(5):
            ir.add_clip(
                asset_hash="abc123", track_id="video_main",
                position_sec=i * 2.0,
            )
    ''')
    result = run_free_form(
        code, tmp_project_with_assets.workdir,
        project_id=tmp_project_with_assets.project_id,
        parent_op_id="e1",
    )
    assert result.success, f"free-form failed: {result.reason}: {result.detail}"
    tmp_project_with_assets.edit_graph.extend(result.ops)
    timeline = derive_timeline(tmp_project_with_assets)
    xml = emit_timeline(timeline)
    assert '<mlt' in xml or '<tractor>' in xml or '<playlist>' in xml  # sanity check


def test_free_form_failure_does_not_corrupt_graph(tmp_project_with_assets):
    """L3: a free-form script that raises an exception does NOT corrupt the graph."""
    from open_edit.agent.script_runner import run_free_form
    pre_ops = list(tmp_project_with_assets.edit_graph)
    code = textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        ir.add_clip(asset_hash="abc123", track_id="video_main", position_sec=0.0)
        raise RuntimeError("boom")
    ''')
    result = run_free_form(
        code, tmp_project_with_assets.workdir,
        project_id=tmp_project_with_assets.project_id,
        parent_op_id="e1",
    )
    assert not result.success
    # Graph is unchanged (atomic commit)
    assert list(tmp_project_with_assets.edit_graph) == pre_ops
    # No ops.jsonl files left behind
    sandbox_dir = tmp_project_with_assets.workdir / ".script-runs"
    if sandbox_dir.exists():
        for run_dir in sandbox_dir.iterdir():
            assert not (run_dir / "ops.jsonl").exists()
