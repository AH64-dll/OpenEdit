"""Open Edit CLI — init / list / summary / undo / render (Phase 0+1+2)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from open_edit.ir.apply import derive_timeline
from open_edit.ir.types import Project, OperationUnion
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


PROJECT_SUBDIR = ".open_edit"


def _project_dir(cwd: Path) -> Path:
    return cwd / PROJECT_SUBDIR


def _find_existing_project(cwd: Path) -> Path | None:
    """Walk up the directory tree looking for an .open_edit/ project."""
    current = cwd.resolve()
    for parent in [current, *current.parents]:
        candidate = parent / PROJECT_SUBDIR
        if (candidate / "edit_graph.db").exists():
            return candidate
    return None


def cmd_init(args: argparse.Namespace) -> int:
    folder = Path(args.folder).resolve()
    if not folder.exists() or not folder.is_dir():
        print(f"error: {folder} is not a directory", file=sys.stderr)
        return 1

    project_dir = folder / PROJECT_SUBDIR
    project_dir.mkdir(exist_ok=True)
    assets_dir = project_dir / "assets"
    db_path = project_dir / "edit_graph.db"

    store = EditGraphStore(db_path)
    asset_store = AssetStore(assets_dir)

    # Ingest every video/audio/image in the folder (top-level only)
    extensions = {".mp4", ".mkv", ".mov", ".webm", ".mp3", ".wav", ".aac", ".flac", ".jpg", ".jpeg", ".png", ".webp"}
    files = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in extensions
    )
    if not files:
        print(f"warning: no media files found in {folder}", file=sys.stderr)

    ingested = 0
    for f in files:
        try:
            asset = asset_store.ingest(str(f))
            ingested += 1
            print(f"  ingested {f.name}  hash={asset.asset_hash[:12]}...  "
                  f"duration={asset.duration_sec:.2f}s")
        except Exception as e:
            print(f"  failed: {f.name}: {e}", file=sys.stderr)

    # Persist a project_meta record
    with store._conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO project_meta (key, value) VALUES (?, ?)",
            ("folder", str(folder)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO project_meta (key, value) VALUES (?, ?)",
            ("ingested_count", str(ingested)),
        )

    print(f"Initialized project at {project_dir}")
    print(f"Ingested {ingested} media file(s)")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    project_dir = _find_existing_project(Path.cwd())
    if project_dir is None:
        print("error: no open_edit project found in this directory or any parent",
              file=sys.stderr)
        return 1
    store = EditGraphStore(project_dir / "edit_graph.db")
    ops = store.load_all()
    applied = sum(1 for o in ops if o.status == "applied")
    reverted = sum(1 for o in ops if o.status == "reverted")
    print(f"Edit graph: {len(ops)} ops ({applied} applied, {reverted} reverted)")
    for i, op in enumerate(ops):
        print(f"  [{i:3d}] [{op.status:9s}] {op.kind:20s} edit_id={op.edit_id[:8]}")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    project_dir = _find_existing_project(Path.cwd())
    if project_dir is None:
        print("error: no open_edit project found", file=sys.stderr)
        return 1
    store = EditGraphStore(project_dir / "edit_graph.db")
    # Build a Project from the loaded ops (assets are not yet tracked in the
    # edit graph; for now we just derive the timeline from ops)
    from open_edit.ir.types import Project as ProjectModel
    project = ProjectModel(name="cli")
    for op in store.load_all():
        project.edit_graph.append(op)
    timeline = derive_timeline(project)
    print(f"Timeline: {len(timeline.tracks)} tracks, duration {timeline.duration_sec:.2f}s")
    for track in timeline.tracks:
        print(f"  [{track.kind:5s}] {track.track_id}: {len(track.clips)} clip(s)")
        for clip in track.clips:
            print(f"    clip {clip.clip_id[:8]}: {clip.position_sec:.2f}s + "
                  f"[{clip.in_point_sec:.2f}, {clip.out_point_sec:.2f}) "
                  f"asset={clip.asset_hash[:12]}")
    return 0


def cmd_undo(args: argparse.Namespace) -> int:
    project_dir = _find_existing_project(Path.cwd())
    if project_dir is None:
        print("error: no open_edit project found", file=sys.stderr)
        return 1
    store = EditGraphStore(project_dir / "edit_graph.db")
    ops = store.load_all()
    for op in reversed(ops):
        if op.status == "applied":
            store.update_status(op.edit_id, "reverted")
            print(f"Reverted: {op.kind} ({op.edit_id[:8]})")
            return 0
    print("Nothing to undo")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    """Render the current project to MP4."""
    project_dir = _find_existing_project(Path.cwd())
    if project_dir is None:
        print("error: no open_edit project found", file=sys.stderr)
        return 1
    from open_edit.render.orchestrator import render_project
    from open_edit.qc.gate import run_qc_gate
    result = render_project(
        project_id=project_dir.parent.name,
        project_dir=project_dir.parent,
        workdir=project_dir / "renders",
        mode=args.mode,
        profile_name=args.profile,
        force=args.force,
    )
    if result.ok:
        print(f"Rendered: {result.output_path}")
        print(f"  duration: {result.duration_sec:.2f}s  elapsed: {result.elapsed_sec:.2f}s  cache_hit: {result.cache_hit}")
        # Run QC gate
        qc = run_qc_gate(result.output_path, project_dir / "thumbs")
        print(f"QC: {'PASS' if qc.passed else 'FAIL'}")
        for c in qc.checks:
            mark = "✓" if c.passed else "✗"
            print(f"  [{mark}] {c.name}: {c.detail}")
        return 0 if qc.passed else 1
    else:
        print(f"Render failed: {result.error}", file=sys.stderr)
        return 1


def cmd_free_form(args: argparse.Namespace) -> int:
    """Run a free-form Python script in the sandbox against a project."""
    from open_edit.agent.sandbox_bridge import run_free_form
    from open_edit.storage.edit_graph import EditGraphStore
    code = Path(args.code_file).read_text()
    db_path = Path(args.project_dir) / "edit_graph.db"
    if not db_path.exists():
        print(f"error: project db not found: {db_path}", file=sys.stderr)
        return 1
    store = EditGraphStore(db_path)
    # Generate a synthetic parent_op_id for CLI testing; in real use this
    # comes from the agent loop.
    from open_edit.ir.types import new_id
    parent_id = new_id()
    result = run_free_form(
        code, Path(args.project_dir),
        project_id=store.project_id,
        parent_op_id=parent_id,
        timeout=args.timeout,
        mem_mb=args.mem,
    )
    if not result.success:
        print(
            f"error: free-form run failed: {result.reason}: {result.detail}",
            file=sys.stderr,
        )
        return 1
    print(f"free-form run completed: {len(result.ops)} ops in {result.duration_s:.2f}s")
    for op in result.ops:
        store.append(op)
    print(f"appended {len(result.ops)} ops to {db_path}")
    return 0


def _notes_store(project_dir_arg: str) -> tuple["NotesStore", Path] | None:
    """Resolve the project dir + open a NotesStore; prints an error and returns
    None on bad input."""
    from open_edit.storage.notes import NotesStore
    project_dir = Path(project_dir_arg)
    if not project_dir.exists():
        print(f"error: project dir not found: {project_dir}", file=sys.stderr)
        return None
    return NotesStore(project_dir / "notes.db"), project_dir


def cmd_notes_list(args: argparse.Namespace) -> int:
    """`open_edit notes list` — list notes for a project (Phase 4 T6)."""
    from open_edit.storage.notes import NoteStatus
    got = _notes_store(args.project_dir)
    if got is None:
        return 1
    store, _ = got
    status = NoteStatus(args.status) if args.status else None
    notes = store.list_all(args.project_id, status=status)
    if not notes:
        print(f"(no notes for project {args.project_id})")
        return 0
    for n in notes:
        anchor = n.anchor.anchor_type
        text = n.text or "(no text)"
        print(f"{n.note_id} [{n.status.value}] {anchor} {text}")
    return 0


def cmd_notes_add(args: argparse.Namespace) -> int:
    """`open_edit notes add` — append a note to a project (M1)."""
    from open_edit.storage.notes import (
        ReviewNote, NoteSource, NoteStatus,
        TimestampAnchor, RegionAnchor, OpAnchor, NoteAnchor,
    )
    got = _notes_store(args.project_dir)
    if got is None:
        return 1
    store, _ = got
    try:
        anchor_data = json.loads(args.anchor)
    except json.JSONDecodeError as e:
        print(f"error: --anchor is not valid JSON: {e}", file=sys.stderr)
        return 1
    try:
        kind = anchor_data.get("anchor_type")
        if kind == "timestamp":
            anchor: NoteAnchor = TimestampAnchor(**anchor_data)
        elif kind == "region":
            anchor = RegionAnchor(**anchor_data)
        elif kind == "op":
            anchor = OpAnchor(**anchor_data)
        else:
            raise ValueError(
                f"unknown anchor_type {kind!r}; expected timestamp, region, or op"
            )
    except (ValueError, TypeError) as e:
        print(f"error: invalid anchor: {e}", file=sys.stderr)
        return 1
    note = ReviewNote(
        project_id=args.project_id,
        anchor=anchor,
        text=args.text,
        source=NoteSource(args.source),
        status=NoteStatus.pending,
    )
    note_id = store.append(note)
    print(note_id)
    return 0


def cmd_notes_dismiss(args: argparse.Namespace) -> int:
    """`open_edit notes dismiss` — soft-delete (dismiss) a note by id (M1)."""
    got = _notes_store(args.project_dir)
    if got is None:
        return 1
    store, _ = got
    store.mark_dismissed([args.note_id])
    print(f"dismissed {args.note_id}")
    return 0


def cmd_notes(args: argparse.Namespace) -> int:
    """Back-compat: bare `open_edit notes` with no subcommand prints help."""
    parser_notes.print_help()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="open_edit",
        description="AI-native video editing platform",
    )
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="Initialize a project in the given folder")
    p_init.add_argument("folder", nargs="?", default=".", help="folder of raw video files")
    p_init.set_defaults(func=cmd_init)

    p_list = sub.add_parser("list", help="List the edit graph")
    p_list.set_defaults(func=cmd_list)

    p_summary = sub.add_parser("summary", help="Show derived timeline")
    p_summary.set_defaults(func=cmd_summary)

    p_undo = sub.add_parser("undo", help="Revert the most recent applied op")
    p_undo.set_defaults(func=cmd_undo)

    p_render = sub.add_parser("render", help="Render the project to MP4 + run QC")
    p_render.add_argument("--profile", default=None, help="render profile (default: auto from --mode; 720p30 for proxy, 1080p30 for final)")
    p_render.add_argument("--mode", default="proxy", choices=["proxy", "final"], help="render mode")
    p_render.add_argument("--force", action="store_true", help="ignore render cache")
    p_render.set_defaults(func=cmd_render)

    p_freeform = sub.add_parser("free-form", help="Run a free-form Python script in the sandbox against a project")
    p_freeform.add_argument("code_file", help="path to the Python script to run")
    p_freeform.add_argument("project_dir", help="path to the open_edit project directory")
    p_freeform.add_argument("--timeout", type=int, default=30, help="wall-clock timeout in seconds (default: 30)")
    p_freeform.add_argument("--mem", type=int, default=512, help="memory cap in MB (default: 512)")
    p_freeform.set_defaults(func=cmd_free_form)

    p_notes = sub.add_parser("notes", help="Manage notes for a project (Phase 4 T6)")
    notes_sub = p_notes.add_subparsers(dest="notes_cmd")

    p_notes_list = notes_sub.add_parser("list", help="List notes for a project")
    p_notes_list.add_argument("project_id", help="project id (matches the bound session's project)")
    p_notes_list.add_argument("--project-dir", required=True, help="path to the open_edit project directory containing notes.db")
    p_notes_list.add_argument("--status", choices=["pending", "processed", "dismissed"],
                              help="filter by status; default = all")
    p_notes_list.set_defaults(func=cmd_notes_list)

    p_notes_add = notes_sub.add_parser("add", help="Append a note to a project")
    p_notes_add.add_argument("project_id", help="project id (matches the bound session's project)")
    p_notes_add.add_argument("--project-dir", required=True, help="path to the open_edit project directory containing notes.db")
    p_notes_add.add_argument("--text", required=True, help="note text")
    p_notes_add.add_argument(
        "--anchor", required=True,
        help='anchor JSON, e.g. \'{"anchor_type":"timestamp","t_start":0,"t_end":1}\'',
    )
    p_notes_add.add_argument("--source", default="typed",
                             choices=["typed", "voice", "region", "agent", "form_correction"],
                             help="note source (default: typed)")
    p_notes_add.set_defaults(func=cmd_notes_add)

    p_notes_dismiss = notes_sub.add_parser("dismiss", help="Soft-delete a note by id")
    p_notes_dismiss.add_argument("project_id", help="project id (matches the bound session's project)")
    p_notes_dismiss.add_argument("note_id", help="id of the note to dismiss")
    p_notes_dismiss.add_argument("--project-dir", required=True, help="path to the open_edit project directory containing notes.db")
    p_notes_dismiss.set_defaults(func=cmd_notes_dismiss)

    p_notes.set_defaults(func=cmd_notes)

    args = parser.parse_args(argv)
    if args.version:
        print("open_edit 0.1.0")
        return 0
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
