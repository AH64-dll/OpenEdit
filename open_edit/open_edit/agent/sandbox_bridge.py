"""Python wrapper for the open-edit-sandbox Rust binary.

Phase 3 Task 8: orchestrates the full free-form run:
1. Preflight: parse header, check ir_api_version and libs.
2. Acquire JobLock (single-slot for free-form runs).
3. Stage: write code.py and _bootstrap.py into <workdir>/.sandbox/run_<id>/.
4. Invoke the Rust binary (seccomp + rlimits + bwrap).
5. Atomic commit: parse JSON output, validate ops.jsonl, append to edit_graph.

NEVER raises (C7: top-level try/except).

Implementation notes (deviations from the brief, with rationale):
- The brief's `with JobLock.try_acquire(...) as ...` is a syntax error against
  the actual `JobLock` API (try_acquire is an instance method that returns
  Optional[str], not a context manager). We use try/finally to release.
- The brief's `AssetStore()` is a constructor mismatch: AssetStore requires
  `assets_dir`. We pass `<workdir>/assets`.
- The brief's `_validate_references` uses `op.target_id` for SetKeyframeOp and
  SetAudioGainOp, but those ops have `effect_id` and `clip_id` respectively.
  We validate per-op using the right field for each.
- The brief's bootstrap template omits `from __future__ import annotations`,
  `import uuid`, `Annotated`, `Any`, `now_iso8601`, and the `Operation` base
  class. Without these the bootstrap is not actually runnable inside the
  sandbox. We add them so C2 holds at runtime, not just structurally.
- The brief's `textwrap.dedent(f'''...''')` is a no-op once inlined sources
  (which have 0 leading whitespace) are interpolated. The result has the
  template's 4-space indent on every line, which is unparseable. We build
  the bootstrap from a list of lines instead so it actually runs.
- Pydantic 2.13 + exec-with-custom-globals (as the Rust binary does) needs
  explicit `model_rebuild()` on each op subclass. Without it, instantiating
  `AddClipOp(...)` after the bootstrap exec raises
  "class-not-fully-defined". The brief's template triggers this in the
  sandbox. We append rebuild calls at the end of the bootstrap.
"""
from __future__ import annotations

import inspect
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from open_edit.agent.exceptions import (
    FreeFormResult, RenderResult, SandboxError, _ValidationError,
)
from open_edit.agent.libs import (
    parse_header, version_supported, lib_version_supported,
)
from open_edit.ir.api import IR
from open_edit.ir.apply import apply_operation, derive_timeline
from open_edit.ir.types import (
    OperationUnion, Project, Asset, new_id,
    AddClipOp, TrimClipOp, MoveClipOp, RemoveClipOp,
    AddEffectOp, SetKeyframeOp, SetAudioGainOp,
)
from open_edit.pydantic_compat import TypeAdapter
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.job_lock import JobLock

# Pin Python at module import time.
PINNED_PYTHON_BIN = sys.executable
EXPECTED_PY_VERSION = '.'.join(platform.python_version().split('.')[:2])
# H9: hard caps so FreeFormCodeOp.timeout_sec can't hold the JobLock forever.
MAX_FREEFORM_TIMEOUT_SEC = 300
MAX_FREEFORM_MEM_MB = 4096


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


def _resolve_sandbox_bin() -> str | None:
    """H5: resolve at call time, not at module import."""
    return shutil.which("open-edit-sandbox")


def run_free_form(
    code: str,
    workdir: Path,
    project_id: str,
    parent_op_id: str,
    *,
    timeout: int = 30,
    mem_mb: int = 512,
    cpu_sec: int | None = None,
    originating_note_id: Optional[str] = None,
) -> FreeFormResult:
    """Run free-form Python in the sandbox. NEVER raises (C7).

    `originating_note_id` is stamped on every op produced inside the sandbox
    so the round-trip from a user note → agent IR op is auditable.
    """
    timeout = min(int(timeout), MAX_FREEFORM_TIMEOUT_SEC)
    mem_mb = min(int(mem_mb), MAX_FREEFORM_MEM_MB)
    try:
        # 1. Preflight
        try:
            declared_version, declared_libs = parse_header(code)
        except SandboxError as e:
            return FreeFormResult.fail("preflight_failed", str(e))
        if not version_supported(declared_version):
            return FreeFormResult.fail(
                "ir_api_version_unsupported", f"got {declared_version}"
            )
        for lib_name, lib_ver in declared_libs.items():
            if not lib_version_supported(lib_name, lib_ver):
                return FreeFormResult.fail(
                    "lib_version_unsupported", f"{lib_name}=={lib_ver}"
                )

        # 2. JobLock (need EditGraphStore; create lazily to fail preflight
        # without touching the db if header is bad).
        db_path = workdir / "edit_graph.db"
        if not db_path.exists():
            return FreeFormResult.fail(
                "preflight_failed", f"edit_graph.db not found in {workdir}"
            )
        store = EditGraphStore(db_path)
        lock = JobLock(store)
        job_id = lock.try_acquire('free_form_python')
        if job_id is None:
            return FreeFormResult.fail("busy", "another job is in progress")
        try:
            return _run_sandboxed(
                code, workdir, project_id, parent_op_id,
                timeout, mem_mb, cpu_sec, originating_note_id,
            )
        finally:
            lock.release(job_id, "completed")
    except subprocess.TimeoutExpired:
        return FreeFormResult.fail(
            "parent_watchdog_timeout",
            "sandbox did not exit within timeout+10s",
        )
    except Exception as e:
        # C7: never-raises safety net.
        return FreeFormResult.fail("internal_error", repr(e))


def _run_sandboxed(
    code, workdir, project_id, parent_op_id,
    timeout, mem_mb, cpu_sec, originating_note_id,
):
    sandbox_bin = _resolve_sandbox_bin()
    if sandbox_bin is None:
        return FreeFormResult.fail(
            "sandbox_binary_missing",
            "'open-edit-sandbox' not found on PATH; build with "
            "'cd open_edit/sandbox && cargo build --release' and install to $PATH",
        )

    run_id = new_id()
    scratch = workdir / '.sandbox' / f'run_{run_id}'
    scratch.mkdir(parents=True, exist_ok=True)
    code_path = scratch / 'code.py'
    ops_path = scratch / 'ops.jsonl'
    bootstrap_path = scratch / '_bootstrap.py'

    code_path.write_text(code)
    bootstrap_path.write_text(_render_bootstrap(
        project_id, parent_op_id, originating_note_id,
    ))

    assets_dir = workdir / 'assets'
    source_dirs = sorted(p for p in assets_dir.iterdir() if p.is_dir()) if assets_dir.exists() else []
    meta_file = workdir / 'edit_graph.db'

    proc = subprocess.run(
        [sandbox_bin,
         '--scratch', str(scratch),
         '--ops-output', str(ops_path),
         '--python-bin', PINNED_PYTHON_BIN,
         '--expected-py-version', EXPECTED_PY_VERSION,
         '--timeout', str(timeout),
         '--mem', str(mem_mb),
         '--cpu', str(cpu_sec or timeout),
         '--json',
         *(arg for src in source_dirs for arg in ('--source-ro', str(src))),
         '--project-meta', str(meta_file),
        ],
        capture_output=True, text=True, timeout=timeout + 10,
    )

    try:
        rust = json.loads(proc.stdout)
    except json.JSONDecodeError:
        ops_path.unlink(missing_ok=True)
        return FreeFormResult.fail("sandbox_protocol_error",
                                   f"invalid JSON: {proc.stdout[:200]}")

    if not rust.get('ok'):
        ops_path.unlink(missing_ok=True)
        return FreeFormResult.fail(rust.get('reason', 'unknown'),
                                   rust.get('stderr', ''))

    if not ops_path.exists():
        return FreeFormResult.fail("ops_missing",
                                   "sandbox ok but ops.jsonl is missing")

    try:
        ops, _ = _validate_ops_incrementally(ops_path, workdir)
    except _ValidationError as e:
        ops_path.unlink(missing_ok=True)
        return FreeFormResult.fail("invalid_op", str(e))

    return FreeFormResult.ok(ops=ops, duration_s=rust.get('duration_s', 0.0))


def _validate_ops_incrementally(ops_path: Path, workdir: Path) -> tuple[list, object]:
    """C6: validate each op against a working-copy timeline, then apply."""
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
            _validate_references(op, timeline, project.assets)
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
    asset_hashes: set[str] = set()
    for op in store.load_all():
        if isinstance(op, AddClipOp):
            asset_hashes.add(op.asset_hash)
    assets_dir = workdir / 'assets'
    if not assets_dir.exists():
        return {}
    asset_store = AssetStore(assets_dir)
    assets: dict[str, Asset] = {}
    for h in asset_hashes:
        asset = asset_store.get(h)
        if asset is not None:
            assets[h] = asset
    return assets


def _validate_references(op: OperationUnion, timeline, assets) -> None:
    asset_hashes = {a.asset_hash for a in assets.values()}
    track_ids = {t.track_id for t in timeline.tracks}
    clip_ids: set[str] = set()
    effect_ids: set[str] = set()
    for t in timeline.tracks:
        for c in t.clips:
            clip_ids.add(c.clip_id)
            for e in c.effects:
                effect_ids.add(e.effect_id)
        for e in t.effects:
            effect_ids.add(e.effect_id)

    if isinstance(op, AddClipOp):
        if op.asset_hash not in asset_hashes:
            raise ReferenceError(f"asset_hash {op.asset_hash!r} not in project")
        # AddClipOp auto-creates the track via _get_or_create_track, so we
        # do NOT pre-validate track_id here. The first op on a new track
        # would otherwise be rejected before the track is created.
    if isinstance(op, (TrimClipOp, MoveClipOp, RemoveClipOp)):
        if op.clip_id not in clip_ids:
            raise ReferenceError(f"clip_id {op.clip_id!r} not in project")
    if isinstance(op, AddEffectOp):
        if op.target_kind == "clip":
            if op.target_id not in clip_ids:
                raise ReferenceError(f"target_id {op.target_id!r} not in project")
        elif op.target_kind == "track":
            if op.target_id not in track_ids:
                raise ReferenceError(f"target_id {op.target_id!r} not in project")
        else:
            raise ReferenceError(
                f"AddEffectOp.target_kind must be 'clip' or 'track', "
                f"got {op.target_kind!r}"
            )
    if isinstance(op, SetKeyframeOp):
        if op.effect_id not in effect_ids:
            raise ReferenceError(f"effect_id {op.effect_id!r} not in project")
    if isinstance(op, SetAudioGainOp):
        if op.clip_id not in clip_ids:
            raise ReferenceError(f"clip_id {op.clip_id!r} not in project")
    if op.parent_id is None:
        raise ReferenceError("op has no parent_id (IR class should stamp at build time)")


def _render_bootstrap(
    project_id: str,
    parent_op_id: str,
    originating_note_id: Optional[str] = None,
) -> str:
    """Generate _bootstrap.py with the IR class and op models inlined.

    C2 preferred fix (Option A): vendor IR into the bootstrap.
    C1: OPS_FILE is hardcoded to /scratch/ops.jsonl (in-sandbox mount path).
    H10: _FlushingBuffer writes first, then appends.
    """
    from open_edit.ir import types as _types

    ir_source = inspect.getsource(IR)
    # Inline the Operation base class FIRST so subclass references resolve.
    op_types = [
        "Operation",
        "AddClipOp", "RemoveClipOp", "MoveClipOp", "TrimClipOp",
        "AddTransitionOp", "RemoveTransitionOp", "SetTransitionPropertyOp",
        "AddEffectOp", "RemoveEffectOp", "SetEffectParamOp",
        "SetKeyframeOp", "RemoveKeyframeOp",
        "SlipClipOp", "RippleDeleteClipOp", "ChangeClipSpeedOp",
        "SplitClipOp", "ReplaceClipSourceOp", "SetClipSpeedRampOp",
        "SetAudioGainOp", "NormalizeAudioOp",
        "GroupEditsOp", "UngroupEditsOp",
        "RawMltXmlOp", "FreeFormCodeOp",
    ]
    op_sources = [inspect.getsource(getattr(_types, name)) for name in op_types]
    new_id_source = inspect.getsource(_types.new_id)
    now_iso_source = inspect.getsource(_types.now_iso8601)

    # Build from a list of lines so all lines start at column 0. (The brief
    # used `textwrap.dedent(f'''...''')` but that's a no-op once the inlined
    # sources (0 indent) are interpolated; the result has 4-space leading
    # whitespace and won't parse.)
    bootstrap_lines = [
        "# === _bootstrap.py (auto-generated by sandbox_bridge) ===",
        "# Self-contained: IR + op models inlined. No import open_edit.",
        "from __future__ import annotations",
        "import json",
        "import uuid",
        "from typing import Annotated, Any, Literal, Optional, Union",
        "from pydantic import BaseModel, Field",
        "from datetime import datetime, timezone",
        "",
        "# --- INLINED: open_edit/ir/types.py:new_id ---",
        new_id_source,
        "",
        "# --- INLINED: open_edit/ir/types.py:now_iso8601 ---",
        now_iso_source,
        "",
        "# --- INLINED: op models (Operation base + 12 subclasses) ---",
        *op_sources,
        "",
        "# --- INLINED: open_edit/ir/api.py:IR ---",
        ir_source,
        "",
        "# === INJECTED CONSTANTS ===",
        f"PROJECT_ID = {project_id!r}",
        f"PARENT_OP_ID = {parent_op_id!r}",
        f"ORIGINATING_NOTE_ID = {originating_note_id!r}",
        'OPS_FILE = "/scratch/ops.jsonl"',
        "",
        "# Write FIRST, then append (H10).",
        "class _FlushingBuffer(list):",
        "    def __init__(self, ops_file):",
        "        super().__init__()",
        "        self._ops_file = ops_file",
        "    def append(self, op):",
        '        with open(self._ops_file, "a") as f:',
        '            f.write(op.model_dump_json() + "\\n")',
        "        super().append(op)",
        "",
        "_ops = _FlushingBuffer(OPS_FILE)",
        "ir = IR(_ops, project_id=PROJECT_ID, parent_op_id=PARENT_OP_ID, "
        "originating_note_id=ORIGINATING_NOTE_ID)",
        "",
        "# Pydantic rebuild: when the bootstrap is exec'd with a custom globals",
        "# dict (as the Rust binary does), Pydantic's class-not-fully-defined",
        "# check fails for subclasses that use Literal discriminator fields.",
        "# Calling model_rebuild() on each subclass re-evaluates the annotations",
        "# in the right module context and unblocks the validator.",
        *[f"{name}.model_rebuild()" for name in op_types if name != "Operation"],
        "",
    ]
    return "\n".join(bootstrap_lines)


def _resolve_render_binary() -> Path:
    """H5: resolve at call time, not at module import.

    Order matches the install conventions in the README:
    1. ~/.local/bin (user-local pip-style install)
    2. /usr/local/bin (system install)
    3. The repo's target/release binary (dev workflow)
    """
    candidates = [
        Path.home() / ".local" / "bin" / "open-edit-render-sandbox",
        Path("/usr/local/bin/open-edit-render-sandbox"),
        Path(__file__).parent.parent.parent / "sandbox" / "target" / "release" / "open-edit-render-sandbox",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        "open-edit-render-sandbox binary not found in any known location "
        f"(tried: {', '.join(str(c) for c in candidates)})"
    )


def run_render(
    code: str,
    workdir: Path,
    output_path: Path,
    timeout_sec: int = 3600,
    mem_mb: int = 4096,
    with_hwaccel: bool = False,
) -> RenderResult:
    """Run heavy-compute code in the render sandbox. Returns the output
    path on success, or raises SandboxError on setup/render failure.

    The Python code receives `OUTPUT_PATH` (the output file to write) and
    `HOME=/tmp` in its environment. It runs inside bwrap with user/pid/ipc/net
    namespaces, no seccomp, cgroup-based memory + CPU limits, and optional
    /dev/dri bind for GPU work.
    """
    workdir = Path(workdir)
    output_path = Path(output_path)
    if workdir not in output_path.resolve().parents and output_path.resolve().parent != workdir:
        # The Rust binary mounts `workdir` at /workdir; the output path must
        # live under the workdir so the rebind exposes it inside the sandbox.
        raise SandboxError(
            f"output_path {output_path} must live under workdir {workdir}"
        )

    code_file = workdir / "_render_code.py"
    code_file.write_text(code)
    try:
        binary = _resolve_render_binary()
        cmd = [
            str(binary),
            "--code", str(code_file),
            "--workdir", str(workdir),
            "--output", str(output_path),
            "--timeout", str(timeout_sec),
            "--mem", str(mem_mb),
        ]
        if with_hwaccel:
            cmd.append("--with-hwaccel")
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=timeout_sec + 30,
        )
        if result.returncode != 0:
            raise SandboxError(
                f"render sandbox failed (exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        if not output_path.exists():
            raise SandboxError(
                f"render sandbox did not produce {output_path}"
            )
        return RenderResult(path=output_path, ok=True)
    finally:
        code_file.unlink(missing_ok=True)
