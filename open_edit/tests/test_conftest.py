"""T1: Conftest fixture sanity check.

The fixture must produce on-disk state that run_free_form's
_load_assets_via_store can discover:

  1. edit_graph.db is seeded with an AddClipOp referencing the asset
     (so the asset_hash set is non-empty).
  2. <assets_dir>/<hash[:2]>/<hash> exists (the CAS file).
  3. <assets_dir>/<hash[:2]>/<hash>.meta.json exists (the sidecar
     JSON, so AssetStore.get() returns full metadata without ffprobe).

The real RED test is the e2e suite (4 of 5 tests fail at the first
ir.add_clip() call if the on-disk seed is missing). Those tests skip
in this dev env (bwrap missing); the assertions below are the local
sanity check that the fixture still produces the expected on-disk
state.
"""
from open_edit.ir.types import AddClipOp
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


def test_fixture_persists_on_disk_state(tmp_project_with_assets):
    """Fixture writes CAS asset + sidecar + edit_graph entry to disk."""
    project = tmp_project_with_assets

    # 1. edit_graph.db has the seed AddClipOp (drives asset_hash discovery).
    graph = EditGraphStore(project.workdir / "edit_graph.db")
    ops = graph.load_all()
    seed = next((op for op in ops if isinstance(op, AddClipOp)), None)
    assert seed is not None, (
        f"edit_graph.db has no AddClipOp; got ops: {ops!r}. "
        f"_load_assets_via_store scans prior AddClipOps to discover "
        f"asset hashes, so an empty edit graph leaves assets=dict empty."
    )

    # 2. <assets_dir>/<hash[:2]>/<hash> exists.
    assets_dir = project.workdir / "assets"
    h = seed.asset_hash
    cas_file = assets_dir / h[:2] / h
    assert cas_file.exists(), f"CAS file missing: {cas_file}"

    # 3. Sidecar JSON lets AssetStore.get() return full metadata.
    sidecar = assets_dir / h[:2] / f"{h}.meta.json"
    assert sidecar.exists(), f"sidecar JSON missing: {sidecar}"
    assert AssetStore(assets_dir).get(h) is not None
