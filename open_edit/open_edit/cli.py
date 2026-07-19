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
