"""Free-form / render facades: orchestration, error mapping, never-raises.

Kept thin (Task 5.4): header preflight, JobLock, backend selection, workdir
validation, and C7 error mapping live here; execution lives in
``backends.py`` / ``staging.py``; bootstrap codegen lives in ``bootstrap.py``.
"""
from __future__ import annotations

import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from open_edit.agent.exceptions import (
    FreeFormResult, RenderResult, SandboxError,
)
from open_edit.agent.libs import (
    parse_header, version_supported, lib_version_supported,
)
from open_edit.agent.sandbox import backends
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.job_lock import JobLock
from open_edit.storage.paths import ProjectPaths

# H9: hard caps so FreeFormCodeOp.timeout_sec can't hold the JobLock forever.
MAX_FREEFORM_TIMEOUT_SEC = 300
MAX_FREEFORM_MEM_MB = 4096
SANDBOX_DEV_REMEDIATION = (
    "For local productivity, set OPEN_EDIT_SANDBOX_BACKEND=dev "
    "to run without isolation."
)

logger = logging.getLogger(__name__)

_POSIX_PATH_RE = re.compile(r"(?<![\w])/(?:[^/\s]+/)*[^/\s]+")
_WINDOWS_PATH_RE = re.compile(
    r"(?<![\w])[A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s]+"
)
_SANDBOX_SETUP_FAILURES = frozenset({
    "sandbox_binary_missing",
    "sandbox_protocol_error",
    "sandbox_unavailable",
})


def _sanitize_agent_detail(detail: object, *, max_len: int = 300) -> str:
    """Return a bounded, single-line detail safe to show to an agent.

    Backend details can contain child-process output or resolver diagnostics.
    Keep a useful first-line hint while redacting absolute paths so project
    locations and host filesystem layout do not cross the agent boundary.
    """
    if not detail:
        return ""
    text = str(detail).splitlines()[0]
    text = "".join(c for c in text if c.isprintable() or c in " \t")
    text = _WINDOWS_PATH_RE.sub("<path>", text)
    text = _POSIX_PATH_RE.sub("<path>", text)
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def _free_form_failure(reason: str, detail: object = "") -> FreeFormResult:
    """Build a sanitized free-form failure with relevant operator hints."""
    safe_detail = _sanitize_agent_detail(detail)
    if reason in _SANDBOX_SETUP_FAILURES:
        if "OPEN_EDIT_SANDBOX_BACKEND=dev" not in safe_detail:
            safe_detail = (
                f"{safe_detail}. {SANDBOX_DEV_REMEDIATION}"
                if safe_detail
                else SANDBOX_DEV_REMEDIATION
            )
    if "timeout" in reason.lower() or "timed out" in safe_detail.lower():
        timeout_hint = f"timeout cap: {MAX_FREEFORM_TIMEOUT_SEC}s"
        if timeout_hint not in safe_detail:
            safe_detail = (
                f"{safe_detail}. {timeout_hint}"
                if safe_detail
                else timeout_hint
            )
    return FreeFormResult.fail(reason, safe_detail)


def _coerce_positive_int(value: object, field_name: str) -> int:
    """Normalize an integer limit without allowing malformed values through."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        normalized = int(value)
    except Exception as exc:
        # Do not surface exception text from caller-controlled conversion
        # objects; the bridge's result is an agent-facing boundary.
        raise ValueError(f"{field_name} must be a positive integer") from exc
    if normalized <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return normalized


def _validate_workdir(workdir: Path) -> Path:
    """P9: resolve a caller-supplied workdir.

    The AI may operate on any directory; we only require that it is a real
    project (contains ``edit_graph.db``) so the store can locate its DB.
    The workdir must be the directory that directly contains the DB —
    ``ProjectPaths.for_workdir`` derives the project root from it.
    No root/allow-list restriction is applied.

    On any failure, raise ValueError with a clear message. The caller
    catches it and returns the appropriate FreeFormResult / RenderResult.
    Returns the resolved absolute Path on success.
    """
    workdir = Path(workdir).resolve()
    if not workdir.is_dir():
        raise ValueError(f"workdir {workdir} is not a directory")
    # A valid workdir is the directory that directly contains the project's
    # edit_graph.db (canonical ``<root>/.open_edit`` or legacy ``<root>``);
    # ProjectPaths.for_workdir derives the project root from it, so the
    # resolved DB must point back at this workdir.
    paths = ProjectPaths.for_workdir(workdir)
    if not (paths.db_path == workdir / "edit_graph.db" and paths.db_path.exists()):
        raise ValueError(
            f"workdir {workdir} is not a valid project directory "
            f"(missing edit_graph.db)"
        )
    return workdir


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
    try:
        try:
            timeout = _coerce_positive_int(timeout, "timeout")
            mem_mb = _coerce_positive_int(mem_mb, "mem_mb")
        except ValueError as e:
            return _free_form_failure("invalid_argument", str(e))
        if cpu_sec is not None:
            try:
                cpu_sec = _coerce_positive_int(cpu_sec, "cpu_sec")
            except ValueError as e:
                return _free_form_failure("invalid_argument", str(e))
        timeout = min(timeout, MAX_FREEFORM_TIMEOUT_SEC)
        mem_mb = min(mem_mb, MAX_FREEFORM_MEM_MB)
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
            return _free_form_failure("preflight_failed", str(e))
        if not version_supported(declared_version):
            return _free_form_failure(
                "ir_api_version_unsupported", f"got {declared_version}"
            )
        for lib_name, lib_ver in declared_libs.items():
            if not lib_version_supported(lib_name, lib_ver):
                return _free_form_failure(
                    "lib_version_unsupported", f"{lib_name}=={lib_ver}"
                )

        # 2. JobLock (need EditGraphStore; create lazily to fail preflight
        # without touching the db if header is bad).
        db_path = workdir / "edit_graph.db"
        store = EditGraphStore(db_path)
        lock = JobLock(store)
        job_id = lock.try_acquire('free_form_python')
        if job_id is None:
            return _free_form_failure(
                "busy",
                "another job is in progress; retry after it finishes "
                f"(timeout cap: {MAX_FREEFORM_TIMEOUT_SEC}s)",
            )
        try:
            backend = backends.get_sandbox_backend()
            result = backend.run(
                code=code,
                workdir=workdir,
                project_id=project_id,
                parent_op_id=parent_op_id,
                timeout=timeout,
                mem_mb=mem_mb,
                cpu_sec=cpu_sec,
                originating_note_id=originating_note_id,
            )
            if not result.success:
                return _free_form_failure(result.reason, result.detail)
            return result
        finally:
            lock.release(job_id, "completed")
    except backends.SandboxUnavailable as e:
        # Fail-closed: the bwrap backend could not create its sandbox. Surface
        # a LOUD, explicit failure (reason='sandbox_unavailable') with the
        # remediation message. We NEVER silently degrade into the dev backend
        # — the operator must opt in via OPEN_EDIT_SANDBOX_BACKEND=dev. C7 is
        # preserved (run_free_form still returns a result, never raises).
        logger.error("sandbox unavailable: %s", e)
        return _free_form_failure("sandbox_unavailable", str(e))
    except ValueError as e:
        # P9: workdir failed validation — do not echo absolute paths.
        logger.info("run_free_form invalid_argument: %s", e)
        return FreeFormResult.fail(
            "invalid_argument",
            "workdir is not a valid project directory",
        )
    except subprocess.TimeoutExpired:
        return _free_form_failure(
            "parent_watchdog_timeout",
            "sandbox did not exit within timeout+10s "
            f"(requested timeout capped at {MAX_FREEFORM_TIMEOUT_SEC}s)",
        )
    except Exception as e:
        # 5a: never-raises safety net. Log the full repr server-side
        # (so on-call has the real stack) but only return the class
        # name + a constant placeholder to the LLM. The previous
        # `repr(e)` echoed absolute paths and exception args back to
        # the caller, which is mild info disclosure and a usable
        # prompt-injection surface.
        logger.exception("run_free_form internal error")
        return _free_form_failure(
            "internal_error",
            f"{type(e).__name__}: <sanitized>",
        )


def run_render(
    code: str,
    workdir: Path,
    output_path: Path,
    timeout_sec: int = 3600,
    mem_mb: int = 4096,
    with_hwaccel: bool = False,
) -> RenderResult:
    """Run a render and always return a structured result."""
    try:
        return _run_render_impl(
            code, workdir, output_path, timeout_sec, mem_mb, with_hwaccel,
        )
    except FileNotFoundError:
        logger.exception("render sandbox binary disappeared")
        try:
            safe_path = Path(output_path)
        except Exception:
            safe_path = Path(".")
        return RenderResult(
            path=safe_path, ok=False,
            detail="render sandbox binary unavailable",
        )
    except Exception:
        logger.exception("run_render internal error")
        try:
            safe_path = Path(output_path)
        except Exception:
            safe_path = Path(".")
        return RenderResult(path=safe_path, ok=False, detail="internal_error")


def _run_render_impl(
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
            detail="output_path must live under workdir",
        )

    code_file = workdir / "_render_code.py"
    try:
        code_file.write_text(code)
    except OSError as e:
        logger.error("failed to stage render code: %s", e)
        return RenderResult(
            path=output_path, ok=False, detail="failed to stage render code"
        )
    try:
        try:
            binary = backends._resolve_render_binary()
        except FileNotFoundError as e:
            logger.error("render sandbox binary unavailable: %s", e)
            return RenderResult(
                path=output_path,
                ok=False,
                detail="render sandbox binary unavailable",
            )
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
                detail=_sanitize_agent_detail(
                    f"render sandbox timed out after {timeout_sec + 30}s"
                ),
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
                detail="render sandbox did not produce output",
            )
        return RenderResult(path=output_path, ok=True, detail="")
    finally:
        code_file.unlink(missing_ok=True)
