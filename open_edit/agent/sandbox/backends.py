"""Free-form sandbox execution backends.

``get_sandbox_backend()`` selects the backend from
``OPEN_EDIT_SANDBOX_BACKEND`` at call time. The bwrap backend is fail-closed:
if the kernel refuses to create the namespaces bwrap needs, the run raises
``SandboxUnavailable`` instead of silently degrading to an unsandboxed
execution path (the operator must explicitly opt in to the dev backend).
"""
from __future__ import annotations

import abc
import json
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional

from open_edit.agent.exceptions import FreeFormResult
from open_edit.agent.sandbox.bootstrap import render_bootstrap
from open_edit.agent.sandbox.staging import _assets_dir_for_workdir, stage_and_collect

# Pin Python at module import time.
PINNED_PYTHON_BIN = sys.executable
EXPECTED_PY_VERSION = '.'.join(platform.python_version().split('.')[:2])

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


def resolve_binary(candidates: list[Path], stem: str) -> str:
    """H5: resolve at call time, not at module import.

    P8: resolve via an absolute allow-list, not $PATH. shutil.which trusts
    the user's PATH, so a hostile 'open-edit-sandbox' earlier in PATH
    would win over the legitimate one. The allow-list is fixed absolute
    locations matching the install conventions in the README.

    Raises FileNotFoundError if no allow-listed binary exists. Callers map
    that to FreeFormResult.fail('sandbox_binary_missing', ...) /
    RenderResult(ok=False).
    """
    for c in candidates:
        if c.exists():
            return str(c)
    raise FileNotFoundError(
        f"{stem} binary not found in any allow-listed location "
        f"(tried: {', '.join(str(c) for c in candidates)})"
    )


def _resolve_sandbox_bin() -> str:
    """H5: resolve at call time, not at module import.

    The allow-list is three fixed absolute locations matching the install
    conventions in the README:

      1. ~/.local/bin (user-local pip-style install)
      2. /usr/local/bin (system install)
      3. <repo>/sandbox/target/release (dev workflow)
    """
    candidates = [
        Path.home() / ".local" / "bin" / "open-edit-sandbox",
        Path("/usr/local/bin/open-edit-sandbox"),
        Path(__file__).parent.parent.parent.parent
        / "sandbox" / "target" / "release" / "open-edit-sandbox",
    ]
    return resolve_binary(candidates, "open-edit-sandbox")


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
        Path(__file__).parent.parent.parent.parent
        / "sandbox" / "target" / "release" / "open-edit-render-sandbox",
    ]
    return Path(resolve_binary(candidates, "open-edit-render-sandbox"))


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

        # workdir is the directory that CONTAINS edit_graph.db. In the
        # canonical layout that IS the .open_edit dir (assets sit beside
        # the db at <root>/.open_edit/assets); legacy projects have the
        # db at the root with assets under <root>/.open_edit/assets.
        assets_dir = _assets_dir_for_workdir(workdir)
        source_dirs = sorted(p for p in assets_dir.iterdir() if p.is_dir()) if assets_dir.exists() else []
        meta_file = workdir / 'edit_graph.db'

        def _execute(scratch: Path, code_path: Path, ops_path: Path, bootstrap_path: Path):
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
                ), 0.0

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
                ), 0.0

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
                ), 0.0

            return None, rust.get('duration_s', 0.0)

        return stage_and_collect(
            workdir=workdir,
            code=code,
            render_bootstrap=lambda ops_path: render_bootstrap(
                project_id, parent_op_id, originating_note_id,
            ),
            execute=_execute,
        )


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

        def _execute(scratch: Path, code_path: Path, ops_path: Path, bootstrap_path: Path):
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
                ), 0.0

            return None, 0.0

        return stage_and_collect(
            workdir=workdir,
            code=code,
            # Point the bootstrap's OPS_FILE at the real scratch path: there
            # is no /scratch bind mount without bwrap.
            render_bootstrap=lambda ops_path: render_bootstrap(
                project_id, parent_op_id, originating_note_id,
                ops_file=str(ops_path),
            ),
            execute=_execute,
        )


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
