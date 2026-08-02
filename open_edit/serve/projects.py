"""Project registry for the Open Edit server.

Each Open Edit "project" is a folder on disk that contains a ``.open_edit/``
subdirectory with at least:

- ``edit_graph.db``  — SQLite database holding the edit graph (per
  ``open_edit/storage/migrations/``)
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
import logging
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

# Real Open Edit storage classes
from open_edit.ir.types import Asset
from open_edit.storage.assets import list_assets_from_disk
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.notes import NotesStore

_LOG = logging.getLogger("open_edit.serve.projects")

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
    proxy_hash: str | None = None
    proxy_profile: str | None = None
    proxy_status: str = "none"
    # Server-relative URL the frontend can use as ``<video src>`` /
    # ``<img src>``. Set by ``_asset_to_info`` (asset list) and by the
    # upload endpoint (ingest response). See
    # ``GET /api/projects/{id}/assets/{hash}/file`` in app.py.
    url: str = ""


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
    t_end: float | None = None
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
    timeline_status: str = "valid"
    timeline_error_code: str | None = None


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
    timeline_full: Optional[dict] = None
    pending_notes_count: int
    notes: list[ReviewNoteInfo] = Field(default_factory=list)
    graph_revision: int = 0
    edit_graph_hash: str | None = None
    timeline_status: str = "valid"
    timeline_error_code: Optional[str] = None


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

def _asset_to_info(asset: Asset, project_id: str = "") -> AssetInfo:
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
        proxy_hash=asset.proxy_hash,
        proxy_profile=asset.proxy_profile,
        proxy_status=asset.proxy_status,
        url=asset_stream_url(project_id, asset.asset_hash) if project_id else "",
    )


def asset_stream_url(project_id: str, asset_hash: str) -> str:
    """Return the server-relative URL for streaming an asset's bytes.

    Centralised so the upload response and the asset-list response
    agree on the URL shape (v1.4 P0-2). Used by
    ``app.post_ingest`` and ``app.get_asset_file``.
    """
    return f"/api/projects/{project_id}/assets/{asset_hash}/file"


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
    t_end: float | None = None
    try:
        anchor = note.anchor
        if hasattr(anchor, "model_dump"):
            anchor_data = anchor.model_dump()
        elif isinstance(anchor, str):
            anchor_data = json.loads(anchor)
        else:
            anchor_data = anchor if isinstance(anchor, dict) else {}
        if isinstance(anchor_data, dict):
            ts = float(anchor_data.get("t_start", 0.0))
            if anchor_data.get("t_end") is not None:
                t_end = float(anchor_data.get("t_end"))
    except Exception:
        pass
    return ReviewNoteInfo(
        id=note.note_id,
        timestamp=ts,
        t_end=t_end,
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
    """Create and validate a project before publishing it to the projects root.

    A project becomes discoverable only after its canonical storage layout and
    edit graph database exist.  Initialising directly in the destination used
    to return a successful API response even when the CLI was unavailable,
    leaving an invisible, unusable folder behind.
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
        temp_path = Path(tempfile.mkdtemp(prefix=f".{path.name}.", dir=root))
        try:
            await asyncio.to_thread(_initialise_project, temp_path)
            if not _is_project_folder(temp_path):
                raise RuntimeError("project initialization did not create edit_graph.db")
            # Verify the schema is readable before making the project visible.
            await asyncio.to_thread(
                lambda: EditGraphStore(temp_path / ".open_edit" / "edit_graph.db").load_all()
            )
            temp_path.rename(path)
        except Exception as exc:
            shutil.rmtree(temp_path, ignore_errors=True)
            _LOG.exception("failed to create project %r", name)
            raise RuntimeError(f"project initialization failed for {name!r}") from exc

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
        asset_models = list_assets_from_disk(path)
        asset_infos = [_asset_to_info(a, project_id) for a in asset_models]

        # Edits: from edit_graph.db via EditGraphStore
        db_path = path / ".open_edit" / "edit_graph.db"
        ops: list = []
        project_id_real = project_id
        graph_revision = 0
        edit_graph_hash: str | None = None
        if db_path.exists():
            try:
                store = EditGraphStore(db_path)
                ops = store.load_all()
                project_id_real = store.project_id
                graph_revision = store.graph_revision()
                try:
                    from open_edit.ir.hash import compute_edit_graph_hash
                    edit_graph_hash = compute_edit_graph_hash(ops)
                except Exception:
                    edit_graph_hash = None
            except Exception:
                # v1.6 P4: a corrupt edit_graph.db used to look identical
                # to "no ops yet". Log the underlying error so the operator
                # can see the DB is unreadable.
                _LOG.warning(
                    "failed to load edit_graph.db at %s; returning empty ops",
                    db_path, exc_info=True,
                )
        op_infos = _ops_to_info(ops)

        # Notes: from notes.db via NotesStore
        notes_db = path / "notes.db"
        note_models: list = []
        if notes_db.exists():
            try:
                ns = NotesStore(notes_db)
                note_models = ns.list_all(project_id_real)
            except Exception:
                # v1.6 P4: same observability fix as for edit_graph.db above.
                _LOG.warning(
                    "failed to load notes.db at %s; returning empty notes",
                    notes_db, exc_info=True,
                )
        note_infos = [_note_to_info(n) for n in note_models]
        pending_count = sum(
            1 for n in note_models
            if (n.status.value if hasattr(n.status, "value") else str(n.status)) == "pending"
        )

        # Derive summary fields from the canonical applied timeline, never
        # from all ingested assets. Unused assets and trims must not affect it.
        total_dur = 0.0
        num_clips = 0
        num_effects = sum(1 for o in ops if getattr(o, "kind", "") == "add_effect")
        num_tracks = 0
        timeline_status = "valid"
        timeline_error_code: str | None = None
        timeline_full: dict[str, Any] | None = None
        try:
            from open_edit.ir.derive import derive_timeline
            from open_edit.ir.types import Project as IRProject
            ir_project = IRProject(
                project_id=project_id_real,
                name=path.name,
                workdir=path,
                assets={asset.asset_hash: asset for asset in asset_models},
                edit_graph=ops,
            )
            full_timeline = derive_timeline(ir_project)
            timeline_full = full_timeline.model_dump(mode="json")
            total_dur = full_timeline.duration_sec
            num_tracks = len(full_timeline.tracks)
            num_clips = sum(len(track.clips) for track in full_timeline.tracks)
        except Exception as exc:
            timeline_status = "invalid"
            timeline_error_code = "timeline_derivation_failed"
            _LOG.warning("failed to derive timeline for project %s", project_id, exc_info=True)
        timeline = TimelineSummary(
            total_duration_s=total_dur,
            num_clips=num_clips,
            num_effects=num_effects,
            num_markers=len(note_models),
            num_tracks=num_tracks,
            head=ops[0].edit_id if ops else None,
            tail=ops[-1].edit_id if ops else None,
            timeline_status=timeline_status,
            timeline_error_code=timeline_error_code,
        )

        return ProjectState(
            id=project_id,
            name=path.name,
            path=str(path),
            assets=asset_infos,
            ops=op_infos,
            timeline=timeline,
            timeline_full=timeline_full,
            pending_notes_count=pending_count,
            notes=note_infos,
            graph_revision=graph_revision,
            edit_graph_hash=edit_graph_hash,
            timeline_status=timeline_status,
            timeline_error_code=timeline_error_code,
        )


# ---------------------------------------------------------------------------
# Render snapshots (used by GET /api/projects/{id}/renders)
# ---------------------------------------------------------------------------

_SNAPSHOT_DB_NAME = "render_snapshots.db"

_SNAPSHOT_STATUS_TO_JOB_STATUS = {
    "ready": "succeeded",
    "rendering": "running",
    "failed": "failed",
}


async def list_renders(project_id: str) -> list[dict[str, Any]]:
    """List past renders for a project.

    Prefers durable ``RenderJobService`` job records, then falls back to
    scanning ``.open_edit/renders/*.mp4``.
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

    out: list[dict[str, Any]] = []
    try:
        from open_edit.kernel.render_jobs import DEFAULT_RENDER_JOB_SERVICE

        for job in DEFAULT_RENDER_JOB_SERVICE.list_jobs(path):
            # Chunk jobs publish a manifest and independent artifacts. They
            # are polled through the preview-manifest API, not shown as
            # whole-file MP4 history.
            if job.mode == "preview-chunks":
                continue
            size_bytes = 0
            if job.output_path:
                try:
                    size_bytes = Path(job.output_path).stat().st_size
                except OSError:
                    size_bytes = 0
            out.append({
                "id": job.job_id,
                "path": job.output_path or "",
                "mode": job.mode,
                "status": job.status,
                "size_bytes": size_bytes,
                "timestamp": job.updated_at,
                "graph_revision": job.graph_revision,
                "edit_graph_hash": job.edit_graph_hash,
                "error": job.error,
            })
    except Exception:
        _LOG.warning("failed to list durable render jobs for %s", project_id, exc_info=True)
        raise

    snapshots: list[dict[str, Any]] = []
    snapshots_db = path / ".open_edit" / _SNAPSHOT_DB_NAME
    if snapshots_db.exists():
        try:
            from open_edit.storage.render_snapshots import RenderSnapshotStore

            for snap in RenderSnapshotStore(snapshots_db).list_for_project(project_id):
                size_bytes = 0
                try:
                    size_bytes = snap.render_path.stat().st_size
                except OSError:
                    size_bytes = 0
                snapshots.append({
                    "id": snap.version_id,
                    "path": str(snap.render_path),
                    "mode": "snapshot",
                    "status": _SNAPSHOT_STATUS_TO_JOB_STATUS.get(snap.status.value, snap.status.value),
                    "size_bytes": size_bytes,
                    "timestamp": snap.created_at,
                    "graph_revision": None,
                    "edit_graph_hash": snap.edit_graph_hash,
                    "error": None,
                })
        except (ImportError, sqlite3.Error, OSError):
            _LOG.warning("failed to list render snapshots for %s", project_id, exc_info=True)
    out.extend(snapshots)

    if out:
        # Also surface on-disk proxy/final files produced by CLI renders so the
        # UI can open them even when durable job records failed/orphaned.
        renders_dir = path / ".open_edit" / "renders"
        if renders_dir.exists():
            known = {row.get("id") for row in out}
            for f in sorted(renders_dir.glob("project_*.mp4"), key=lambda p: p.stat().st_mtime):
                if f.stem in known or not _is_complete_render_mp4(f):
                    continue
                st = f.stat()
                out.append({
                    "id": f.stem,
                    "path": str(f),
                    "mode": "proxy",
                    "status": "succeeded",
                    "size_bytes": st.st_size,
                    "timestamp": st.st_mtime,
                })
        return out

    # Fallback: scan the renders directory.
    renders_dir = path / ".open_edit" / "renders"
    if not renders_dir.exists():
        return []
    for f in sorted(renders_dir.glob("*.mp4")):
        if not _is_complete_render_mp4(f):
            continue
        st = f.stat()
        out.append({
            "id": f.stem,
            "path": str(f),
            "mode": "proxy" if "proxy" in f.stem.lower() else "final",
            "status": "succeeded",
            "size_bytes": st.st_size,
            "timestamp": st.st_mtime,
        })
    return out


def _is_complete_render_mp4(path: Path) -> bool:
    """Skip melt intermediates / tiny stubs so the preview never auto-loads junk."""
    name = path.name.lower()
    if path.suffix.lower() != ".mp4":
        return False
    # melt writes ``project_<hash>.melt.mp4`` while rendering; that file is not
    # a finished proxy and breaks the <video> element if auto-loaded.
    if name.endswith(".melt.mp4") or ".melt." in name:
        return False
    try:
        return path.is_file() and path.stat().st_size >= 10_000
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _scan_project(path: Path) -> ProjectInfo:
    """Build a ProjectInfo by inspecting path on disk."""
    db = path / ".open_edit" / "edit_graph.db"
    num_assets = 0
    num_ops = 0
    duration_s = 0.0
    ops: list[Any] = []

    if db.exists():
        try:
            store = EditGraphStore(db)
            ops = store.load_all()
            num_ops = len(ops)
        except Exception:
            pass

    # Assets from filesystem
    asset_models = list_assets_from_disk(path)
    num_assets = len(asset_models)
    try:
        from open_edit.ir.derive import derive_timeline
        from open_edit.ir.types import Project as IRProject
        timeline = derive_timeline(IRProject(
            project_id=_project_id_from_path(path), name=path.name, workdir=path,
            assets={asset.asset_hash: asset for asset in asset_models}, edit_graph=ops,
        ))
        duration_s = timeline.duration_sec
    except Exception:
        _LOG.warning("failed to derive project summary timeline for %s", path, exc_info=True)

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


def _initialise_project(path: Path) -> None:
    """Create the supported project layout with storage APIs, not a subprocess."""
    project_dir = path / ".open_edit"
    for directory in ("assets", "renders", "conversations", "logs", "temp", "inbox"):
        (project_dir / directory).mkdir(parents=True, exist_ok=True)
    store = EditGraphStore(project_dir / "edit_graph.db")
    with store._conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO project_meta (key, value) VALUES (?, ?)",
            ("folder", str(path)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO project_meta (key, value) VALUES (?, ?)",
            ("ingested_count", "0"),
        )
