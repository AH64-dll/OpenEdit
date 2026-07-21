"""Per-project metadata accessors for the open_edit server.

v1.5 added the ``verify_disabled`` opt-out flag. The flag is stored in
the ``project_meta`` table of ``edit_graph.db`` and read by the agent
loop to decide whether to run the visual verification stage. This
module is the single read-side accessor; the storage-side lives in
``open_edit.storage.edit_graph.EditGraphStore``.
"""
from __future__ import annotations

from pathlib import Path


def is_verify_disabled(project_path: Path) -> bool:
    """Return True if the project's ``verify_disabled`` flag is set.

    Reads from the ``project_meta`` table in ``edit_graph.db``. Returns
    False for projects where the DB doesn't exist (fresh project) or the
    flag isn't set.
    """
    db = project_path / ".open_edit" / "edit_graph.db"
    if not db.exists():
        return False
    try:
        from open_edit.storage.edit_graph import EditGraphStore
        meta = EditGraphStore(db).get_project_meta()
        return bool(int(meta.get("verify_disabled", 0)))
    except Exception:
        return False
