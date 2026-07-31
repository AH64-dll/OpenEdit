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

import abc
import inspect
import json
import logging
import os
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
from open_edit.ir.apply import apply_operation
from open_edit.ir.derive import derive_timeline
from open_edit.ir.validate import OpValidationError, validate_op_references
from open_edit.ir.types import (
    OperationUnion, Project, Asset, new_id,
)
from pydantic import TypeAdapter
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.job_lock import JobLock

# Pin Python at module import time.
PINNED_PYTHON_BIN = sys.executable
EXPECTED_PY_VERSION = '.'.join(platform.python_version().split('.')[:2])
# H9: hard caps so FreeFormCodeOp.timeout_sec can't hold the JobLock forever.
MAX_FREEFORM_TIMEOUT_SEC = 300
MAX_FREEFORM_MEM_MB = 4096

# Max length for stderr/stdout fragments echoed into result detail (5b).
# Keeps the LLM-facing error short (no prompt-injection surface) while still
# giving a hint about what went wrong.
_DETAIL_MAX_LEN = 200

logger = logging.getLogger(__name__)

# Pluggable-backend selection. Read at call time (never cached at import) so
# tests / operators can flip it via the environment.
#   "bwrap" (default) -> BwrapBackend (bwrap + seccomp + rlimits, fail-closed).
#   "dev"             -> DevSubprocessBackend (NO isolation, local dev only).
SANDBOX_BACKEND_ENV = "OPEN_EDIT_SANDBOX_BACKEND"
_DEFAULT_SANDBOX_BACKEND = "bwrap"  # POSIX default; Windows unset → DevSubprocessBackend


class SandboxUnavailable(Exception):
    """Fail-closed signal: the bwrap sandbox could not be created.

    Raised ONLY when the default (bwrap) backend is selected and the kernel
    refuses to create the namespaces bwrap needs (e.g. the observed
    ``bwrap: Creating new namespace failed: Resource temporarily
    unavailable``). We NEVER silently fall through to an unsandboxed
    execution path; the operator must consciously opt in to the dev backend
    (``OPEN_EDIT_SANDBOX_BACKEND=dev``) or fix the host environment.
    """


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


def _resolve_sandbox_bin() -> str:
    """H5: resolve at call time, not at module import.

    P8: resolve via an absolute allow-list, not $PATH. shutil.which trusts
    the user's PATH, so a hostile 'open-edit-sandbox' earlier in PATH
    would win over the legitimate one. The allow-list is three fixed
    absolute locations matching the install conventions in the README:

      1. ~/.local/bin (user-local pip-style install)
      2. /usr/local/bin (system install)
      3. <repo>/sandbox/target/release (dev workflow)

    Raises FileNotFoundError if no allow-listed binary exists. Callers
    map that to FreeFormResult.fail('sandbox_binary_missing', ...).
    """
    candidates = [
        Path.home() / ".local" / "bin" / "open-edit-sandbox",
        Path("/usr/local/bin/open-edit-sandbox"),
        Path(__file__).parent.parent.parent
        / "sandbox" / "target" / "release" / "open-edit-sandbox",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    raise FileNotFoundError(
        "open-edit-sandbox binary not found in any allow-listed location "
        f"(tried: {', '.join(str(c) for c in candidates)})"
    )


def _assets_dir_for_workdir(workdir: Path) -> Path:
    """Return the asset-store directory for a sandbox workdir.

    The workdir is whichever directory contains ``edit_graph.db``:
    - canonical layout: ``<root>/.open_edit/`` → assets at ``<workdir>/assets``
    - legacy layout: ``<root>/`` → assets at ``<workdir>/.open_edit/assets``
    """
    direct = workdir / "assets"
    if direct.is_dir():
        return direct
    return workdir / ".open_edit" / "assets"


def _validate_workdir(workdir: Path) -> Path:
    """P9: resolve a caller-supplied workdir.

    The AI may operate on any directory; we only require that it is a real
    project (contains ``edit_graph.db``) so the store can locate its DB.
    No root/allow-list restriction is applied.

    On any failure, raise ValueError with a clear message. The caller
    catches it and returns the appropriate FreeFormResult / RenderResult.
    Returns the resolved absolute Path on success.
    """
    workdir = Path(workdir).resolve()
    if not workdir.is_dir():
        raise ValueError(f"workdir {workdir} is not a directory")
    if not (workdir / "edit_graph.db").exists():
        raise ValueError(
            f"workdir {workdir} is not a valid project directory "
            f"(missing edit_graph.db)"
        )
    return workdir


def _sanitize_for_detail(s: str, max_len: int = _DETAIL_MAX_LEN) -> str:
    """5b: make a string safe to surface in a result detail.

    - Take only the first line (drop everything after \\n).
    - Strip control characters (NUL, BEL, escape sequences, etc.).
    - Truncate to `max_len` characters with an ellipsis suffix.
    - Empty / non-string input returns "".

    The raw value is meant to be logged server-side, not echoed back to
    the LLM (it could contain absolute paths, tokens, or prompt-injection
    payloads from a misbehaving child process).
    """
    if not s:
        return ""
    s = s.split("\n", 1)[0]
    s = "".join(c for c in s if c.isprintable() or c in " \t")
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s


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
        # P9: validate workdir FIRST, before any other I/O. A hostile
        # tool call with project_path="/etc" must NOT cause code.py /
        # _render_code.py / bootstrap.py to be staged on the host.
        workdir = _validate_workdir(workdir)

        # Plan D: auto-inject ir_api_version header if missing (backward compat).
        if not code.startswith("# ir_api_version:"):
            code = "# ir_api_version: 0.1; libs: {}\n" + code

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
        store = EditGraphStore(db_path)
        lock = JobLock(store)
        job_id = lock.try_acquire('free_form_python')
        if job_id is None:
            return FreeFormResult.fail("busy", "another job is in progress")
        try:
            backend = get_sandbox_backend()
            return backend.run(
                code=code,
                workdir=workdir,
                project_id=project_id,
                parent_op_id=parent_op_id,
                timeout=timeout,
                mem_mb=mem_mb,
                cpu_sec=cpu_sec,
                originating_note_id=originating_note_id,
            )
        finally:
            lock.release(job_id, "completed")
    except SandboxUnavailable as e:
        # Fail-closed: the bwrap backend could not create its sandbox. Surface
        # a LOUD, explicit failure (reason='sandbox_unavailable') with the
        # remediation message. We NEVER silently degrade into the dev backend
        # — the operator must opt in via OPEN_EDIT_SANDBOX_BACKEND=dev. C7 is
        # preserved (run_free_form still returns a result, never raises).
        logger.error("sandbox unavailable: %s", e)
        return FreeFormResult.fail("sandbox_unavailable", str(e))
    except ValueError as e:
        # P9: workdir failed validation.
        return FreeFormResult.fail("invalid_argument", str(e))
    except subprocess.TimeoutExpired:
        return FreeFormResult.fail(
            "parent_watchdog_timeout",
            "sandbox did not exit within timeout+10s",
        )
    except Exception as e:
        # 5a: never-raises safety net. Log the full repr server-side
        # (so on-call has the real stack) but only return the class
        # name + a constant placeholder to the LLM. The previous
        # `repr(e)` echoed absolute paths and exception args back to
        # the caller, which is mild info disclosure and a usable
        # prompt-injection surface.
        logger.exception("run_free_form internal error")
        return FreeFormResult.fail(
            "internal_error",
            f"{type(e).__name__}: <sanitized>",
        )


class SandboxBackend(abc.ABC):
    """Pluggable execution backend for a free-form Python run.

    A backend receives the (already header-validated, JobLock-held) request
    and is responsible for staging the scratch dir, executing the generated
    bootstrap + user code, and returning a FreeFormResult after validating
    ops.jsonl. Backends MUST clean up their scratch dir on every code path.
    """

    #: Stable identifier used in log lines / diagnostics.
    name: str = "abstract"

    @abc.abstractmethod
    def run(
        self,
        *,
        code: str,
        workdir: Path,
        project_id: str,
        parent_op_id: str,
        timeout: int,
        mem_mb: int,
        cpu_sec: int | None,
        originating_note_id: Optional[str],
    ) -> FreeFormResult:
        """Execute the run and return a FreeFormResult (may raise
        SandboxUnavailable to fail closed)."""
        raise NotImplementedError


def _looks_like_bwrap_unavailable(proc: subprocess.CompletedProcess) -> bool:
    """Return True if the process output indicates bwrap could not create
    the namespaces it needs (the failure that makes the sandbox dead).

    We match bwrap's own diagnostics rather than a bare non-zero exit so a
    legitimate script error / usage error is still reported normally.
    """
    stderr = proc.stderr if isinstance(proc.stderr, str) else ""
    needles = (
        "Creating new namespace failed",
        "setting up uid map",
        "Can't mount proc on",
        "No permissions to creating new namespace",
    )
    if any(n in stderr for n in needles):
        return True
    # Generic bwrap namespace error shape.
    return "bwrap:" in stderr and "namespace" in stderr.lower()


class BwrapBackend(SandboxBackend):
    """Default, secure backend: the Rust ``open-edit-sandbox`` binary
    (bwrap + seccomp + rlimits). Behavior is identical to the original
    ``_run_sandboxed`` path, plus fail-closed detection of a dead sandbox.
    """

    name = "bwrap"

    def run(
        self,
        *,
        code: str,
        workdir: Path,
        project_id: str,
        parent_op_id: str,
        timeout: int,
        mem_mb: int,
        cpu_sec: int | None,
        originating_note_id: Optional[str],
    ) -> FreeFormResult:
        try:
            sandbox_bin = _resolve_sandbox_bin()
        except FileNotFoundError as e:
            return FreeFormResult.fail("sandbox_binary_missing", str(e))

        run_id = new_id()
        scratch = workdir / '.sandbox' / f'run_{run_id}'
        try:
            scratch.mkdir(parents=True, exist_ok=True)
            code_path = scratch / 'code.py'
            ops_path = scratch / 'ops.jsonl'
            bootstrap_path = scratch / '_bootstrap.py'

            code_path.write_text(code)
            bootstrap_path.write_text(_render_bootstrap(
                project_id, parent_op_id, originating_note_id,
            ))

            # workdir is the directory that CONTAINS edit_graph.db. In the
            # canonical layout that IS the .open_edit dir (assets sit beside
            # the db at <root>/.open_edit/assets); legacy projects have the
            # db at the root with assets under <root>/.open_edit/assets.
            assets_dir = _assets_dir_for_workdir(workdir)
            source_dirs = sorted(p for p in assets_dir.iterdir() if p.is_dir()) if assets_dir.exists() else []
            meta_file = workdir / 'edit_graph.db'

            proc = subprocess.run(
                [sandbox_bin,
                 '--scratch', str(scratch),
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

            # FAIL-CLOSED: if bwrap could not create its namespaces the
            # sandbox is dead. Never degrade into an unsandboxed run — raise
            # so the operator either fixes the host or explicitly opts into
            # OPEN_EDIT_SANDBOX_BACKEND=dev.
            if _looks_like_bwrap_unavailable(proc):
                logger.error(
                    "bwrap sandbox unavailable; raw stderr=%r", proc.stderr,
                )
                raise SandboxUnavailable(
                    "the bwrap sandbox could not be created "
                    f"({_sanitize_for_detail(proc.stderr)}). "
                    "Fix the host environment (kernel user namespaces / "
                    "resource limits), or for LOCAL DEV ONLY set "
                    f"{SANDBOX_BACKEND_ENV}=dev to run without isolation."
                )

            # M1 (v1.1): the Rust binary's stdout may have noise before the
            # final protocol JSON line. Scan for the LAST line that starts
            # with '{' and parse that. See the long-form comment in history.
            json_line = None
            for line in proc.stdout.splitlines():
                if line.startswith("{"):
                    json_line = line
            try:
                rust = json.loads(json_line) if json_line else None
            except (json.JSONDecodeError, TypeError):
                # 5b: log raw stdout/stderr; return only a sanitized hint.
                logger.warning(
                    "sandbox returned invalid JSON; raw stdout=%r raw stderr=%r",
                    proc.stdout, proc.stderr,
                )
                return FreeFormResult.fail(
                    "sandbox_protocol_error",
                    _sanitize_for_detail(f"invalid JSON: {proc.stdout}"),
                )

            # Defense in depth: if the Rust binary returned with no JSON on
            # stdout (e.g. failed with a usage error before producing protocol
            # output), surface a clear error instead of crashing on
            # `rust.get('ok')`.
            if rust is None:
                # 5b: log raw stderr; surface only a sanitized hint.
                logger.warning(
                    "sandbox produced no protocol JSON; raw stdout=%r raw stderr=%r",
                    proc.stdout, proc.stderr,
                )
                return FreeFormResult.fail(
                    "sandbox_protocol_error",
                    _sanitize_for_detail(
                        f"no protocol JSON in sandbox stdout: {proc.stdout} "
                        f"stderr: {proc.stderr}"
                    ),
                )

            if not rust.get('ok'):
                # 5b: log raw stderr from the child; return only a sanitized hint.
                raw_stderr = rust.get('stderr', '') or ''
                logger.warning(
                    "sandbox returned ok=false reason=%r stderr=%r",
                    rust.get('reason', 'unknown'), raw_stderr,
                )
                return FreeFormResult.fail(
                    rust.get('reason', 'unknown'),
                    _sanitize_for_detail(raw_stderr),
                )

            if not ops_path.exists():
                return FreeFormResult.ok(ops=[], duration_s=0.0)

            try:
                ops, _ = _validate_ops_incrementally(ops_path, workdir)
            except _ValidationError as e:
                return FreeFormResult.fail("invalid_op", str(e))

            return FreeFormResult.ok(ops=ops, duration_s=rust.get('duration_s', 0.0))
        finally:
            # 6a: remove the scratch dir on every code path. Each successful
            # free-form run otherwise leaves ~3 staged files (code.py,
            # _bootstrap.py, ops.jsonl) on disk forever under
            # <workdir>/.sandbox/.
            shutil.rmtree(scratch, ignore_errors=True)


class DevSubprocessBackend(SandboxBackend):
    """UNSAFE local-dev backend. Runs the generated bootstrap + user code in
    a plain ``subprocess`` with NO bwrap, NO seccomp, and NO namespace
    isolation. Used ONLY when the operator explicitly sets
    ``OPEN_EDIT_SANDBOX_BACKEND=dev``.

    It still performs everything EXCEPT the OS-level sandboxing: header
    validation and the JobLock are handled by ``run_free_form`` before we get
    here, and this backend stages the scratch dir and validates ops.jsonl the
    same way the bwrap backend does. The executed code runs with the full
    privileges of the host process — do NOT enable this in production.
    """

    name = "dev"

    def run(
        self,
        *,
        code: str,
        workdir: Path,
        project_id: str,
        parent_op_id: str,
        timeout: int,
        mem_mb: int,
        cpu_sec: int | None,
        originating_note_id: Optional[str],
    ) -> FreeFormResult:
        logger.warning(
            "OPEN_EDIT_SANDBOX_BACKEND=dev: running free-form code WITHOUT "
            "OS-level isolation (no bwrap/seccomp). Local development only."
        )
        run_id = new_id()
        scratch = workdir / '.sandbox' / f'run_{run_id}'
        try:
            scratch.mkdir(parents=True, exist_ok=True)
            code_path = scratch / 'code.py'
            ops_path = scratch / 'ops.jsonl'
            bootstrap_path = scratch / '_bootstrap.py'

            code_path.write_text(code)
            # Point the bootstrap's OPS_FILE at the real scratch path: there
            # is no /scratch bind mount without bwrap.
            bootstrap_path.write_text(_render_bootstrap(
                project_id, parent_op_id, originating_note_id,
                ops_file=str(ops_path),
            ))

            # Mirror the Rust binary's execution model (main.rs): exec the
            # bootstrap, then the user code, in a shared globals dict.
            runner = (
                "g = {'__name__': '__main__'}; "
                f"exec(open({str(bootstrap_path)!r}).read(), g); "
                f"exec(open({str(code_path)!r}).read(), g)"
            )
            proc = subprocess.run(
                [PINNED_PYTHON_BIN, '-c', runner],
                capture_output=True, text=True, timeout=timeout + 10,
            )

            if proc.returncode != 0:
                # 5b: log raw stderr; surface only a sanitized hint.
                logger.warning(
                    "dev sandbox script failed exit=%d stderr=%r",
                    proc.returncode, proc.stderr,
                )
                return FreeFormResult.fail(
                    "sandbox_failed", _sanitize_for_detail(proc.stderr),
                )

            if not ops_path.exists():
                return FreeFormResult.ok(ops=[], duration_s=0.0)

            try:
                ops, _ = _validate_ops_incrementally(ops_path, workdir)
            except _ValidationError as e:
                return FreeFormResult.fail("invalid_op", str(e))

            return FreeFormResult.ok(ops=ops, duration_s=0.0)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


def get_sandbox_backend() -> SandboxBackend:
    """Select the free-form sandbox backend from the environment.

    Env contract (``OPEN_EDIT_SANDBOX_BACKEND``, read at call time):
      - unset on POSIX -> BwrapBackend (default, fail-closed).
      - unset on Windows (``win32``) -> DevSubprocessBackend (no bwrap).
      - ``"bwrap"`` -> BwrapBackend (raises ValueError on Windows).
      - ``"dev"``   -> DevSubprocessBackend (UNSAFE, local / MCP host isolation).

    Any other value raises ValueError so a typo can never silently pick an
    unexpected (or unsandboxed) backend.
    """
    raw = os.environ.get(SANDBOX_BACKEND_ENV)
    if raw is None or not raw.strip():
        if sys.platform == "win32":
            return DevSubprocessBackend()
        return BwrapBackend()
    choice = raw.strip().lower()
    if choice == "bwrap":
        if sys.platform == "win32":
            raise ValueError(
                f"{SANDBOX_BACKEND_ENV}=bwrap is not supported on Windows; "
                "leave unset (defaults to 'dev') or set to 'dev'"
            )
        return BwrapBackend()
    if choice == "dev":
        return DevSubprocessBackend()
    raise ValueError(
        f"{SANDBOX_BACKEND_ENV}={choice!r} is not a valid sandbox backend "
        "(expected 'bwrap' or 'dev')"
    )


def _validate_ops_incrementally(ops_path: Path, workdir: Path) -> tuple[list, object]:
    """C6: validate each op against a working-copy timeline, then apply.

    Reference validation is delegated to
    ``open_edit.ir.validate.validate_op_references(op, project, strict=True)``
    (Task 3.4: the sandbox no longer owns a second reference checker). The
    growing working timeline is passed in so a batch op may reference a clip
    created earlier in the SAME batch; group labels / edit ids are still
    resolved against the stored graph, exactly as before. Violations surface
    as ``OpValidationError`` (the IR layer's reference-error type) wrapped in
    a line-numbered ``_ValidationError``.
    """
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
            errors = validate_op_references(op, project, strict=True, timeline=timeline)
            if errors:
                raise OpValidationError("; ".join(errors))
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
    """Build ``project.assets`` from every asset physically present in the
    store's on-disk sidecars.

    Previously this only included asset hashes already referenced by an
    existing ``add_clip`` op, which created a chicken-and-egg: the first
    clip for a freshly imported asset could never validate because
    ``project.assets`` was empty. Loading the full inventory lets any
    ingested asset be used immediately.
    """
    assets_dir = _assets_dir_for_workdir(workdir)
    if not assets_dir.exists():
        return {}
    assets: dict[str, Asset] = {}
    for meta in assets_dir.rglob("*.meta.json"):
        try:
            asset = Asset.model_validate_json(meta.read_text())
        except Exception:
            continue
        assets[asset.asset_hash] = asset
    return assets


def _render_bootstrap(
    project_id: str,
    parent_op_id: str,
    originating_note_id: Optional[str] = None,
    ops_file: str = "/scratch/ops.jsonl",
) -> str:
    """Generate _bootstrap.py with the IR class and op models inlined.

    C2 preferred fix (Option A): vendor IR into the bootstrap.
    C1: OPS_FILE defaults to /scratch/ops.jsonl (the in-sandbox mount path
    used by the bwrap backend). The dev backend overrides ``ops_file`` with
    the real host scratch path since it has no /scratch bind mount.
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
        "AddHtmlOverlayOp", "RemoveHtmlOverlayOp",
        "AddRemotionCompositionOp", "RemoveRemotionCompositionOp",
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
        "# --- INLINED: open_edit/ir/ids.py:new_id ---",
        new_id_source,
        "",
        "# --- INLINED: open_edit/ir/ids.py:now_iso8601 ---",
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
        f'OPS_FILE = "{ops_file}"',
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
    """Run heavy-compute code in the render sandbox. Returns a RenderResult
    (never raises).

    - ok=True, path=output_path on success.
    - ok=False, detail=<reason> on setup/render failure (missing binary,
      non-zero exit, missing output, timeout, output_path outside workdir,
      FileNotFoundError, etc.).

    Callers (e.g. ``engine.generate_visual``,
    ``pyagent_generate_visual_for_segment``) MUST check ``result.ok`` and
    convert the failure into the appropriate error shape for their caller.

    The Python code receives `OUTPUT_PATH` (the output file to write) and
    `HOME=/tmp` in its environment. It runs inside bwrap with user/pid/ipc/net
    namespaces, no seccomp, cgroup-based memory + CPU limits, and optional
    /dev/dri bind for GPU work.

    On Windows the Linux render-sandbox binary is unavailable; this always
    returns ``ok=False`` with ``detail=render_sandbox_unsupported_on_windows``.
    """
    output_path = Path(output_path)
    if sys.platform == "win32":
        return RenderResult(
            path=output_path,
            ok=False,
            detail="render_sandbox_unsupported_on_windows",
        )
    workdir = Path(workdir)
    # P9: validate workdir FIRST, before any host-side staging
    # (_render_code.py is written to <workdir>/_render_code.py). A hostile
    # tool call with project_path="/etc" must NOT cause _render_code.py to
    # be staged on the host.
    try:
        workdir = _validate_workdir(workdir)
    except ValueError:
        # 5b: do not echo the validation message verbatim either — a path
        # like /etc in the message would leak. The coarse reason tells the
        # caller (engine.generate_visual) the input was rejected; the
        # detailed message is in the logs.
        return RenderResult(path=output_path, ok=False, detail="invalid_argument")
    if workdir not in output_path.resolve().parents and output_path.resolve().parent != workdir:
        # The Rust binary mounts `workdir` at /workdir; the output path must
        # live under the workdir so the rebind exposes it inside the sandbox.
        return RenderResult(
            path=output_path, ok=False,
            detail=f"output_path {output_path} must live under workdir {workdir}",
        )

    code_file = workdir / "_render_code.py"
    try:
        code_file.write_text(code)
    except OSError as e:
        return RenderResult(path=output_path, ok=False, detail=f"failed to stage code: {e}")
    try:
        try:
            binary = _resolve_render_binary()
        except FileNotFoundError as e:
            return RenderResult(path=output_path, ok=False, detail=str(e))
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
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=timeout_sec + 30,
            )
        except subprocess.TimeoutExpired:
            return RenderResult(
                path=output_path, ok=False,
                detail=f"render sandbox timed out after {timeout_sec + 30}s",
            )
        if result.returncode != 0:
            # 5b: log the raw stderr/stdout server-side, but DO NOT echo
            # them into the result detail. Child stderr can contain
            # absolute paths, tokens, or prompt-injection payloads.
            logger.error(
                "render sandbox failed: exit=%d stderr=%r stdout=%r",
                result.returncode, result.stderr, result.stdout,
            )
            return RenderResult(
                path=output_path, ok=False,
                detail=f"render sandbox failed (exit {result.returncode})",
            )
        if not output_path.exists():
            return RenderResult(
                path=output_path, ok=False,
                detail=f"render sandbox did not produce {output_path}",
            )
        return RenderResult(path=output_path, ok=True, detail="")
    finally:
        code_file.unlink(missing_ok=True)
