# Phase 3 — Free-Form Python Sandbox (Design)

**Date:** 2026-07-21
**Status:** Approved
**Supersedes:** §6.8 of `2026-07-20-open-edit-design.md` (which remains the high-level
direction; this spec is the implementation contract)
**Phase:** 3 of 5
**Estimated effort:** 1 week (down from the 2-3 weeks in the parent spec)

---

## 1. Scope and v1 trust model

Phase 3 implements the **subprocess sandbox** for free-form Python code
(`FreeFormCodeOp`). It is the bridge between the AI agent's need to run arbitrary
logic and the system's need to keep source media and resources safe.

**v1 trust model:** the sandbox exists to prevent **accidental** corruption,
runaway resource use, and accidental network calls. It is **not** a security
boundary against malicious code. Tightening to a real seccomp allowlist and full
landlock is **v1.1** (see §10).

**Out of v1 scope (explicitly):**
- `--with-hwaccel` flag (no demo uses VAAPI/DRM in v1)
- A `firejail` fallback (parent spec §6.8 mentions this; v1 uses bwrap, which is
  the path we picked — see §2.1)
- Hardened seccomp allowlist derived from strace fixtures (v1 ships a
  network-only denylist)
- Adversarial bypass testing (v1 tests positive safety properties only — see §7)

---

## 2. Architecture

### 2.1 Component overview

```
                           ┌────────────────────┐
   apply.py receives ──▶   │ sandbox_bridge.py  │  (Python)
   FreeFormCodeOp          │  open_edit/agent/  │
                           └─────────┬──────────┘
                                     │ subprocess.run
                                     ▼
                           ┌────────────────────┐
                           │ open-edit-sandbox  │  (Rust binary)
                           │ sandbox/src/       │
                           │ - main.rs          │
                           │ - jail.rs          │
                           │ - network_denylist │
                           └─────────┬──────────┘
                                     │ exec
                                     ▼
                           ┌────────────────────┐
                           │ bwrap              │  (existing, /usr/bin/bwrap)
                           │ - unshare net/pid  │
                           │ - ro-bind /usr     │
                           │ - ro-bind sources  │
                           │ - rw scratch       │
                           └─────────┬──────────┘
                                     │ exec
                                     ▼
                           ┌────────────────────┐
                           │ python3 (pinned)   │  (sys.executable of parent)
                           │ runs _bootstrap.py │
                           │ then code.py       │
                           └────────────────────┘
```

**Why bwrap (not landlock directly):** bwrap is a well-tested userland tool that
gives us unprivileged filesystem isolation on Linux 4.x+ kernels without writing
a custom landlock ABI. Landlock ABI varies across kernel versions; bwrap abstracts
it. v1.1 may drop bwrap and call landlock directly via the `landlock` crate.

### 2.2 Flow (single free-form run)

```
1. apply.py calls sandbox_bridge.run_free_form(
       code, workdir, project_id, parent_op_id,
       timeout=30, mem_mb=512, cpu_sec=30
   )

2. PREFLIGHT (in Python, before spawning Rust):
   a. parse code header: # ir_api_version: X.Y; libs: {name: ver, ...}
      on missing/malformed header → FreeFormResult.fail("preflight_failed", ...)
   b. check ir_api_version is in open_edit/agent/allowed_libs.txt
      on mismatch → fail("ir_api_version_unsupported", ...)
   c. check each (lib_name, lib_ver) is in allowed_libs.txt
      on any mismatch → fail("lib_version_unsupported", ...)

3. JOBLOCK (single-slot for free-form runs):
   JobLock.try_acquire('free_form_python', timeout=5)
   on busy → fail("busy", "another free-form run is in progress")

4. STAGE (in <workdir>/.sandbox/run_<id>/):
   - write code.py (the user's code, unchanged)
   - write _bootstrap.py (injected: sets up `ir` global, _FlushingBuffer writes
     ops.jsonl on every op append, stamps parent_id on every op)
   - ops.jsonl will be created by the child as it runs

5. INVOKE RUST BINARY (example with two sources resolved from <workdir>/assets/):
   open-edit-sandbox \
     --code <workdir>/.sandbox/run_<id>/code.py \
     --scratch <workdir>/.sandbox/run_<id>      (rw: ops.jsonl + temps) \
     --source-ro <workdir>/assets/clip_a        (one --source-ro per asset dir) \
     --source-ro <workdir>/assets/clip_b \
     --project-meta <workdir>/edit_graph.db     (ro: project metadata) \
     --python-bin <sys.executable of open_edit>  (pinned) \
     --expected-py-version <platform.python_version()> \
     --timeout 30 --mem 512 --cpu 30 \
     --ops-output <workdir>/.sandbox/run_<id>/ops.jsonl \
     --json
   (In practice, sandbox_bridge iterates <workdir>/assets/*/ and adds one
   --source-ro per directory. The above is the fully-resolved example.)

6. RUST does:
   a. install seccomp network denylist (block: socket, connect, bind, accept,
      listen, sendto, recvfrom, sendmsg, recvmsg)
   b. set rlimits: RLIMIT_AS=512M, RLIMIT_CPU=30s, RLIMIT_NOFILE=256,
      RLIMIT_NPROC=64
   c. exec bwrap with:
      --unshare-user --unshare-pid --unshare-ipc --unshare-uts --unshare-net
      --die-with-parent
      --ro-bind /usr /usr
      --ro-bind /lib /lib
      --ro-bind /etc /etc
      --ro-bind <source1> /mnt/src1
      --ro-bind <source2> /mnt/src2
      --ro-bind <project-meta> /mnt/meta
      --bind <scratch> /scratch
      --tmpfs /tmp --tmpfs /home --tmpfs /var
      --dev /dev/null --dev /dev/urandom
      --new-session
      -- <python-bin> -c "
            import sys; assert sys.version_info[:2] == <expected>
            g = {'__name__': '__main__'}
            exec(open('/scratch/_bootstrap.py').read(), g)
            exec(open('/scratch/code.py').read(), g)
        "
   d. on bwrap exit: capture exit code, stderr, wall-clock duration
   e. write JSON to stdout: {"ok": bool, "exit_code": int, "reason": str?,
      "duration_s": float, "stderr": str}

7. ATOMIC COMMIT GATE (in Python):
   a. parse Rust JSON. on parse error → fail("sandbox_protocol_error", ...)
   b. if rust.ok == false:
      - unlink ops.jsonl (atomic: clean exit ONLY)
      - return FreeFormResult.fail(rust.reason, rust.stderr)
   c. if rust.ok == true:
      - assert ops.jsonl exists; on missing → fail("ops_missing", ...)
      - read line by line, parse each as Pydantic OperationUnion
      - on any parse failure: unlink ops.jsonl, return fail("invalid_op", ...)
      - on referential integrity failure (asset/track/clip/effect not in
        project): unlink ops.jsonl, return fail("invalid_op", ...)

8. RETURN FreeFormResult(success=True, ops=[...], duration_s=...)
   apply.py iterates the ops and appends each to the edit graph (parent_id is
   already stamped on each op by _FlushingBuffer → IR.add_clip at build time)
```

### 2.3 Two halves of the change

**Rust half (sandbox/):** new code, ~250 lines, has its own Cargo.toml, lives
in `open_edit/sandbox/`. Builds to a binary `open-edit-sandbox` that is invoked
by the Python wrapper.

**Python half (open_edit/):** new code (~500 lines) + small extensions to
existing code (~50 lines).

---

## 3. Rust binary: `open-edit-sandbox`

### 3.1 Files

| File | Lines (est) | Purpose |
|------|-------------|---------|
| `sandbox/Cargo.toml` | ~25 | package metadata, deps: clap, nix, libseccomp-rs, anyhow |
| `sandbox/src/main.rs` | ~80 | clap CLI parse, call into jail, output JSON |
| `sandbox/src/jail.rs` | ~120 | install seccomp, set rlimits, exec bwrap |
| `sandbox/src/network_denylist.rs` | ~30 | the network-only denylist policy |
| `sandbox/tests/integration.rs` | ~150 | end-to-end tests |
| `sandbox/observations/*.txt` | existing | Phase 0 strace fixtures (informative) |

### 3.2 CLI (clap)

```
open-edit-sandbox
  --code <PATH>               # Python file to run
  --scratch <PATH>            # rw directory for ops.jsonl + temps
  --source-ro <PATH>          # ro directory of source media (repeatable, 0+)
  --project-meta <PATH>       # ro file (edit_graph.db)
  --python-bin <PATH>         # default: sys.executable of parent (passed by sandbox_bridge)
  --expected-py-version <STR> # e.g. "3.14.5" — sandbox asserts and exits if mismatch
  --timeout <SEC>             # default: 30 (wall clock, enforced by parent watchdog)
  --cpu <SEC>                 # default: 30 (RLIMIT_CPU)
  --mem <MB>                  # default: 512 (RLIMIT_AS)
  --ops-output <PATH>         # default: <scratch>/ops.jsonl
  --json                      # machine-readable output
```

### 3.3 Output JSON

**Success:**
```json
{"ok": true, "exit_code": 0, "duration_s": 1.23, "stderr": ""}
```

**Failure (one of these reason codes):**

| reason | exit_code | meaning |
|--------|-----------|---------|
| `timeout` | -1 | parent watchdog killed the process |
| `nonzero_exit` | int (real exit) | Python exited with non-zero (uncaught exception) |
| `py_version_mismatch` | -1 | sandbox Python version != --expected-py-version |
| `seccomp_violation` | -1 | child attempted a blocked syscall |
| `oom_killed` | 139 | RLIMIT_AS hit (SIGSEGV) |
| `cpu_limit_killed` | 137 | RLIMIT_CPU hit (SIGXCPU) |
| `nofile_limit` | 1 | EMFILE |
| `nproc_limit` | 1 | EAGAIN |
| `bwrap_unavailable` | -1 | bwrap not on PATH |
| `userns_unavailable` | -1 | --unshare-user failed non-trivially |
| `pidns_unavailable` | -1 | --unshare-pid failed non-trivially |
| `setup_error` | -1 | seccomp/rlimit/bwrap exec itself failed |

### 3.4 Seccomp policy: `network_denylist`

The v1 policy is a **network-only denylist**, not a true allowlist. We block
only:

- `socket`
- `connect`
- `bind`
- `accept`
- `listen`
- `sendto`
- `recvfrom`
- `sendmsg`
- `recvmsg`

All other syscalls pass. Rationale: a tighter allowlist (the original §6.8
design) requires analyzing every syscall Python and SQLite make, plus
melt/ffmpeg if invoked from inside the sandbox. The Phase 0 strace fixtures
cover melt/ffmpeg/ffprobe, not the Python child. v1.1 will tighten to a real
allowlist (see §10).

The v1 trust model is documented and explicit: this is "prevent accidental
network calls and runaway resources," not a malicious-code defense.

### 3.5 rlimits (set in the Rust binary before exec)

| rlimit | value | effect on hit |
|--------|-------|---------------|
| `RLIMIT_AS` | `--mem` MB | SIGSEGV; child exits 139; reason=`oom_killed` |
| `RLIMIT_CPU` | `--cpu` seconds | SIGXCPU; child exits 137; reason=`cpu_limit_killed` |
| `RLIMIT_NOFILE` | 256 | Python raises `OSError(EMFILE)`; child exits 1; reason=`nofile_limit` |
| `RLIMIT_NPROC` | 64 | Python raises `OSError(EAGAIN)`; child exits 1; reason=`nproc_limit` |

### 3.6 Namespaces: fail loud, no `-try`

The bwrap invocation uses:

```
--unshare-user --unshare-pid --unshare-ipc --unshare-uts --unshare-net
```

If `--unshare-user` or `--unshare-pid` fails, bwrap exits non-trivially; the
Rust binary maps this to `userns_unavailable` or `pidns_unavailable` and the
parent gets a `FreeFormResult.fail(...)`. **No silent degradation.**

### 3.7 CPU default: 30s is sufficient

30s CPU is the v1 default. The boundary is: free-form Python is for **per-op
lightweight work** (frame extraction, keyframe math, color analysis, batch
`AddClipOp` generation). Full melt renders go through the Phase 2 render
orchestrator, not through the sandbox. If a free-form script needs to call
melt for an in-sandbox preview, that's allowed but the user should know the
CPU limit is tight.

### 3.8 Build and install

`cargo build --release` produces `target/release/open-edit-sandbox`. The build
is a step in the Phase 3 plan, not a runtime dependency. The binary must be
on `$PATH` for sandbox_bridge to find it (resolved via `shutil.which`).

If the binary is not found at runtime, `run_free_form` returns
`FreeFormResult.fail("sandbox_binary_missing", ...)`. No fallback to direct
Python execution.

---

## 4. Python side

### 4.1 `open_edit/ir/api.py` — real implementation

Replaces the 25-line stub. ~250 lines. The class:

```python
class IR:
    """Free-form Python IR API. Each method builds one Pydantic op and
    appends it to the buffer (which the sandbox wires to ops.jsonl)."""

    def __init__(self, ops_buffer, project_id: str, parent_op_id: str):
        self._ops = ops_buffer
        self._project_id = project_id
        self._parent_op_id = parent_op_id

    def add_clip(self, asset_hash: str, track_id: str, position_sec: float,
                 in_point_sec: float = 0.0, out_point_sec: float | None = None,
                 label: str | None = None) -> str:
        """Append AddClipOp; return generated clip_id."""
        clip_id = new_id()
        op = AddClipOp(
            edit_id=new_id(),
            project_id=self._project_id,
            parent_id=self._parent_op_id,  # STAMPED AT BUILD TIME
            clip_id=clip_id,
            asset_hash=asset_hash,
            track_id=track_id,
            position_sec=position_sec,
            in_point_sec=in_point_sec,
            out_point_sec=out_point_sec,
            label=label,
        )
        self._ops.append(op)  # _FlushingBuffer writes JSONL here
        return clip_id

    # ... 11 more methods: trim_clip, move_clip, remove_clip, add_transition,
    #     add_effect, set_keyframe, set_audio_gain, normalize_audio,
    #     group_edits, raw_mlt_xml, free_form_code
```

**Validation policy:** each method builds the Pydantic model. Schema errors
fail at build time. Referential validation (does `asset_hash` exist? does
`track_id` exist?) is **not** done in `IR.add_clip`; it is done in
`sandbox_bridge._validate_references` after reading ops.jsonl. This way, if
any op in a batch has a bad reference, the whole batch is rejected with a
clear error pointing at the offending line.

### 4.2 The bootstrap module (sandbox_bridge writes this into the scratch dir)

```python
# <scratch>/_bootstrap.py — injected by sandbox_bridge, NOT user-written
import json
from open_edit.ir.api import IR
from open_edit.ir.types import OperationUnion

PROJECT_ID = "<injected by sandbox_bridge>"
PARENT_OP_ID = "<injected by sandbox_bridge>"
OPS_FILE = "<injected by sandbox_bridge, = --ops-output>"

# A list that writes each appended op to OPS_FILE as one JSONL line.
class _FlushingBuffer(list):
    def append(self, op):
        super().append(op)
        with open(OPS_FILE, "a") as f:
            f.write(op.model_dump_json() + "\n")

_ops: list[OperationUnion] = _FlushingBuffer()
ir = IR(_ops, project_id=PROJECT_ID, parent_op_id=PARENT_OP_ID)
```

**Why this works:**
- After `_bootstrap.py` runs, `ir` is a global in the user script's namespace.
  No import needed.
- Every `ir.<method>(...)` call appends to the in-memory list **and** writes a
  JSONL line to `ops.jsonl` immediately and durably. No in-memory state that
  could be lost on crash.
- The bwrap exec is `<python-bin> -c "exec(_bootstrap); exec(code.py)"` so
  both run in the same process and share `ir` in globals.

### 4.3 `open_edit/agent/sandbox_bridge.py`

```python
import json
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from open_edit.agent.exceptions import FreeFormResult, SandboxError
from open_edit.agent.libs import parse_header, version_supported, lib_version_supported
from open_edit.ir.types import OperationUnion
from open_edit.pydantic_compat import TypeAdapter
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.job_lock import JobLock, JobLockBusy

# Constants — pin Python at module import time
PINNED_PYTHON_BIN = sys.executable
EXPECTED_PY_VERSION = platform.python_version()
SANDBOX_BIN = shutil.which("open-edit-sandbox") or "open-edit-sandbox"


def run_free_form(
    code: str,
    workdir: Path,
    project_id: str,
    parent_op_id: str,
    *,
    timeout: int = 30,
    mem_mb: int = 512,
    cpu_sec: int | None = None,
) -> FreeFormResult:
    """Run free-form Python. ALWAYS returns FreeFormResult, never raises."""

    # 1. Preflight
    try:
        declared_version, declared_libs = parse_header(code)
    except SandboxError as e:
        return FreeFormResult.fail("preflight_failed", str(e))
    if not version_supported(declared_version):
        return FreeFormResult.fail("ir_api_version_unsupported", f"got {declared_version}")
    for lib_name, lib_ver in declared_libs.items():
        if not lib_version_supported(lib_name, lib_ver):
            return FreeFormResult.fail("lib_version_unsupported", f"{lib_name}=={lib_ver}")

    # 2. JobLock
    try:
        with JobLock.try_acquire('free_form_python', timeout=5):
            return _run_sandboxed(
                code, workdir, project_id, parent_op_id, timeout, mem_mb, cpu_sec
            )
    except JobLockBusy:
        return FreeFormResult.fail("busy", "another free-form run is in progress")
    except subprocess.TimeoutExpired:
        return FreeFormResult.fail("parent_watchdog_timeout", "sandbox did not exit within timeout+10s")


def _run_sandboxed(code, workdir, project_id, parent_op_id, timeout, mem_mb, cpu_sec):
    run_id = new_id()
    scratch = workdir / '.sandbox' / f'run_{run_id}'
    scratch.mkdir(parents=True, exist_ok=True)
    code_path = scratch / 'code.py'
    ops_path = scratch / 'ops.jsonl'
    bootstrap_path = scratch / '_bootstrap.py'

    code_path.write_text(code)
    bootstrap_path.write_text(_render_bootstrap(project_id, parent_op_id, ops_path))

    # Discover sources (ro-bound for the child)
    assets_dir = workdir / 'assets'
    source_dirs = sorted(p for p in assets_dir.iterdir() if p.is_dir()) if assets_dir.exists() else []
    meta_file = workdir / 'edit_graph.db'

    # Invoke Rust binary
    try:
        proc = subprocess.run(
            [SANDBOX_BIN,
             '--code', str(code_path),
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
    except FileNotFoundError:
        return FreeFormResult.fail("sandbox_binary_missing", f"{SANDBOX_BIN} not found")

    # 3. Parse Rust JSON
    try:
        rust = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return FreeFormResult.fail("sandbox_protocol_error", f"invalid JSON: {proc.stdout[:200]}")

    # 4. Atomic commit gate
    if not rust.get('ok'):
        ops_path.unlink(missing_ok=True)  # discard partial ops
        return FreeFormResult.fail(rust.get('reason', 'unknown'), rust.get('stderr', ''))

    if not ops_path.exists():
        return FreeFormResult.fail("ops_missing", "sandbox ok but ops.jsonl is missing")

    # 5. Read + validate ops.jsonl (Pydantic + referential)
    ops: list[OperationUnion] = []
    # Load the current project from the edit graph so referential checks
    # have authoritative asset/track/clip/effect IDs to compare against.
    project = _load_project_for_validation(workdir)
    for line_num, line in enumerate(ops_path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            op_dict = json.loads(line)
            op = TypeAdapter(OperationUnion).validate_python(op_dict)
            _validate_references(op, project)
            ops.append(op)
        except (json.JSONDecodeError, ValidationError, ReferenceError) as e:
            ops_path.unlink(missing_ok=True)
            return FreeFormResult.fail("invalid_op", f"line {line_num}: {e}")

    return FreeFormResult.ok(ops=ops, duration_s=rust.get('duration_s', 0.0))


def _load_project_for_validation(workdir: Path) -> Project:
    """Load the project from workdir/edit_graph.db for referential checks.

    Uses the same EditGraphStore as apply.py. We don't open the .sandbox
    scratch area — only the canonical project state.
    """
    db_path = workdir / 'edit_graph.db'
    if not db_path.exists():
        raise SandboxError(f"project db not found: {db_path}")
    store = EditGraphStore(db_path)
    assets = _load_assets_via_store(workdir)  # uses AssetStore
    return Project(
        name=workdir.name,
        workdir=workdir,
        assets=assets,
        edit_graph=store.load_all(),
    )


def _load_assets_via_store(workdir: Path) -> dict[str, "Asset"]:
    """Read asset metadata via the global AssetStore. Hash-list comes from
    iterating the project's edit graph and pulling out referenced asset_hash
    values (only assets actually used by an op need to be available)."""
    from open_edit.storage.assets import AssetStore
    db_path = workdir / 'edit_graph.db'
    store = EditGraphStore(db_path)
    asset_hashes: set[str] = set()
    for op in store.load_all():
        if isinstance(op, AddClipOp):
            asset_hashes.add(op.asset_hash)
    asset_store = AssetStore()  # uses default ~/.open-edit/assets
    assets = {}
    for h in asset_hashes:
        asset = asset_store.get(h)
        if asset is not None:
            assets[h] = asset
    return assets


def _validate_references(op: OperationUnion, project: Project) -> None:
    """Raise ReferenceError if op references non-existent project entity."""
    # Build the set of valid IDs by deriving the timeline from the current
    # edit graph (this is what the actual MLT render does, so it's the right
    # source of truth for "does this id exist?").
    timeline = derive_timeline(project)

    asset_hashes = {a.asset_hash for a in project.assets.values()}
    track_ids = {t.track_id for t in timeline.tracks}
    clip_ids: set[str] = set()
    for t in timeline.tracks:
        for c in t.clips:
            clip_ids.add(c.clip_id)
    effect_ids: set[str] = set()
    for t in timeline.tracks:
        for c in t.clips:
            for e in c.effects:
                effect_ids.add(e.effect_id)
        for e in t.effects:
            effect_ids.add(e.effect_id)

    if isinstance(op, AddClipOp):
        if op.asset_hash not in asset_hashes:
            raise ReferenceError(f"asset_hash {op.asset_hash!r} not in project")
        if op.track_id not in track_ids:
            raise ReferenceError(f"track_id {op.track_id!r} not in project")
    if isinstance(op, (TrimClipOp, MoveClipOp, RemoveClipOp)):
        if op.clip_id not in clip_ids:
            raise ReferenceError(f"clip_id {op.clip_id!r} not in project")
    if isinstance(op, (AddEffectOp, SetKeyframeOp, SetAudioGainOp)):
        if op.target_id not in clip_ids and op.target_id not in track_ids:
            raise ReferenceError(f"target_id {op.target_id!r} not in project")
    if op.parent_id is None:
        raise ReferenceError("op has no parent_id (IR class should stamp at build time)")


def _render_bootstrap(project_id: str, parent_op_id: str, ops_path: Path) -> str:
    return textwrap.dedent(f'''
        import json
        from open_edit.ir.api import IR
        from open_edit.ir.types import OperationUnion

        PROJECT_ID = {project_id!r}
        PARENT_OP_ID = {parent_op_id!r}
        OPS_FILE = {str(ops_path)!r}

        class _FlushingBuffer(list):
            def append(self, op):
                super().append(op)
                with open(OPS_FILE, "a") as f:
                    f.write(op.model_dump_json() + "\\n")

        _ops = _FlushingBuffer()
        ir = IR(_ops, project_id=PROJECT_ID, parent_op_id=PARENT_OP_ID)
    ''')
```

### 4.4 `open_edit/agent/exceptions.py`

```python
from dataclasses import dataclass, field
from open_edit.ir.types import OperationUnion


@dataclass
class FreeFormResult:
    success: bool
    ops: list[OperationUnion] = field(default_factory=list)
    reason: str = ""
    detail: str = ""
    duration_s: float = 0.0

    @classmethod
    def ok(cls, ops, duration_s):
        return cls(success=True, ops=ops, duration_s=duration_s)

    @classmethod
    def fail(cls, reason: str, detail: str = ""):
        return cls(success=False, reason=reason, detail=detail)


class SandboxError(Exception):
    """Raised for unrecoverable preflight/setup errors (NOT runtime)."""
```

### 4.5 `open_edit/agent/libs.py` — header parsing + allowed_libs check

```python
import re
from pathlib import Path

_HEADER_RE = re.compile(
    r'^\s*#\s*ir_api_version:\s*(\S+)\s*;\s*libs:\s*(\{.*?\})\s*$',
    re.MULTILINE,
)

ALLOWED_LIBS_PATH = Path(__file__).parent / "allowed_libs.txt"


def parse_header(code: str) -> tuple[str, dict[str, str]]:
    """Parse `# ir_api_version: X.Y; libs: {name: ver, ...}` from code.
    
    Returns (version, libs_dict). Raises SandboxError on missing/malformed header.
    """
    m = _HEADER_RE.search(code)
    if not m:
        raise SandboxError("missing or malformed ir_api_version header")
    version = m.group(1)
    libs = _safe_eval_libs(m.group(2))  # ast.literal_eval on the libs dict
    return version, libs


def version_supported(declared: str) -> bool:
    manifest = _load_manifest()
    return declared in manifest.get("versions", [])


def lib_version_supported(name: str, ver: str) -> bool:
    manifest = _load_manifest()
    return ver in manifest.get("libs", {}).get(name, [])


# ... _load_manifest reads allowed_libs.txt, _safe_eval_libs uses ast.literal_eval
```

### 4.6 `open_edit/agent/allowed_libs.txt` — the manifest

```
# ir_api_version: 0.1
# Each line under [versions] is a supported ir_api_version string.
# Each line under [libs.<name>] is a supported <name>==<version>.

[versions]
0.1

[libs.numpy]
1.26.4
2.1.3

[libs.opencv-python]
4.8.1.78
4.10.0.84

[libs.pillow]
10.4.0
11.0.0
```

Manifest format is intentionally a flat text file. A future "librarian" tool
(probably a v1.1 sub-phase) will populate it from the actual `site-packages`.

### 4.7 `open_edit/ir/apply.py` — new `_apply_free_form_code` branch

```python
def _apply_free_form_code(op: FreeFormCodeOp, project: Project) -> Project:
    result = sandbox_bridge.run_free_form(
        op.code,
        Path(project.workdir),
        project_id=project.project_id,
        parent_op_id=op.edit_id,
        timeout=op.timeout_sec,
        mem_mb=op.mem_mb,
    )
    if not result.success:
        raise ApplyError(
            f"free-form run failed: {result.reason}: {result.detail}"
        )
    # parent_id already stamped on each op by IR.<method> at build time
    project.edit_graph.extend(result.ops)
    return project
```

### 4.8 Cross-phase change: `Project.workdir`

Phase 0+1 built `Project` without a `workdir` field. Phase 3 adds:

```python
class Project(BaseModel):
    project_id: str = Field(default_factory=new_id)
    name: str
    workdir: Path  # NEW in Phase 3
    created_at: str = Field(default_factory=now_iso8601)
    assets: dict[str, Asset] = Field(default_factory=dict)
    edit_graph: list[OperationUnion] = Field(default_factory=list)
```

Existing fixtures that construct `Project` directly (3-4 in
`tests/testdata/`) need `workdir=tmp_path` added. This is a one-line change
per fixture.

### 4.9 `FreeFormCodeOp` extension

```python
class FreeFormCodeOp(Operation):
    kind: Literal["free_form_code"] = "free_form_code"
    code: str
    timeout_sec: int = 30      # optional override
    mem_mb: int = 512          # optional override
    label: str | None = None
```

---

## 5. Files added / changed

### New files

| File | Lines (est) | Purpose |
|------|-------------|---------|
| `sandbox/Cargo.toml` | 25 | package metadata |
| `sandbox/src/main.rs` | 80 | CLI + orchestration |
| `sandbox/src/jail.rs` | 120 | seccomp + rlimits + bwrap |
| `sandbox/src/network_denylist.rs` | 30 | the denylist policy |
| `sandbox/tests/integration.rs` | 150 | end-to-end tests |
| `open_edit/agent/__init__.py` | 3 | package marker |
| `open_edit/agent/sandbox_bridge.py` | 180 | the wrapper |
| `open_edit/agent/exceptions.py` | 25 | FreeFormResult, SandboxError |
| `open_edit/agent/libs.py` | 50 | header parsing, manifest lookup |
| `open_edit/agent/allowed_libs.txt` | 15 | ir_api_version + libs manifest |
| `tests/test_sandbox_bridge.py` | 100 | unit tests (mock Rust binary) |
| `tests/test_ir_api.py` | 100 | unit tests of IR methods |
| `tests/test_free_form_e2e.py` | 150 | 50-line script → child ops in graph |
| `open_edit/ir/api.py` (REWRITE) | 250 | 12 methods (replaces 25-line stub) |

### Modified files

| File | Change |
|------|--------|
| `open_edit/ir/types.py` | Add `workdir: Path` to `Project`; add `timeout_sec`, `mem_mb`, `label` to `FreeFormCodeOp` |
| `open_edit/ir/apply.py` | Add `_apply_free_form_code` branch (~30 lines) |
| `tests/conftest.py` | Add `tmp_project_with_assets` fixture (skip if bwrap missing) |
| `tests/testdata/*/edit_graph.json` (3-4 files) | Add `workdir` field |

**Total: ~1280 lines new + ~60 lines modified.**

---

## 6. End-to-end test (the "Done when" criterion from the parent spec)

```python
# tests/test_free_form_e2e.py
import textwrap
import shutil
import pytest
from pathlib import Path

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bubblewrap not installed",
)


@pytest.fixture
def tmp_project_with_assets(tmp_path):
    """A project with one asset pre-ingested, suitable for free-form runs."""
    from open_edit.ir.types import Project, Asset
    asset = Asset(
        asset_hash="abc123",
        original_path=Path("/tmp/clip.mp4"),
        stored_path=Path("/tmp/.open-edit/assets/ab/abc123"),
        type="video",
        duration_sec=10.0,
        fps=30.0,
        width=1920,
        height=1080,
        codec="h264",
        has_audio=True,
    )
    (tmp_path / 'assets' / 'abc123').mkdir(parents=True)
    (tmp_path / 'edit_graph.db').touch()
    return Project(
        name="test",
        workdir=tmp_path,
        assets={asset.asset_hash: asset},
    )


def test_pyagent_run_python_50_lines(tmp_project_with_assets):
    code = textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        # `ir` is provided by _bootstrap.py
        for i in range(50):
            ir.add_clip(
                asset_hash="abc123",
                track_id="video_main",
                position_sec=i * 2.0,
                label=f"clip_{i}",
            )
    ''')
    op = FreeFormCodeOp(
        edit_id="e1",
        project_id=tmp_project_with_assets.project_id,
        code=code,
    )
    updated = apply_operation(tmp_project_with_assets, op)

    child_ops = [
        o for o in updated.edit_graph
        if getattr(o, 'parent_id', None) == "e1"
    ]
    assert len(child_ops) == 50
    assert all(isinstance(o, AddClipOp) for o in child_ops)
    assert all(o.position_sec == i * 2.0 for i, o in enumerate(child_ops))
```

This test exercises the full pipeline: preflight → JobLock → Rust binary →
bwrap → Python (parent's runtime) → _bootstrap.py → user's code.py →
_flushing buffer → ops.jsonl → atomic commit gate → Pydantic validation →
referential check → return to apply.py → extend edit graph.

A second test (`test_free_form_then_render`) does the same plus a full melt
render of the resulting timeline, asserting the output mp4 is non-empty.

---

## 7. Testing strategy

### 7.1 Four layers

**Layer 1: Rust unit tests** (`sandbox/tests/`)
- `network_denylist_blocks_socket` — `socket(AF_INET, SOCK_STREAM)` → EPERM
- `rlimit_as_kills_on_overuse` — allocate 600 MB with 512 limit → exit 139
- `rlimit_cpu_kills_on_overuse` — `while True: pass` → SIGXCPU
- `userns_unavailable_fails_loud` — if userns unavailable, exit with reason
- `bwrap_unavailable` — without bwrap on PATH, exit with reason

**Layer 2: Rust integration tests** (`sandbox/tests/integration.rs`)
- `e2e_python_runs_and_writes_ops` — code.py calls `ir.add_clip(...)`; assert
  ops.jsonl has 1 line
- `e2e_network_blocked` — script tries `socket.socket()`; assert ok=false and
  reason matches
- `e2e_source_ro_blocks_writes` — script tries `open('/mnt/src/clip.mp4', 'w')`;
  assert PermissionError in stderr
- `e2e_timeout_kills_runaway` — `time.sleep(60)` with --timeout 5; assert exit
  before 15s wall clock
- `e2e_python_version_mismatch` — pass `--expected-py-version "3.99"`; assert
  reason=py_version_mismatch
- `e2e_parent_id_stamped` — script calls `ir.add_clip(...)`; read ops.jsonl;
  assert each op's parent_id field equals the parent_op_id we injected

**Layer 3: Python unit tests** (`tests/test_sandbox_bridge.py`,
`tests/test_ir_api.py`)
- `test_preflight_rejects_unsupported_version` — code with
  `# ir_api_version: 99.0` → `FreeFormResult.fail("ir_api_version_unsupported")`
- `test_preflight_rejects_unsupported_lib` — code with
  `# libs: {numpy: 99.0}` → fail
- `test_preflight_rejects_missing_header` — code without header → fail
- `test_bridge_propagates_sandbox_failure` — mock Rust binary returns
  `{"ok": false, "reason": "timeout"}` → FreeFormResult.fail("timeout")
- `test_bridge_discards_ops_on_nonzero_exit` — mock returns ok=false; ops.jsonl
  exists; assert unlinked
- `test_bridge_validates_referential_integrity` — script references nonexistent
  asset → fail("invalid_op")
- `test_ir_api_12_methods` — one test per IR method; assert the produced
  Pydantic model has the right fields, parent_id stamped
- `test_ir_api_streams_to_jsonl` — pass a `_FlushingBuffer`; assert ops.jsonl
  written per call (file size grows as ops are added)
- `test_ir_api_rejects_at_build_time` — `ir.add_clip(invalid_uuid_format)` →
  Pydantic ValidationError
- `test_bridge_joblock_blocks_concurrent` — second run while first holds lock
  → fail("busy")

**Layer 4: End-to-end (the parent spec's "Done when")** (`tests/test_free_form_e2e.py`)
- `test_pyagent_run_python_50_lines` — see §6
- `test_free_form_then_render` — 50 clips via free-form → render → assert mp4
  exists and is > 0 bytes
- `test_free_form_failure_does_not_corrupt_graph` — script raises an exception;
  assert the original graph is unchanged (atomic commit)

### 7.2 What we explicitly do NOT test in v1

- Adversarial seccomp bypass (v1 trust model: not a security boundary)
- Landlock-specific edge cases (we use bwrap, not landlock directly)
- Multi-language support (Python only in v1)
- Sandbox escape attempts
- Performance / load testing

### 7.3 Positive safety-property tests

We prove the sandbox rejects the actions it's supposed to reject:
- Network: `socket.socket()` → blocked
- Source write: `open('/mnt/src/clip.mp4', 'w')` → blocked
- Memory cap: `bytearray(600 MB)` → killed
- CPU cap: `while True: pass` → killed
- Timeout: `time.sleep(60)` with --timeout 5 → killed

These are **positive** tests of the safety properties, run in CI, skipped if
`bwrap` is missing.

### 7.4 Skip conditions

All sandbox tests are skipped if `bwrap` is not on PATH. Rust unit tests that
don't require bwrap (e.g. seccomp_policy tests) run unconditionally. The CI
environment has `bubblewrap` installed; developer machines may or may not.

---

## 8. Configuration and deployment

### 8.1 Build

```bash
# Build the Rust binary (one-time, or when sandbox/ changes)
cd open_edit/sandbox
cargo build --release
# Binary at: target/release/open-edit-sandbox
# Add to PATH or install to ~/.local/bin
```

### 8.2 Runtime requirements

- Linux 4.x+ with user namespace support (5.x+ recommended)
- `bubblewrap` (bwrap) installed (`apt install bubblewrap` / `pacman -S bubblewrap`)
- The system Python matches `>=3.11` (already required by `pyproject.toml`)
- `open-edit-sandbox` binary on `$PATH`

### 8.3 Failure modes

| Failure | Behavior |
|---------|----------|
| `open-edit-sandbox` not on PATH | `run_free_form` returns `FreeFormResult.fail("sandbox_binary_missing")`. CLI/agent surfaces error to user. |
| `bwrap` not on PATH | Rust binary exits with reason=`bwrap_unavailable`; surfaces to user. |
| User-namespace disabled in kernel | Rust binary exits with reason=`userns_unavailable`; surfaces to user. |
| Seccomp not available (very old kernels) | Rust binary exits with reason=`setup_error`; surfaces to user. |

No silent fallbacks. If the sandbox can't be set up, the free-form run fails
loud and the agent/user knows to fix the environment.

---

## 9. Acceptance criteria (this spec is "done when")

1. `cd open_edit/sandbox && cargo test` passes (Layer 1 + Layer 2 tests).
2. `cd open_edit && pytest tests/test_ir_api.py tests/test_sandbox_bridge.py tests/test_free_form_e2e.py` passes (Layer 3 + Layer 4 tests), **skipped on environments without bwrap**.
3. The 50-line script in `test_pyagent_run_python_50_lines` produces 50 child ops in the edit graph, each with the correct `parent_id` and Pydantic-valid.
4. A free-form script that raises an exception does NOT corrupt the edit graph.
5. A free-form script that references a nonexistent asset_hash is rejected with a clear `invalid_op` error.
6. The atomic commit gate: non-zero exit, timeout, or invalid op → `ops.jsonl` is unlinked, no partial writes reach the edit graph.
7. The preflight header is required; a script without `# ir_api_version: X.Y; libs: {}` is rejected before the sandbox spawns.
8. The `_apply_free_form_code` branch in `apply.py` calls `sandbox_bridge` and appends child ops to the edit graph with the correct `parent_id`.
9. The `Project.workdir` retroactive change: existing Phase 0+1 fixtures still pass after adding `workdir=tmp_path` to their constructors.

**No `open_edit/sandbox/observations/strace_*.txt` is consumed by the v1
binary.** The Phase 0 strace fixtures are kept as documentation of what
syscalls melt/ffmpeg/ffprobe make, and will be the starting point for the
v1.1 allowlist work.

---

## 10. v1.1 hardening (deferred)

- **Tightened seccomp allowlist** derived from the Phase 0 strace fixtures +
  new strace against a typical free-form Python run.
- **Landlock directly** (drop bwrap; call `landlock::Ruleset` from the
  `landlock` crate).
- **`--with-hwaccel` flag** for `/dev/dri/*` and `/dev/shm` (VAAPI/DRM).
- **Librarian tool** to populate `allowed_libs.txt` from `site-packages`.
- **Per-project allowlist** (different projects may have different lib sets).
- **Adversarial testing** (sandbox escape attempts as a CI step).
- **Resource accounting** (track CPU/memory used per run; report to the user).
