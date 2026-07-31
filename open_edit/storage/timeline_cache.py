"""Timeline snapshot cache policy over an ``EditGraphStore``.

``derive_or_load_timeline`` returns a project's Timeline, using a cached
snapshot when the edit graph's canonical hash matches a stored one. The
store is duck-typed (any object with ``load_timeline_snapshot`` /
``save_timeline_snapshot``); any storage error degrades gracefully to a
fresh derive.
"""
from __future__ import annotations

import contextlib

from open_edit.ir.derive import derive_timeline
from open_edit.ir.hash import compute_edit_graph_hash
from open_edit.ir.types import Project, Timeline


def derive_or_load_timeline(project: Project, store=None, strict: bool = False) -> Timeline:
    """Return the Timeline for ``project``, using a cached snapshot when the
    edit graph's canonical hash matches a stored snapshot.

    If ``store`` (an EditGraphStore) is provided and a snapshot exists for the
    current ``compute_edit_graph_hash(project.edit_graph)``, deserialize and
    return it. Otherwise derive via ``derive_timeline``, and if ``store`` is
    given, persist the snapshot keyed by that hash. If ``store`` is None,
    always derive. Any storage error degrades gracefully to a fresh derive.
    """
    h = compute_edit_graph_hash(project.edit_graph)

    if store is not None:
        try:
            snap = store.load_timeline_snapshot(h)
            if snap is not None:
                return Timeline.model_validate_json(snap)
        except Exception:
            pass

    tl = derive_timeline(project, strict=strict)

    if store is not None:
        with contextlib.suppress(Exception):
            store.save_timeline_snapshot(h, project.project_id, tl.model_dump_json())

    return tl
