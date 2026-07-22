from open_edit.ir.types import Project, AddClipOp
from open_edit.ir.apply import derive_timeline

def test_project_can_be_created():
    p = Project(name="test")
    assert p.name == "test"
    assert p.project_id is not None
    assert p.edit_graph == []

def test_add_clip_op_produces_timeline():
    op = AddClipOp(
        edit_id="e1",
        author="ai",
        timestamp="2026-01-01T00:00:00",
        asset_hash="abc123",
        track_id="t1",
        position_sec=0.0,
        in_point_sec=0.0,
        out_point_sec=10.0,
    )
    project = Project(name="test", edit_graph=[op])
    result = derive_timeline(project)
    assert result is not None
    assert len(result.tracks) > 0

def test_empty_ops_returns_empty_timeline():
    result = derive_timeline(Project(name="test"))
    assert result is not None
    assert len(result.tracks) == 0
