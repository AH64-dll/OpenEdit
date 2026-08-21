"""Open Edit CLI — init / list / summary / undo / render (Phase 0+1+2)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from importlib import metadata
from pathlib import Path

from open_edit.ir.derive import derive_timeline
from open_edit.kernel.render_jobs import DEFAULT_RENDER_JOB_SERVICE
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


def render_preview_chunks(*, project_id: str, project_dir: Path, job_id: str) -> dict:
    """Call the optional host preview worker through a stable CLI seam."""
    try:
        from open_edit.render.preview_chunks import (
            render_preview_chunks as worker,
        )
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("open_edit.render.preview_chunks"):
            raise RuntimeError("preview-chunks worker is unavailable") from exc
        raise
    return worker(project_id=project_id, project_dir=project_dir, job_id=job_id)


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

    # Visibility hint (v1.4 P0-1): the chat server (``open_edit serve``)
    # only sees projects that are SUBDIRECTORIES of OPEN_EDIT_PROJECTS_ROOT.
    # If the user ran ``open_edit init .`` from inside the root, or
    # pointed init at a folder that is not under the root, the project
    # will exist on disk but ``GET /api/projects`` will not list it.
    # Warn so the user knows what to do.
    server_root_raw = os.environ.get("OPEN_EDIT_PROJECTS_ROOT", "~/OpenEditProjects")
    server_root = Path(server_root_raw).expanduser().resolve()
    try:
        folder.relative_to(server_root)
        under_root = True
    except ValueError:
        under_root = False
    if not under_root:
        print(
            f"note: this project is not a subdirectory of "
            f"OPEN_EDIT_PROJECTS_ROOT={server_root}, so it will NOT be "
            f"visible to `open_edit serve`.",
            file=sys.stderr,
        )
        print(
            f"  To make it visible, run:  open_edit init {server_root}/<name>",
            file=sys.stderr,
        )
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


def cmd_asset_proxy(args: argparse.Namespace) -> int:
    """Drain (and optionally await) the project's source-proxy job queue.

    Runs every persisted ``queued``/``running``/``orphaned`` asset-proxy job
    through the host worker pool — the CLI equivalent of the serve
    background drain. Without ``--wait`` the command returns once the jobs
    are *started*; with ``--wait`` it blocks until the queue drains (all
    rows terminal) or ``--timeout`` expires.
    """
    if args.project:
        project_dir = Path(args.project).resolve()
        if not (project_dir / ".open_edit").is_dir() and project_dir.name != ".open_edit":
            print(
                f"error: {project_dir} is not an open_edit project "
                "(no .open_edit/ directory)",
                file=sys.stderr,
            )
            return 1
    else:
        project_dir = _find_existing_project(Path.cwd())
        if project_dir is None:
            print(
                "error: no open_edit project found in this directory or any parent",
                file=sys.stderr,
            )
            return 1

    from open_edit.kernel.asset_proxy_jobs import (
        DEFAULT_ASSET_PROXY_JOB_SERVICE,
        AssetProxyJobService,
    )

    # Both call forms work: project root (canonical) or the .open_edit dir
    # returned by _find_existing_project (legacy CLI convention).
    root = (
        project_dir
        if project_dir.name != ".open_edit"
        else project_dir.parent
    )
    service = DEFAULT_ASSET_PROXY_JOB_SERVICE
    try:
        stats = service.drain(root)
    except Exception as exc:
        result = {"ok": False, "mode": "asset-proxy", "error": str(exc)}
        if args.json:
            print(json.dumps(result, default=str))
        else:
            print(f"Asset proxy failed: {result['error']}", file=sys.stderr)
        return 1

    if args.wait:
        deadline = time.monotonic() + args.timeout
        while True:
            jobs = service.list_jobs(root)
            pending = [
                job for job in jobs
                if job.status in ("queued", "running")
            ]
            if not pending:
                break
            if time.monotonic() >= deadline:
                result = {
                    "ok": False,
                    "mode": "asset-proxy",
                    "error": (
                        f"timed out after {args.timeout}s; "
                        f"{len(pending)} job(s) still queued/running"
                    ),
                    "stats": stats,
                }
                if args.json:
                    print(json.dumps(result, default=str))
                else:
                    print(
                        f"Asset proxy: timed out after {args.timeout}s; "
                        f"{len(pending)} job(s) still queued/running",
                        file=sys.stderr,
                    )
                return 1
            time.sleep(0.25)
        jobs = service.list_jobs(root)
    else:
        jobs = service.list_jobs(root)

    succeeded = sum(1 for job in jobs if job.status == "succeeded")
    failed = sum(1 for job in jobs if job.status == "failed")
    not_needed = sum(
        1 for job in jobs
        if job.status == "succeeded" and job.proxy_hash is None
    )
    other = len(jobs) - succeeded - failed
    if args.json:
        print(json.dumps({
            "ok": failed == 0,
            "mode": "asset-proxy",
            "drain": stats,
            "jobs": {
                "total": len(jobs),
                "succeeded": succeeded,
                "failed": failed,
                "not_needed": not_needed,
                "other": other,
            },
        }, default=str))
    else:
        print(
            f"Asset proxy: drain {stats} | jobs: {len(jobs)} total, "
            f"{succeeded} succeeded, {failed} failed, "
            f"{not_needed} not needed, {other} other",
        )
    return 0 if failed == 0 else 1


def cmd_preview_chunks(args: argparse.Namespace) -> int:
    """Run one durable preview-chunks job and emit its worker result."""
    project_dir = _find_existing_project(Path.cwd())
    if project_dir is None:
        result = {
            "ok": False,
            "mode": "preview-chunks",
            "error": "no open_edit project found",
        }
    else:
        job = DEFAULT_RENDER_JOB_SERVICE.get(project_dir.parent, args.job_id)
        if job is None:
            result = {
                "ok": False,
                "mode": "preview-chunks",
                "error": f"render job not found: {args.job_id}",
            }
        elif job.mode != "preview-chunks":
            result = {
                "ok": False,
                "mode": "preview-chunks",
                "error": f"render job {args.job_id} is mode {job.mode!r}",
            }
        else:
            try:
                result = render_preview_chunks(
                    project_id=job.project_id,
                    project_dir=project_dir.parent,
                    job_id=job.job_id,
                )
            except Exception as exc:
                result = {
                    "ok": False,
                    "mode": "preview-chunks",
                    "error": str(exc),
                }
            if not isinstance(result, dict):
                result = {
                    "ok": False,
                    "mode": "preview-chunks",
                    "error": "preview worker returned a non-dict result",
                }

    if args.json:
        print(json.dumps(result, default=str))
    elif result.get("ok"):
        print(f"Preview chunks: {result.get('output_path', '')}")
    else:
        print(f"Preview chunks failed: {result.get('error', 'unknown error')}", file=sys.stderr)
    return 0 if result.get("ok") is True else 1


def cmd_render(args: argparse.Namespace) -> int:
    """Render the current project to MP4."""
    project_dir = _find_existing_project(Path.cwd())
    if project_dir is None:
        print("error: no open_edit project found", file=sys.stderr)
        return 1
    from open_edit.render.orchestrator import render_project
    from open_edit.render.diagnostics import StageRecorder
    from open_edit.qc.gate import run_qc_gate
    from open_edit.qc.policy import resolve_qc_policy
    overrides = {k: v for k, v in (
        ("crf", args.crf), ("vb", args.vb), ("preset", args.preset),
        ("scale", args.scale), ("codec", args.codec),
    ) if v is not None}
    result = render_project(
        project_id=project_dir.parent.name,
        project_dir=project_dir.parent,
        workdir=project_dir / "renders",
        mode=args.mode,
        profile_name=args.profile,
        quality=args.quality,
        overrides=overrides,
        force=args.force,
        force_remotion=getattr(args, "force_remotion", False),
        remotion_uids=getattr(args, "remotion_uids", ()),
        nice_level=10,
        encoder_backend=getattr(args, "encoder", None),
    )
    if result.ok:
        if args.json:
            print(json.dumps({
                "ok": True,
                "output_path": str(result.output_path),
                "duration_sec": result.duration_sec,
                "elapsed_sec": result.elapsed_sec,
                "cache_hit": result.cache_hit,
                "diagnostics": result.diagnostics,
                "mode": args.mode,
            }))
            return 0
        print(f"Rendered: {result.output_path}")
        print(f"  duration: {result.duration_sec:.2f}s  elapsed: {result.elapsed_sec:.2f}s  cache_hit: {result.cache_hit}")
        diagnostics = dict(result.diagnostics or {})
        cache_hit = bool(result.cache_hit)
        cache_info = diagnostics.get("cache")
        if not cache_hit and isinstance(cache_info, dict):
            cache_hit = bool(cache_info.get("hit"))
        if not cache_hit:
            stages = diagnostics.get("stages")
            if isinstance(stages, dict):
                cache_stage = stages.get("render_cache_lookup")
                if isinstance(cache_stage, dict):
                    cache_hit = bool(cache_stage.get("hit"))

        qc_policy = resolve_qc_policy(args.mode, cache_hit=cache_hit)
        diagnostics["qc_policy"] = qc_policy.mode
        qc_t0 = time.monotonic()
        qc_recorder = StageRecorder()
        # The human-readable path performs the same policy-aware gate as the
        # durable service. The JSON path above remains render-result-only.
        try:
            qc = run_qc_gate(
                result.output_path, project_dir / "thumbs",
                target_duration_s=result.duration_sec, mode=args.mode,
                source_baseline=diagnostics.get("source_baseline"),
                policy=qc_policy,
            )
            if qc_policy.mode == "skip":
                reason = "deliverable_cache_hit" if cache_hit else "policy_never"
                qc.reason = reason
                for check in qc.checks:
                    check.detail = f"skipped by policy=skip; {reason}"
            qc_report = qc.model_dump(mode="json")
            qc_recorder.record(
                "qc",
                time.monotonic() - qc_t0,
                status="skipped" if qc_policy.mode == "skip" else "completed",
                passed=bool(qc_report.get("passed")),
                policy=qc_policy.mode,
                complete=bool(qc_report.get("complete", False)),
                reason=qc_report.get("reason", ""),
            )
        except Exception as exc:
            qc_report = {
                "passed": False,
                "policy": qc_policy.mode,
                "complete": False,
                "reason": f"qc gate failed: {exc}",
                "checks": [
                    {"name": "qc_gate", "passed": False, "detail": f"qc gate failed: {exc}"},
                ],
            }
            qc_recorder.record(
                "qc",
                time.monotonic() - qc_t0,
                status="failed",
                error=str(exc),
                policy=qc_policy.mode,
            )
        diagnostics.setdefault("stages", {}).update(qc_recorder.stages)
        diagnostics["qc_report"] = qc_report
        result.diagnostics = diagnostics
        if qc_report.get("policy") == "skip" and qc_report.get("reason") == "deliverable_cache_hit":
            print("QC: SKIPPED (deliverable cache hit)")
        elif qc_report.get("policy") == "skip":
            print(f"QC: SKIPPED ({qc_report.get('reason', 'policy')})")
        elif qc_report.get("policy") == "light":
            print(f"QC: INCOMPLETE ({qc_report.get('reason', 'policy')})")
        else:
            print(f"QC: {'PASS' if qc_report['passed'] else 'FAIL'}")
        for c in qc_report["checks"]:
            mark = "PASS" if c["passed"] else "FAIL"
            print(f"  [{mark}] {c['name']}: {c['detail']}")
        return 0 if qc_report["passed"] else 1
    else:
        if args.json:
            print(json.dumps({"ok": False, "error": result.error, "mode": args.mode}))
            return 1
        print(f"Render failed: {result.error}", file=sys.stderr)
        return 1


def cmd_free_form(args: argparse.Namespace) -> int:
    """Run a free-form Python script in the sandbox against a project."""
    from open_edit.agent.sandbox import run_free_form
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


def _notes_store(project_dir_arg: str) -> tuple["NotesStore", Path] | None:  # noqa: F821
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
    """Back-compat: bare `open_edit notes` with no subcommand prints help.

    The notes subparser is built inside ``main()`` (so it can't be reached
    from this module-scope callback). Print a one-liner pointing the user
    at the full help instead.
    """
    print("usage: open_edit notes <list|add|dismiss> ...", file=sys.stderr)
    print("Run 'open_edit notes <subcommand> --help' for details.", file=sys.stderr)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Start the chat-driven FastAPI backend (uvicorn)."""
    try:
        import uvicorn
    except ImportError:
        print(
            "ERROR: uvicorn is not installed. Run `pip install 'uvicorn[standard]'` "
            "or `pip install -e '.[serve]'`.",
            file=sys.stderr,
        )
        return 1

    # Propagate the token into the environment so the auth middleware
    # (which reads OPEN_EDIT_TOKEN at request time) picks it up. Optional:
    # if no token was supplied, auth stays off.
    if getattr(args, "token", None):
        os.environ["OPEN_EDIT_TOKEN"] = args.token
    # MCP-first default: review-only unless --with-agent cleared the flag.
    os.environ["OPEN_EDIT_REVIEW_ONLY"] = (
        "1" if getattr(args, "review_only", True) else "0"
    )

    uvicorn.run(
        "open_edit.serve.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    """Start the local stdio MCP server for an external agent host."""
    from open_edit.mcp.server import main as mcp_main

    argv: list[str] = []
    if getattr(args, "project", None):
        argv.extend(["--project", args.project])
    return mcp_main(argv)


def _version() -> str:
    try:
        return metadata.version("open_edit")
    except metadata.PackageNotFoundError:
        return "0.0.0"


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

    p_render = sub.add_parser(
        "render",
        help=("Render the project to MP4 + run QC. Exit code 1 when the QC gate "
              "fails (diagnostic only; server render path unaffected)."),
    )
    p_render.add_argument("--profile", default=None, help="render profile (default: auto from --mode; 720p30 for proxy, 1080p30 for final)")
    p_render.add_argument("--mode", default="proxy", choices=["proxy", "final"], help="render mode")
    p_render.add_argument(
        "--encoder", default=None, choices=["gpu", "cpu"],
        help="video encoder backend (default: gpu, or OPEN_EDIT_RENDER_BACKEND)",
    )
    p_render.add_argument("--quality", default=None, choices=["fast", "standard", "high", "archival"],
                          help="encode quality tier (default: fast for proxy, standard for final)")
    p_render.add_argument("--crf", type=int, default=None, help="quality override 0-51 (nvenc: mapped to cq)")
    p_render.add_argument("--vb", default=None, help="video bitrate override, e.g. 10M")
    p_render.add_argument("--preset", default=None, help="encoder preset override")
    p_render.add_argument("--scale", default=None, help="output scale override, e.g. 1280x720")
    p_render.add_argument("--codec", default=None, choices=["h264", "hevc", "av1"],
                          help="codec family override")
    p_render.add_argument("--json", action="store_true", help="emit one structured render result JSON object")
    p_render.add_argument("--force", action="store_true", help="ignore render cache")
    p_render.add_argument(
        "--force-remotion",
        action="store_true",
        help="bypass Remotion manifest and composition caches",
    )
    p_render.add_argument(
        "--remotion-uid",
        dest="remotion_uids",
        action="append",
        default=[],
        help="bypass Remotion caches for one composition UID (repeatable)",
    )
    p_render.set_defaults(func=cmd_render)

    p_asset_proxy = sub.add_parser(
        "asset-proxy",
        help=(
            "Drain (and optionally await) the project's source-proxy "
            "generation queue"
        ),
    )
    p_asset_proxy.add_argument(
        "project",
        nargs="?",
        default=None,
        help=(
            "project path (default: nearest open_edit project from cwd, "
            "like the other commands)"
        ),
    )
    p_asset_proxy.add_argument(
        "--wait",
        action="store_true",
        default=False,
        help="block until every queued/running job reaches a terminal state",
    )
    p_asset_proxy.add_argument(
        "--timeout",
        type=int,
        default=3600,
        help="wall-clock wait limit in seconds (default: 3600)",
    )
    p_asset_proxy.add_argument(
        "--json",
        action="store_true",
        help="emit one structured drain result JSON object",
    )
    p_asset_proxy.set_defaults(func=cmd_asset_proxy)

    p_preview_chunks = sub.add_parser(
        "preview-chunks",
        help="Run the internal durable preview-chunks worker",
    )
    p_preview_chunks.add_argument("--job-id", required=True, help="durable render job id")
    p_preview_chunks.add_argument(
        "--json", action="store_true", help="emit one structured worker result JSON object",
    )
    p_preview_chunks.set_defaults(func=cmd_preview_chunks)

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

    # --- chat UI serve (v1.3+) ------------------------------------------
    p_serve = sub.add_parser(
        "serve",
        help="Start the chat-driven FastAPI backend (uvicorn).",
        description=(
            "Start the Open Edit HTTP + WebSocket server. The server "
            "exposes a REST API under /api/ and a chat WebSocket at "
            "/api/chat/{project_id}. The static frontend (if present) is "
            "served at /."
        ),
    )
    p_serve.add_argument(
        "--host",
        default=os.environ.get("OPEN_EDIT_SERVE_HOST", "127.0.0.1"),
        help="Bind host (default 127.0.0.1, env OPEN_EDIT_SERVE_HOST)",
    )
    p_serve.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("OPEN_EDIT_SERVE_PORT", "8000")),
        help="Bind port (default 8000, env OPEN_EDIT_SERVE_PORT)",
    )
    p_serve.add_argument(
        "--token",
        default=os.environ.get("OPEN_EDIT_TOKEN"),
        help=(
            "Optional bearer token required for remote (non-localhost) "
            "requests (env OPEN_EDIT_TOKEN). If unset, no auth is required."
        ),
    )
    p_serve.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable uvicorn auto-reload (dev mode).",
    )
    p_serve.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="Uvicorn log level (default info).",
    )
    p_serve.add_argument(
        "--review-only",
        action="store_true",
        default=True,
        help=(
            "Review studio mode (default): preview UI + timeline without "
            "built-in LLM chat or provider config (use with external MCP harness)."
        ),
    )
    p_serve.add_argument(
        "--with-agent",
        dest="review_only",
        action="store_false",
        help=(
            "Enable built-in agent chat / provider UI (disables review-only). "
            "Not needed when using Open Edit as an MCP server."
        ),
    )
    p_serve.set_defaults(func=cmd_serve)

    p_mcp = sub.add_parser(
        "mcp",
        help="Start local stdio MCP server (agent plugin mode).",
        description=(
            "Expose Open Edit pillar tools over MCP stdio so Cursor "
            "(or another MCP client) owns the agent loop. Pin a project "
            "with --project or OPEN_EDIT_PROJECT. See docs/MCP.md."
        ),
    )
    p_mcp.add_argument(
        "--project",
        default=None,
        help="Path to an Open Edit project (contains .open_edit/). "
             "Defaults to OPEN_EDIT_PROJECT.",
    )
    p_mcp.set_defaults(func=cmd_mcp)

    args = parser.parse_args(argv)
    if args.version:
        print(f"open_edit {_version()}")
        return 0
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
