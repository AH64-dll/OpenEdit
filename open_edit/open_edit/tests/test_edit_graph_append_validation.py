import pytest
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.ir.validate import OpValidationError
from open_edit.ir.types import TrimClipOp, AddClipOp


def test_append_dangling_reference_rejected(tmp_path):
    store = EditGraphStore(tmp_path / "edit_graph.db")
    # TrimClipOp references a clip_id that does not exist in the project.
    op = TrimClipOp(
        clip_id="does_not_exist", new_in_point_sec=0.0,
        new_out_point_sec=1.0, author="ai",
    )
    with pytest.raises(OpValidationError):
        store.append(op)
    # Nothing was written.
    assert store.load_all() == []


def test_append_valid_op_persists(monkeypatch, tmp_path):
    from open_edit.ir import validate as _v
    # Isolate append's own persist path from asset/catalog checks.
    monkeypatch.setattr(_v, "validate_op_for_append", lambda op, s: [])
    store = EditGraphStore(tmp_path / "edit_graph.db")
    op = AddClipOp(asset_hash="h", track_id="V1", position_sec=0.0, author="ai")
    n = store.append(op)
    assert n == 0
    assert store.load_all()[0].clip_id == op.clip_id
