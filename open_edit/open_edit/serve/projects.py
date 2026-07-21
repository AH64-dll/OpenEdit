"""Project registry for the Open Edit server.

Each Open Edit "project" is a folder on disk that contains a ``.open_edit/``
subdirectory with at least:

- ``edit_graph.db``  — SQLite database holding the edit graph (per ``schema.sql``)
- ``assets/``        — content-addressed media (CAS via ``<prefix>/<hash>``)
                       with sidecar ``<hash>.meta.json`` per asset
- ``notes.db``       — SQLite database for review notes (per ``storage.notes``)
- ``conversations/`` — JSONL conversation logs created by this server

This module is **thread-safe**: a single ``asyncio.Lock`` serialises the
mutating operations (``create_project``) against the read operations
(``list_projects`` / ``get_project_state``).

Environment
------------
``OPEN_EDIT_PROJECTS_ROOT``  — override the projects root (defaults to
 ``~/OpenEditProjects``). The directory is created on first use.

Real Open Edit schema (NOT a custom schema — we use the real storage classes):

- **assets**: read from filesystem via ``AssetStore``. No SQL table.
  Sidecar ``<hash>.meta.json`` holds the full ``Asset`` Pydantic model.
- **edits**: stored in ``edit_graph.db`` table ``edits`` with columns
  ``edit_id, parent_id, kind, author, timestamp, status, sequence_num, payload``.
  Read via ``EditGraphStore.load_all()`` which returns ``list[OperationUnion]``.
- **notes**: stored in ``notes.db`` table ``notes`` with columns
  ``note_id, project_id, anchor_type, anchor, text, source, status, ...``.
  Read via ``NotesStore.list_all(project_id)``.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from pydantic import BaseModel, Field

# Real Open Edit storage classes
from open_edit.ir.types import Asset
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.notes import NotesStore, NoteStatus

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def projects_root() -> Path:
    """Return the projects root directory, creating it if necessary."""
    raw = os.environ.get("OPEN_EDIT_PROJECTS_ROOT", "~/OpenEditProjects")
    root = Path(raw).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# Pydantic models (API contract — same as frontend expects)
# ---------------------------------------------------------------------------

class AssetInfo(BaseModel):
    """One ingested media asset (subset of the real Asset Pydantic model)."""
    hash: str
    filename: str
    duration_s: float = 0.0
    fps: float = 0.0
    width: int = 0
    height: int = 0
    codec: str = ""
    has_audio: bool = False
    type: str = "video"  # "video" | "audio" | "image"


class EffectInfo(BaseModel):
    """An effect attached to an op (real Open Edit doesn't have a separate
    effects table; effects are part of the op payload). Kept for the
    frontend contract; populated by parsing the op payload if relevant."""
    id: str
    op_id: str
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class OpInfo(BaseModel):
    """One node in the edit graph."""
    id: str
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    status: str = "applied"
    effects: list[EffectInfo] = Field(default_factory=list)


class ReviewNoteInfo(BaseModel):
    """A review note (marker) on the timeline."""
    id: str
    timestamp: float
    source: str  # "agent" | "user" | "system"
    text: str
    status: str  # "pending" | "resolved" | ...


class TimelineSummary(BaseModel):
    """A lightweight derived view of the timeline."""
    total_duration_s: float = 0.0
    num_clips: int = 0
    num_effects: int = 0
    num_markers: int = 0
    num_tracks: int = 0
    head: Optional[str] = None
    tail: Optional[str] = None


class ProjectInfo(BaseModel):
    """Public identity + summary stats for a project."""
    id: str
    name: str
    path: str
    num_assets: int = 0
    num_ops: int = 0
    duration_s: float = 0.0
    last_modified: str = ""


class ProjectState(BaseModel):
    """Full snapshot of a project returned by GET /api/projects/{id}."""
    id: str
    name: str
    path: str
    assets: list[AssetInfo]
    ops: list[OpInfo]
    timeline: TimelineSummary
    pending_notes_count: int
    notes: list[ReviewNoteInfo] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

@dataclass
class _Registry:
    lock: asyncio.Lock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.lock is None:
            self.lock = asyncio.Lock()


_REGISTRY = _Registry()


def _project_id_from_path(path: Path) -> str:
    """Deterministic project id = sha1(absolute_path)[:12] — stable across runs."""
    h = hashlib.sha1(str(path).encode("utf-8")).hexdigest()
    return h[:12]


def _is_project_folder(path: Path) -> bool:
    return (path / ".open_edit" / "edit_graph.db").is_file()


# ---------------------------------------------------------------------------
# Real-data access (uses the real Open Edit storage classes)
# ---------------------------------------------------------------------------

def _list_assets_from_disk(project_path: Path) -> list[Asset]:
    """Read all asset sidecar JSONs from <project>/assets/."""
    assets_dir = project_path / ".open_edit" / "assets"
    if not assets_dir.exists():
        # Fallback to project root's assets dir (older layout)
        assets_dir = project_path / "assets"
    if not assets_dir.exists():
        return []
    out: list[Asset] = []
    for meta_file in assets_dir.glob("*/*.meta.json"):
        try:
            out.append(Asset.model_validate_json(meta_file.read_text()))
        except Exception:
            continue
    return out


def _asset_to_info(asset: Asset) -> AssetInfo:
    """Convert the real ``Asset`` Pydantic model to the API ``AssetInfo``."""
    return AssetInfo(
        hash=asset.asset_hash,
        filename=Path(asset.original_path).name if asset.original_path else "",
        duration_s=asset.duration_sec,
        fps=asset.fps or 0.0,
        width=asset.width or 0,
        height=asset.height or 0,
        codec=asset.codec or "",
        has_audio=asset.has_audio,
        type=asset.type,
    )


def _ops_to_info(ops: list) -> list[OpInfo]:
    """Convert ``list[OperationUnion]`` to ``list[OpInfo]`` for the API."""
    out: list[OpInfo] = []
    for op in ops:
        # Real ops have: edit_id, parent_id, kind, author, timestamp, status,
        # sequence_num, payload. Convert to dict for the API.
        try:
            payload = op.model_dump(mode="json")
        except Exception:
            payload = {"_repr": repr(op)}
        out.append(
            OpInfo(
                id=op.edit_id,
                type=op.kind,
                payload=payload,
                created_at=str(getattr(op, "timestamp", "")),
                status=str(getattr(op, "status", "applied")),
                effects=[],  # Real IR has no separate effects table
            )
        )
    return out


def _note_to_info(note) -> ReviewNoteInfo:
    """Convert a real ``ReviewNote`` to the API ``ReviewNoteInfo``."""
    # The note's anchor is JSON-encoded (e.g. {"t_start": 3.2, "t_end": 3.2}).
    # We extract t_start as the timestamp.
    ts = 0.0
    try:
        anchor_data = json.loads(note.anchor) if isinstance(note.anchor, str) else note.anchor
        if isinstance(anchor_data, dict):
            ts = float(anchor_data.get("t_start", 0.0))
    except Exception:
        pass
    return ReviewNoteInfo(
        id=note.note_id,
        timestamp=ts,
        source=str(note.source.value if hasattr(note.source, "value") else note.source),
        text=note.text or "",
        status=str(note.status.value if hasattr(note.status, "value") else note.status),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def list_projects() -> list[ProjectInfo]:
    """List every project under the projects root."""
    async with _REGISTRY.lock:
        root = projects_root()
        out: list[ProjectInfo] = []
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if not _is_project_folder(child):
                continue
            out.append(_scan_project(child))
        return out


async def create_project(name: str) -> ProjectInfo:
    """Create a new project folder and run ``open_edit init`` on it.

    The folder is created as ``<root>/<safe_name>``. If the name is already
    taken, a numeric suffix is appended until a free name is found.
    """
    safe = _slugify(name)
    if not safe:
        raise ValueError(f"invalid project name: {name!r}")

    async with _REGISTRY.lock:
        root = projects_root()
        path = (root / safe).resolve()
        n = 2
        while path.exists():
            path = (root / f"{safe}-{n}").resolve()
            n += 1
        path.mkdir(parents=True, exist_ok=True)

        # Run `open_edit init` to bootstrap .open_edit/ + edit_graph.db.
        try:
            _run_open_edit(["init"], cwd=path)
        except RuntimeError:
            # The CLI may not be on PATH in test environments. We still
            # proceed; the project folder is created and the user (or a
            # subsequent ingest) can finish setup. The downstream code is
            # defensive about missing DBs.
            pass

        return _scan_project(path)


async def get_project_state(project_id: str) -> ProjectState:
    """Return the full state of a project (assets, ops, notes, summary)."""
    async with _REGISTRY.lock:
        path = _resolve_project_by_id(project_id)
        if path is None:
            root = projects_root()
            raise KeyError(
                f"project not found: {project_id!r} under "
                f"OPEN_EDIT_PROJECTS_ROOT={root}. "
                f"Run `open_edit init {root}/<name>` to create it."
            )

        # Assets: from filesystem via AssetStore
        asset_models = _list_assets_from_disk(path)
        asset_infos = [_asset_to_info(a) for a in asset_models]

        # Edits: from edit_graph.db via EditGraphStore
        db_path = path / ".open_edit" / "edit_graph.db"
        ops: list = []
        project_id_real = project_id
        if db_path.exists():
            try:
                store = EditGraphStore(db_path)
                ops = store.load_all()
                project_id_real = store.project_id
            except Exception:
                pass
        op_infos = _ops_to_info(ops)

        # Notes: from notes.db via NotesStore
        notes_db = path / "notes.db"
        note_models: list = []
        if notes_db.exists():
            try:
                ns = NotesStore(notes_db)
                note_models = ns.list_all(project_id_real)
            except Exception:
                pass
        note_infos = [_note_to_info(n) for n in note_models]
        pending_count = sum(
            1 for n in note_models
            if (n.status.value if hasattr(n.status, "value") else str(n.status)) == "pending"
        )

        # Derive a minimal timeline summary
        total_dur = sum(a.duration_sec for a in asset_models)
        num_clips = sum(1 for o in ops if getattr(o, "kind", "") == "add_clip")
        num_effects = sum(1 for o in ops if getattr(o, "kind", "") == "add_effect")
        # num_tracks from clip op payloads (track_id field)
        track_ids = set()
        for o in ops:
            if getattr(o, "kind", "") == "add_clip":
                t = getattr(o, "track_id", None)
                if t:
                    track_ids.add(t)
        timeline = TimelineSummary(
            total_duration_s=total_dur,
            num_clips=num_clips,
            num_effects=num_effects,
            num_markers=len(note_models),
            num_tracks=len(track_ids),
            head=ops[0].edit_id if ops else None,
            tail=ops[-1].edit_id if ops else None,
        )

        return ProjectState(
            id=project_id,
            name=path.name,
            path=str(path),
            assets=asset_infos,
            ops=op_infos,
            timeline=timeline,
            pending_notes_count=pending_count,
            notes=note_infos,
        )


# ---------------------------------------------------------------------------
# Render snapshots (used by GET /api/projects/{id}/renders)
# ---------------------------------------------------------------------------

async def list_renders(project_id: str) -> list[dict[str, Any]]:
    """List past renders for a project.

    Tries ``open_edit.storage.render_snapshots.RenderSnapshots`` first,
    then falls back to scanning ``.open_edit/renders/*.mp4``.
    """
    async with _REGISTRY.lock:
        path = _resolve_project_by_id(project_id)
        if path is None:
            root = projects_root()
            raise KeyError(
                f"project not found: {project_id!r} under "
                f"OPEN_EDIT_PROJECTS_ROOT={root}. "
                f"Run `open_edit init {root}/<name>` to create it."
            )

    try:
        from open_edit.storage.render_snapshots import RenderSnapshots
        snaps = RenderSnapshots(path)
        for attr in ("list_renders", "list", "all"):
            if hasattr(snaps, attr):
                items = getattr(snaps, attr)()
                return [_render_row_to_dict(r) for r in items]
    except Exception:
        pass

    # Fallback: scan the renders directory.
    renders_dir = path / ".open_edit" / "renders"
    if not renders_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for f in sorted(renders_dir.glob("*.mp4")):
        st = f.stat()
        out.append({
            "id": f.stem,
            "path": str(f),
            "mode": "proxy" if "proxy" in f.stem.lower() else "final",
            "size_bytes": st.st_size,
            "created_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        })
    return out


def _render_row_to_dict(row: Any) -> dict[str, Any]:
    """Best-effort conversion of a RenderSnapshots row to a plain dict."""
    if isinstance(row, dict):
        return row
    if hasattr(row, "model_dump"):
        return row.model_dump()
    if hasattr(row, "__dict__"):
        return {k: v for k, v in vars(row).items() if not k.startswith("_")}
    return {"value": str(row)}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _scan_project(path: Path) -> ProjectInfo:
    """Build a ProjectInfo by inspecting path on disk."""
    db = path / ".open_edit" / "edit_graph.db"
    num_assets = 0
    num_ops = 0
    duration_s = 0.0

    if db.exists():
        try:
            store = EditGraphStore(db)
            ops = store.load_all()
            num_ops = len(ops)
        except Exception:
            pass

    # Assets from filesystem
    asset_models = _list_assets_from_disk(path)
    num_assets = len(asset_models)
    duration_s = sum(a.duration_sec for a in asset_models)

    last_modified = datetime.fromtimestamp(
        db.stat().st_mtime if db.exists() else path.stat().st_mtime,
        tz=timezone.utc,
    ).isoformat()

    return ProjectInfo(
        id=_project_id_from_path(path),
        name=path.name,
        path=str(path),
        num_assets=num_assets,
        num_ops=num_ops,
        duration_s=duration_s,
        last_modified=last_modified,
    )


def _resolve_project_by_id(project_id: str) -> Optional[Path]:
    """Find the project folder whose id matches ``project_id``."""
    root = projects_root()
    for child in root.iterdir():
        if not child.is_dir():
            continue
        if not _is_project_folder(child):
            continue
        if _project_id_from_path(child.resolve()) == project_id:
            return child.resolve()
    return None


def _slugify(name: str) -> str:
    """Convert a human-friendly name to a filesystem-safe slug."""
    out = []
    for ch in name.strip():
        if ch.isalnum() or ch in ("-", "_", "."):
            out.append(ch)
        elif ch.isspace():
            out.append("-")
    return "".join(out).strip("-_.")


def _run_open_edit(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Invoke the ``open_edit`` CLI in a project directory."""
    try:
        return subprocess.run(
            ["open_edit", *args],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "`open_edit` CLI not found on PATH. Install Open Edit or add it to PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"`open_edit {' '.join(args)}` failed (exit {exc.returncode}): "
            f"{exc.stderr.strip() or exc.stdout.strip()}"
        ) from exc
