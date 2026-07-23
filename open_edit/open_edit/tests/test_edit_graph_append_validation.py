import pytest
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.ir.validate import OpValidationError, TimelineValidationError
from open_edit.ir.types import TrimClipOp, AddClipOp, SplitClipOp, Project
from open_edit.ir.apply import derive_or_load_timeline


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


def test_append_add_clip_with_ingested_asset_persists(tmp_path):
    # Regression: an AddClipOp referencing a freshly-created asset (not yet
    # referenced by any existing op) must pass validate_op_for_append and
    # persist. Mirrors tests/conftest.py's tmp_project_with_assets fixture:
    # seed a real CAS asset + sidecar so AssetStore.get() returns it.
    from open_edit.ir.types import Asset
    from open_edit.storage.assets import AssetStore

    asset = Asset(
        asset_hash="feedface",
        original_path="/tmp/clip.mp4",
        stored_path="",
        type="video",
        duration_sec=10.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
    )
    asset_store = AssetStore(tmp_path / "assets")
    cas_file = asset_store._cas_path(asset.asset_hash)
    cas_file.parent.mkdir(parents=True, exist_ok=True)
    cas_file.write_bytes(b"\x00")
    asset.stored_path = str(cas_file)
    asset_store._sidecar_path(asset.asset_hash).write_text(
        asset.model_dump_json(indent=2)
    )

    store = EditGraphStore(tmp_path / "edit_graph.db")
    op = AddClipOp(
        author="user",
        asset_hash=asset.asset_hash,
        track_id="video_main",
        position_sec=0.0,
        in_point_sec=0.0,
        out_point_sec=asset.duration_sec,
    )
    n = store.append(op)  # must not raise OpValidationError
    assert n == 0
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0].edit_id == op.edit_id
    assert loaded[0].asset_hash == asset.asset_hash


def test_append_valid_op_persists(monkeypatch, tmp_path):
    from open_edit.ir import validate as _v
    # Isolate append's own persist path from asset/catalog checks.
    monkeypatch.setattr(_v, "validate_op_for_append", lambda op, s: [])
    store = EditGraphStore(tmp_path / "edit_graph.db")
    op = AddClipOp(asset_hash="h", track_id="V1", position_sec=0.0, author="ai")
    n = store.append(op)
    assert n == 0
    assert store.load_all()[0].clip_id == op.clip_id


def test_render_derive_strict_rejects_overlap(tmp_path):
    store = EditGraphStore(tmp_path / "edit_graph.db")
    store.append(AddClipOp(asset_hash="h", track_id="V1", position_sec=0.0,
                           in_point_sec=0.0, out_point_sec=5.0, author="ai"))
    store.append(AddClipOp(asset_hash="h", track_id="V1", position_sec=4.0,
                           in_point_sec=0.0, out_point_sec=5.0, author="ai"))
    ops = store.load_all()
    proj = Project(project_id="p", name="p", workdir=tmp_path, assets={}, edit_graph=ops)
    with pytest.raises(TimelineValidationError):
        derive_or_load_timeline(proj, store, strict=True)


def test_append_split_then_trim_half_passes(tmp_path):
    # SplitClipOp creates left/right clip ids during timeline replay; a
    # follow-up op targeting the split half must not be rejected at the door.
    store = EditGraphStore(tmp_path / "edit_graph.db")
    c1 = AddClipOp(asset_hash="h", track_id="V1", position_sec=0.0,
                   in_point_sec=0.0, out_point_sec=10.0, author="ai")
    split = SplitClipOp(clip_id=c1.clip_id, at_sec=5.0, author="ai")
    trim = TrimClipOp(clip_id=split.left_clip_id, new_in_point_sec=0.0,
                     new_out_point_sec=3.0, author="ai")
    store.append(c1)
    store.append(split)
    n = store.append(trim)  # must not raise
    assert n == 2
    assert store.load_all()[2].clip_id == trim.clip_id

