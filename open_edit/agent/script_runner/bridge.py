"""Free-form / render facades: orchestration, error mapping, never-raises.

Kept thin (Task 5.4): header preflight, JobLock, script execution, workdir
validation, and C7 error mapping live here; execution lives in
``execution.py`` / ``staging.py``; bootstrap codegen lives in ``bootstrap.py``.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

from open_edit.agent.exceptions import (
    FreeFormResult,
    RenderResult,
    ScriptValidationError,
)
from open_edit.agent.libs import (
    lib_version_supported,
    parse_header,
    version_supported,
)
from open_edit.agent.script_runner.execution import execute_python, run_script
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.job_lock import JobLock
from open_edit.storage.paths import ProjectPaths

# H9: hard caps so FreeFormCodeOp.timeout_sec can't hold the JobLock forever.
MAX_FREEFORM_TIMEOUT_SEC = 300
logger = logging.getLogger(__name__)

_POSIX_PATH_RE = re.compile(r"(?<![\w])/(?:[^/\s]+/)*[^/\s]+")
_WINDOWS_PATH_RE = re.compile(
    r"(?<![\w])[A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s]+"
)


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
    originating_note_id: str | None = None,
) -> FreeFormResult:
    """Run trusted free-form Python in a subprocess. NEVER raises (C7).

    Memory/CPU arguments validate legacy inputs but do not impose OS limits.
    Scripts inherit the host account permissions.

    `originating_note_id` is stamped on every op produced by the script
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
        except ScriptValidationError as e:
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
            result = run_script(
                code=code,
                workdir=workdir,
                project_id=project_id,
                parent_op_id=parent_op_id,
                timeout=timeout,
                originating_note_id=originating_note_id,
            )
            if not result.success:
                return _free_form_failure(result.reason, result.detail)
            return result
        finally:
            lock.release(job_id, "completed")
    except ValueError as e:
        # P9: workdir failed validation — do not echo absolute paths.
        logger.info("run_free_form invalid_argument: %s", e)
        return FreeFormResult.fail(
            "invalid_argument",
            "workdir is not a valid project directory",
        )
    except subprocess.TimeoutExpired:
        return _free_form_failure(
            "script_timeout",
            "script exceeded its timeout "
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
    """Run trusted graphics Python with OUTPUT_PATH and a wall-clock timeout.

    Memory/GPU arguments are retained for legacy callers; execution inherits
    the host's resources and permissions. Output must be inside the project.
    """
    try:
        output_path = Path(output_path).resolve()
        workdir = _validate_workdir(workdir)
        timeout_sec = min(_coerce_positive_int(timeout_sec, "timeout_sec"), 3600)
        if workdir not in output_path.parents:
            return RenderResult(output_path, False, "output_path must live under workdir")
        # Render into a fresh path so an old output cannot disguise a failed run.
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="render-", dir=workdir) as scratch:
            staged_output = Path(scratch) / output_path.name
            code_path = Path(scratch) / "render.py"
            code_path.write_text(code, encoding="utf-8")
            env = dict(os.environ, OUTPUT_PATH=str(staged_output))
            proc, _ = execute_python([str(code_path)], workdir, timeout_sec, env=env)
            if proc.returncode:
                return RenderResult(output_path, False, f"render script failed (exit {proc.returncode})")
            if not staged_output.is_file() or not staged_output.stat().st_size:
                return RenderResult(output_path, False, "render script did not produce output")
            staged_output.replace(output_path)
        return RenderResult(output_path)
    except subprocess.TimeoutExpired:
        return RenderResult(Path(output_path), False, "render script timed out")
    except ValueError:
        return RenderResult(Path(output_path), False, "invalid_argument")
    except Exception:
        logger.exception("run_render internal error")
        return RenderResult(Path(output_path), False, "internal_error")
