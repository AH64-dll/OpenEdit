"""Shared staging / collect / cleanup for free-form sandbox runs.

Both backends stage a scratch dir with ``code.py`` + ``_bootstrap.py``,
invoke their executor, validate ``ops.jsonl`` against a working-copy
timeline, and remove the scratch dir on every code path. ``stage_and_collect``
owns that lifecycle so the two backends cannot drift apart (they were ~90%
duplicated before Task 5.4).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable

from open_edit.agent.exceptions import FreeFormResult, _ValidationError
from open_edit.ir.apply import apply_operation
from open_edit.ir.derive import derive_timeline
from open_edit.ir.types import (
    Asset, OperationUnion, Project, new_id,
)
from open_edit.ir.validate import OpValidationError, validate_op_references
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.paths import ProjectPaths
from pydantic import TypeAdapter


class _FlushingBuffer(list):
    """A list that writes each appended op to disk before keeping it.

    H10: write FIRST, then append. If the file write fails, raise immediately
    so the whole run aborts; no silent loss.
    """
    def __init__(self, ops_file: Path):
        super().__init__()
        self._ops_file = Path(ops_file)

    def append(self, op):
        with open(self._ops_file, "a") as f:
            f.write(op.model_dump_json() + "\n")
        super().append(op)


def _assets_dir_for_workdir(workdir: Path) -> Path:
    """Return the asset-store directory for a sandbox workdir.

    The workdir is whichever directory contains ``edit_graph.db``
    (``<root>/.open_edit`` canonical, ``<root>`` legacy); the project
    root and its canonical asset CAS are derived via ``ProjectPaths``.
    A legacy ``<workdir>/assets`` store is honored when present.
    """
    direct = workdir / "assets"
    if direct.is_dir():
        return direct
    return ProjectPaths.for_workdir(workdir).assets_dir


def stage_and_collect(
    *,
    workdir: Path,
    code: str,
    render_bootstrap: Callable[[Path], str],
    execute: Callable[[Path, Path, Path, Path], tuple[FreeFormResult | None, float]],
) -> FreeFormResult:
    """Stage ``code.py`` + ``_bootstrap.py`` into a fresh scratch dir, run
    the backend-specific executor, validate ``ops.jsonl``, and remove the
    scratch dir on every code path (6a).

    ``render_bootstrap(ops_path)`` returns the bootstrap source for the
    scratch dir (the dev backend overrides the in-sandbox ops path with the
    real host scratch path).

    ``execute(scratch, code_path, ops_path, bootstrap_path)`` runs the
    sandbox and returns ``(override, duration_s)``:
    - ``override`` is returned as-is when non-None (failure / early exit);
      ``None`` proceeds to ops.jsonl collection.
    - ``duration_s`` is used for the success result.
    """
    run_id = new_id()
    scratch = workdir / '.sandbox' / f'run_{run_id}'
    try:
        scratch.mkdir(parents=True, exist_ok=True)
        code_path = scratch / 'code.py'
        ops_path = scratch / 'ops.jsonl'
        bootstrap_path = scratch / '_bootstrap.py'

        code_path.write_text(code)
        bootstrap_path.write_text(render_bootstrap(ops_path))

        override, duration_s = execute(scratch, code_path, ops_path, bootstrap_path)
        if override is not None:
            return override

        if not ops_path.exists():
            return FreeFormResult.ok(ops=[], duration_s=0.0)

        try:
            ops, _ = _validate_ops_incrementally(ops_path, workdir)
        except _ValidationError as e:
            return FreeFormResult.fail("invalid_op", str(e))

        return FreeFormResult.ok(ops=ops, duration_s=duration_s)
    finally:
        # 6a: remove the scratch dir on every code path. Each successful
        # free-form run otherwise leaves ~3 staged files (code.py,
        # _bootstrap.py, ops.jsonl) on disk forever under
        # <workdir>/.sandbox/.
        shutil.rmtree(scratch, ignore_errors=True)


def _validate_ops_incrementally(ops_path: Path, workdir: Path) -> tuple[list, object]:
    """C6: validate each op against a working-copy timeline, then apply.

    Reference validation is delegated to
    ``open_edit.ir.validate.validate_op_references(op, project, strict=True)``
    (Task 3.4: the sandbox no longer owns a second reference checker). The
    growing working timeline is passed in so a batch op may reference a clip
    created earlier in the SAME batch; group labels / edit ids are still
    resolved against the stored graph, exactly as before. Violations surface
    as ``OpValidationError`` (the IR layer's reference-error type) wrapped in
    a line-numbered ``_ValidationError``.
    """
    try:
        project = _load_project_for_validation(workdir)
    except Exception as e:
        raise _ValidationError(f"project load failed: {e}") from e

    timeline = derive_timeline(project)
    ops: list[OperationUnion] = []
    for line_num, line in enumerate(ops_path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            op = TypeAdapter(OperationUnion).validate_python(json.loads(line))
            errors = validate_op_references(op, project, strict=True, timeline=timeline)
            if errors:
                raise OpValidationError("; ".join(errors))
            timeline = apply_operation(timeline, op)
            ops.append(op)
        except Exception as e:
            raise _ValidationError(f"line {line_num}: {e}") from e
    return ops, timeline


def _load_project_for_validation(workdir: Path) -> Project:
    db_path = workdir / 'edit_graph.db'
    if not db_path.exists():
        raise _ValidationError(f"project db not found: {db_path}")
    store = EditGraphStore(db_path)
    assets = _load_assets_via_store(store, workdir)
    return Project(
        project_id=store.project_id,
        name=workdir.name,
        workdir=workdir,
        assets=assets,
        edit_graph=store.load_all(),
    )


def _load_assets_via_store(store: EditGraphStore, workdir: Path) -> dict[str, Asset]:
    """Build ``project.assets`` from every asset physically present in the
    store's on-disk sidecars.

    Previously this only included asset hashes already referenced by an
    existing ``add_clip`` op, which created a chicken-and-egg: the first
    clip for a freshly imported asset could never validate because
    ``project.assets`` was empty. Loading the full inventory lets any
    ingested asset be used immediately.
    """
    assets_dir = _assets_dir_for_workdir(workdir)
    if not assets_dir.exists():
        return {}
    assets: dict[str, Asset] = {}
    for meta in assets_dir.rglob("*.meta.json"):
        try:
            asset = Asset.model_validate_json(meta.read_text())
        except Exception:
            continue
        assets[asset.asset_hash] = asset
    return assets
