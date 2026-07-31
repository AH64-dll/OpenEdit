"""Shared edit-graph mutation service for AI tools and the manual UI.

All interactive timeline commands go through this module so UI and agent
mutations share the same validation, author tagging, and revision checks.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from open_edit.ir.types import (
    AddClipOp,
    MoveClipOp,
    RemoveClipOp,
    SplitClipOp,
    TrimClipOp,
    new_id,
)
from open_edit.ir.validate import OpValidationError
from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict
from open_edit.storage.paths import ProjectPaths

CommandName = Literal[
    "add_clip",
    "move_clip",
    "trim_clip",
    "split_clip",
    "remove_clip",
    "change_track",
]


class EditGraphCommandError(ValueError):
    """User-facing command validation failure."""


def open_store(project_path: Path) -> EditGraphStore:
    db = ProjectPaths.for_project(project_path).db_path
    if not db.exists():
        raise EditGraphCommandError("edit graph not found")
    return EditGraphStore(db)


def apply_command(
    project_path: Path,
    command: str,
    params: dict[str, Any],
    *,
    author: Literal["ai", "user"] = "user",
    expected_revision: int | None = None,
    parent_id: str | None = None,
) -> dict[str, Any]:
    """Append one validated timeline command and return the new revision."""
    if command not in (
        "add_clip", "move_clip", "trim_clip", "split_clip", "remove_clip", "change_track",
    ):
        raise EditGraphCommandError(f"unsupported command: {command!r}")

    store = open_store(project_path)
    op = _build_op(command, params, author=author, parent_id=parent_id)
    try:
        sequence_num = store.append(op, expected_revision=expected_revision)
    except GraphRevisionConflict:
        raise
    except OpValidationError as exc:
        raise EditGraphCommandError(str(exc)) from exc

    revision = store.graph_revision()
    return {
        "edit_id": op.edit_id,
        "kind": op.kind,
        "sequence_num": sequence_num,
        "graph_revision": revision,
        "op": op.model_dump(mode="json"),
    }


def _build_op(
    command: str,
    params: dict[str, Any],
    *,
    author: Literal["ai", "user"],
    parent_id: str | None,
) -> Any:
    pid = parent_id  # None is valid for root ops
    if command == "add_clip":
        asset_hash = str(params.get("asset_hash") or "").strip()
        track_id = str(params.get("track_id") or "V1").strip() or "V1"
        if not asset_hash:
            raise EditGraphCommandError("asset_hash is required")
        try:
            position_sec = float(params.get("position_sec", 0.0))
            in_point_sec = float(params.get("in_point_sec", 0.0))
        except (TypeError, ValueError) as exc:
            raise EditGraphCommandError("position_sec and in_point_sec must be numbers") from exc
        out_raw = params.get("out_point_sec")
        out_point_sec = float(out_raw) if out_raw is not None else None
        return AddClipOp(
            edit_id=new_id(),
            author=author,
            parent_id=pid,
            asset_hash=asset_hash,
            track_id=track_id,
            position_sec=position_sec,
            in_point_sec=in_point_sec,
            out_point_sec=out_point_sec,
            clip_id=str(params.get("clip_id") or new_id()),
        )

    clip_id = str(params.get("clip_id") or "").strip()
    if not clip_id:
        raise EditGraphCommandError("clip_id is required")

    if command == "move_clip" or command == "change_track":
        new_track_id = str(params.get("new_track_id") or "").strip()
        if not new_track_id:
            raise EditGraphCommandError("new_track_id is required")
        try:
            new_position_sec = float(params.get("new_position_sec", 0.0))
        except (TypeError, ValueError) as exc:
            raise EditGraphCommandError("new_position_sec must be a number") from exc
        return MoveClipOp(
            edit_id=new_id(),
            author=author,
            parent_id=pid,
            clip_id=clip_id,
            new_track_id=new_track_id,
            new_position_sec=new_position_sec,
        )

    if command == "trim_clip":
        try:
            new_in = float(params["in_point_sec"])
            new_out = float(params["out_point_sec"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EditGraphCommandError("in_point_sec and out_point_sec are required numbers") from exc
        return TrimClipOp(
            edit_id=new_id(),
            author=author,
            parent_id=pid,
            clip_id=clip_id,
            new_in_point_sec=new_in,
            new_out_point_sec=new_out,
        )

    if command == "split_clip":
        try:
            at_sec = float(params["at_sec"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EditGraphCommandError("at_sec is required") from exc
        return SplitClipOp(
            edit_id=new_id(),
            author=author,
            parent_id=pid,
            clip_id=clip_id,
            at_sec=at_sec,
        )

    if command == "remove_clip":
        return RemoveClipOp(
            edit_id=new_id(),
            author=author,
            parent_id=pid,
            clip_id=clip_id,
        )

    raise EditGraphCommandError(f"unsupported command: {command!r}")
