"""Edit-graph ordering operations.

The reorder/delete family rewrites ``edits.sequence_num``. These mutate the
graph, so any cached timeline snapshot for the project is invalidated in the
same transaction (Task 6.5 refines the invalidation strategy).
"""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from open_edit.storage.edit_graph import EditGraphStore


def _invalidate_project_snapshots(conn: sqlite3.Connection, store: EditGraphStore) -> None:
    """Delete cached timeline snapshot rows for the project (one db per project)."""
    row = conn.execute(
        "SELECT value FROM project_meta WHERE key = 'project_id'"
    ).fetchone()
    project_id = row[0] if row is not None else store.project_id
    conn.execute(
        "DELETE FROM timeline_snapshots WHERE project_id = ?", (project_id,)
    )


def delete_op(
    store: EditGraphStore, edit_id: str, expected_revision: int | None = None,
) -> bool:
    """Remove an operation from the edit graph by id.

    Any ops that had ``parent_id == edit_id`` get their parent_id
    cleared (set to NULL) so the graph remains consistent.
    Returns True if an op was found and deleted.
    """
    with store._conn() as conn:
        cur = conn.execute(
            "SELECT edit_id FROM edits WHERE edit_id = ?", (edit_id,)
        )
        if cur.fetchone() is None:
            return False
        conn.execute(
            "UPDATE edits SET parent_id = NULL WHERE parent_id = ?",
            (edit_id,),
        )
        conn.execute(
            "DELETE FROM edits WHERE edit_id = ?", (edit_id,)
        )
        _invalidate_project_snapshots(conn, store)
        store._check_and_bump_revision(conn, expected_revision)
    return True


def move_arbitrary(
    store: EditGraphStore, edit_id: str, new_sequence_num: int,
    expected_revision: int | None = None,
) -> bool:
    """Move an operation to any position in the sequence.

    This is a general reorder operation (not just adjacent swap).
    Returns True if the op was found and moved.
    """
    with store._conn() as conn:
        cur = conn.execute(
            "SELECT sequence_num FROM edits WHERE edit_id = ?",
            (edit_id,),
        )
        row = cur.fetchone()
        if row is None:
            return False
        old_pos = row[0]
        if old_pos == new_sequence_num:
            return True
        if old_pos < new_sequence_num:
            conn.execute(
                "UPDATE edits SET sequence_num = sequence_num - 1 "
                "WHERE sequence_num > ? AND sequence_num <= ?",
                (old_pos, new_sequence_num),
            )
        else:
            conn.execute(
                "UPDATE edits SET sequence_num = sequence_num + 1 "
                "WHERE sequence_num >= ? AND sequence_num < ?",
                (new_sequence_num, old_pos),
            )
        conn.execute(
            "UPDATE edits SET sequence_num = ? WHERE edit_id = ?",
            (new_sequence_num, edit_id),
        )
        _invalidate_project_snapshots(conn, store)
        store._check_and_bump_revision(conn, expected_revision)
    return True


def reorder_all(
    store: EditGraphStore, edit_ids: list[str],
    expected_revision: int | None = None,
) -> int:
    """Atomically replace the complete edit ordering.

    Callers must supply every edit exactly once.  Validating the
    permutation before changing any sequence number prevents partial
    reorder state when a browser sends a duplicate, omits an operation,
    or contains an unknown id.
    """
    if len(edit_ids) != len(set(edit_ids)):
        raise ValueError("reorder contains duplicate edit IDs")
    with store._conn() as conn:
        rows = conn.execute("SELECT edit_id FROM edits ORDER BY sequence_num").fetchall()
        existing = [row[0] for row in rows]
        if set(edit_ids) != set(existing) or len(edit_ids) != len(existing):
            missing = sorted(set(existing) - set(edit_ids))
            unknown = sorted(set(edit_ids) - set(existing))
            details = []
            if missing:
                details.append(f"missing IDs: {', '.join(missing)}")
            if unknown:
                details.append(f"unknown IDs: {', '.join(unknown)}")
            raise ValueError("reorder must be a complete permutation (" + "; ".join(details) + ")")
        # A two-phase update avoids transient duplicate sequence numbers
        # if a future schema makes sequence_num unique.
        offset = len(existing) + 1
        for index, edit_id in enumerate(edit_ids):
            conn.execute("UPDATE edits SET sequence_num = ? WHERE edit_id = ?", (offset + index, edit_id))
        for index, edit_id in enumerate(edit_ids):
            conn.execute("UPDATE edits SET sequence_num = ? WHERE edit_id = ?", (index, edit_id))
        _invalidate_project_snapshots(conn, store)
        return store._check_and_bump_revision(conn, expected_revision)


def reorder(
    store: EditGraphStore, edit_id_a: str, edit_id_b: str,
    expected_revision: int | None = None,
) -> int:
    """Swap the sequence_num of two adjacent operations.

    Raises ValueError if either id does not exist or if the two ops
    are not adjacent in sequence_num.
    """
    with store._conn() as conn:
        cur = conn.execute(
            "SELECT edit_id, sequence_num FROM edits "
            "WHERE edit_id IN (?, ?) ORDER BY sequence_num",
            (edit_id_a, edit_id_b),
        )
        rows = cur.fetchall()
        if len(rows) != 2:
            raise ValueError(f"Both edits must exist; got {len(rows)} rows")
        (id1, seq1), (id2, seq2) = rows
        if abs(seq1 - seq2) != 1:
            raise ValueError(
                f"Edits must be adjacent to reorder; "
                f"got sequence_num gap {abs(seq1 - seq2)}"
            )
        conn.execute(
            "UPDATE edits SET sequence_num = ? WHERE edit_id = ?",
            (seq2, id1),
        )
        conn.execute(
            "UPDATE edits SET sequence_num = ? WHERE edit_id = ?",
            (seq1, id2),
        )
        _invalidate_project_snapshots(conn, store)
        return store._check_and_bump_revision(conn, expected_revision)
