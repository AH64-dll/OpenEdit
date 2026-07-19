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

**Known v1 trust-model boundaries (explicit, not implicit):**

1. **Network:** blocked by the seccomp denylist (`socket`, `connect`, etc.).
2. **Source media write:** blocked by `--ro-bind` on `<workdir>/assets/`.
3. **Resource limits:** enforced by `RLIMIT_AS` (memory), `RLIMIT_CPU` (cpu),
   wall-clock timeout via Rust fork+watcher.
4. **execve not blocked (M5):** a script can write a binary to `/tmp` (writable
   tmpfs) and exec it. The exec'd binary inherits the seccomp filter (no
   network) but has full filesystem and CPU access. Acceptable for v1; v1.1
   will add `SCMP_ACT_KILL_PROCESS` on `execve`/`execveat`/`memfd_create`.
5. **CAP_SYS_ADMIN in new userns (H11):** `--unshare-user` gives the child
   `CAP_SYS_ADMIN` in the new namespace, allowing `mount(2)` of certain
   filesystem types. Defense-in-depth cap drop is v1.1.
6. **`--unshare-ipc` (M6):** `multiprocessing.shared_memory` and SysV IPC
   don't work inside the sandbox. v1 demos don't use multiprocessing; v1.1
   may bind `/dev/shm` if needed.
7. **`HOME=/tmp` (M3):** libraries writing to `~/.cache/` (fontconfig,
   matplotlib, PIL) may fail or fall back. User scripts should not rely on
   `~/.config` or `~/.cache`.

**Out of v1 scope (explicitly):**
- `--with-hwaccel` flag (no demo uses VAAPI/DRM in v1)
- A `firejail` fallback (parent spec §6.8 mentions this; v1 uses bwrap, which is
  the path we picked — see §2.1)
- Hardened seccomp allowlist derived from strace fixtures (v1 ships a
  network-only denylist)
- Adversarial bypass testing (v1 tests positive safety properties only — see §7)
- Cap drop (defense in depth; deferred to v1.1)
- Landlock for finer-grained filesystem access (deferred to v1.1)

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
      listen, sendto, recvfrom, sendmsg, recvmsg) with `SCMP_ACT_ERRNO(EPERM)`
      action (see §3.4)
   b. set rlimits: RLIMIT_AS=2048M (see H1), RLIMIT_CPU=30s, RLIMIT_NOFILE=256,
      RLIMIT_NPROC=64
   c. exec bwrap with:
      --unshare-user --unshare-pid --unshare-ipc --unshare-net
      --die-with-parent
      --ro-bind /usr /usr
      --ro-bind /lib /lib
      --ro-bind-try /lib64 /lib64       # H2: multi-arch dynamic linker
      --ro-bind /etc /etc
      --symlink /usr/bin /bin           # H2: split-config distros
      --symlink /usr/sbin /sbin         # H2
      --proc /proc                     # H2: libraries reading /proc/cpuinfo
      --ro-bind <source1> /mnt/src1
      --ro-bind <source2> /mnt/src2
      --ro-bind <project-meta> /mnt/meta
      --bind <scratch> /scratch
      --tmpfs /tmp --tmpfs /home --tmpfs /var
      --dev /dev                       # C4: single --dev /dev
      --setenv HOME /tmp               # M3: avoid ~/.cache surprises
      --setenv XDG_CACHE_HOME /tmp/cache  # M3
      --new-session
      -- <python-bin> -c "
            import sys
            expected = tuple(int(x) for x in '<expected>'.split('.'))
            assert sys.version_info[:2] == expected, 'sandbox Python mismatch'
            g = {'__name__': '__main__'}
            exec(open('/scratch/_bootstrap.py').read(), g)
            exec(open('/scratch/code.py').read(), g)
        "
   d. on bwrap exit: capture exit code, stderr, wall-clock duration
   e. write JSON to stdout: {"ok": bool, "exit_code": int, "reason": str?,
      "duration_s": float, "stderr": str}

   f. Wall-clock timeout: Rust forks a watcher thread before exec'ing bwrap.
      The watcher sleeps `--timeout` seconds, then sends SIGTERM to the
      bwrap pid. After 2s grace, sends SIGKILL. If SIGKILL fires, the
      reported reason is `timeout` (not `parent_watchdog_timeout`); see C3
      and §3.1.

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
| `sandbox/src/jail.rs` | ~180 | install seccomp, set rlimits, fork+watcher timeout, exec bwrap (C3) |
| `sandbox/src/network_denylist.rs` | ~30 | the network-only denylist policy |
| `sandbox/tests/integration.rs` | ~150 | end-to-end tests, feature-gated (L7) |
| `sandbox/observations/*.txt` | existing | Phase 0 strace fixtures (informative) |

### 3.2 CLI (clap)

H4: `--code` flag was removed. The Rust binary reads `/scratch/code.py`
directly (sandbox_bridge writes it there). All paths inside the sandbox are
fixed by the bwrap mount convention.

```
open-edit-sandbox
  --scratch <PATH>            # rw directory for ops.jsonl + temps
  --source-ro <PATH>          # ro directory of source media (repeatable, 0+)
  --project-meta <PATH>       # ro file (edit_graph.db)
  --python-bin <PATH>         # default: sys.executable of parent (passed by sandbox_bridge)
  --expected-py-version <STR> # major.minor, e.g. "3.14"; child parses back to tuple
  --timeout <SEC>             # default: 30 (wall clock, enforced by Rust fork+watcher; C3)
  --cpu <SEC>                 # default: 30 (RLIMIT_CPU)
  --mem <MB>                  # default: 2048 (RLIMIT_AS; raised from 512 per H1)
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

**H3: explicit action.** All denials use `SCMP_ACT_ERRNO(EPERM)` (errno 1)
rather than the libseccomp default `SCMP_ACT_KILL_PROCESS` (which kills with
`SIGSYS` and no diagnostic). This lets the child see `PermissionError` from
`socket.socket()` etc., which the user can catch and reason about.

```rust
// sandbox/src/network_denylist.rs
use libseccomp::{ScmpAction, ScmpFilterContext, ScmpSyscall};

pub fn install(ctx: &mut ScmpFilterContext) -> anyhow::Result<()> {
    let action = ScmpAction::Errno(1);  // EPERM
    for name in ["socket", "connect", "bind", "accept", "listen",
                 "sendto", "recvfrom", "sendmsg", "recvmsg"] {
        let nr = ScmpSyscall::from_name(name)?;
        ctx.add_rule_exact(action, nr)?;
    }
    Ok(())
}
```

**M5: known gap, v1 trust model.** The denylist does NOT block `execve`,
`execveat`, or `memfd_create`. A sandboxed script can write a binary to
`/tmp` (writable tmpfs) and `exec` it. The exec'd binary inherits the seccomp
filter so it can't make network calls, but it has full filesystem and CPU
access. This is acceptable for v1's trust model ("prevent accidental
corruption and network calls, not malicious code") but will be tightened in
v1.1 with `SCMP_ACT_KILL_PROCESS` on `execve`/`execveat`/`memfd_create` once
the tighter allowlist work is done (see §10).

The v1 trust model is documented and explicit: this is "prevent accidental
network calls and runaway resources," not a malicious-code defense.

### 3.5 rlimits (set in the Rust binary before exec)

| rlimit | value | effect on hit |
|--------|-------|---------------|
| `RLIMIT_AS` | `--mem` MB (default **2048** per H1) | SIGSEGV; child exits 139; reason=`oom_killed` |
| `RLIMIT_CPU` | `--cpu` seconds | SIGXCPU; child exits 137; reason=`cpu_limit_killed` |
| `RLIMIT_NOFILE` | 256 | Python raises `OSError(EMFILE)`; child exits 1; reason=`nofile_limit` |
| `RLIMIT_NPROC` | 64 | Python raises `OSError(EAGAIN)`; child exits 1; reason=`nproc_limit` |

**H1 rationale:** 512 MB is too small for Python+numpy+opencv import alone
(~600 MB of virtual address space). Default raised to 2048 MB. Scripts that
need more can pass `--mem 4096`. The hard cap in `sandbox_bridge` (H9) is
4096 MB.

**H1 future direction (v1.1):** `RLIMIT_AS` is widely considered broken for
capping memory because it limits virtual address space, not resident memory.
A bare `python3 -c 'pass'` allocates 80–150 MB of VM. v1.1 will use cgroup
v2 `memory.max` via systemd-run (`systemd-run --user --scope -p MemoryMax=512M
open-edit-sandbox ...`) which caps RESIDENT memory (the right semantic). For
v1, we accept the 2 GB virtual address space default.

### 3.6 Namespaces: fail loud, no `-try`

The bwrap invocation uses:

```
--unshare-user --unshare-pid --unshare-ipc --unshare-net
```

(M7: `--unshare-uts` is dropped — hiding the hostname has no benefit and
clutters the command line.)

If `--unshare-user` or `--unshare-pid` fails, bwrap exits non-trivially; the
Rust binary maps this to `userns_unavailable` or `pidns_unavailable` and the
parent gets a `FreeFormResult.fail(...)`. **No silent degradation.**

**H11: CAP_SYS_ADMIN in the new user namespace.** `--unshare-user` creates a
new user namespace where the child has `CAP_SYS_ADMIN` and can `mount(2)`
certain filesystem types (`tmpfs`, `procfs`, `sysfs`, `devtmpfs`). This is a
known bwrap footgun. The v1 trust model acknowledges this and accepts the
risk: the sandbox is for accidental-corruption prevention, not malicious-code
defense. v1.1 will drop capabilities post-fork pre-exec as defense in
depth (`caps::clear(None, CapSet::Effective)?;` etc.) — out of v1 scope.

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

The bootstrap is generated by `sandbox_bridge._render_bootstrap` from the actual
IR source via `inspect.getsource()`. It is **self-contained**: it inlines the
`IR` class, the 12 Pydantic op models, and the `new_id` helper, so the bootstrap
does NOT need to `import open_edit` inside the sandbox. This eliminates the
install-location discovery problem (venv vs dist-packages vs system) and the
transitive-deps problem (pydantic, lxml).

```python
# <scratch>/_bootstrap.py — generated by sandbox_bridge via inspect.getsource().
# The actual file is ~500 lines: ~250 for IR + ~250 for the 12 op models +
# ~50 for new_id and types.

# (Below is the structure of the generated file.)

# === INLINED: open_edit/ir/api.py:IR class ===
# === INLINED: open_edit/ir/types.py:12 op models ===
# === INLINED: open_edit/ir/types.py:new_id helper ===

import json

# === INJECTED CONSTANTS ===
PROJECT_ID = "<project_id>"        # from sandbox_bridge
PARENT_OP_ID = "<parent_op_id>"    # from sandbox_bridge
OPS_FILE = "/scratch/ops.jsonl"    # ALWAYS this in-sandbox path; the scratch
                                    # dir is mounted at /scratch inside bwrap

# === INJECTED: _FlushingBuffer ===
# Write FIRST, then append — if the file write fails, raise immediately so
# the whole run aborts instead of silently losing the op (see H10).
class _FlushingBuffer(list):
    def append(self, op):
        with open(OPS_FILE, "a") as f:
            f.write(op.model_dump_json() + "\n")
        super().append(op)

_ops = _FlushingBuffer()
ir = IR(_ops, project_id=PROJECT_ID, parent_op_id=PARENT_OP_ID)
```

**Why this works:**
- The bootstrap is self-contained: it inlines the IR API and op models it
  needs, so no `import open_edit` happens inside the sandbox.
- The in-sandbox path is fixed at `/scratch/ops.jsonl` because the bwrap
  invocation always mounts scratch at `/scratch` (see §2.2 step 6c).
- Every `ir.<method>(...)` call appends to the in-memory list **and** writes a
  JSONL line to `ops.jsonl` immediately and durably. No in-memory state that
  could be lost on crash.
- The bwrap exec is `<python-bin> -c "exec(_bootstrap); exec(code.py)"` so
  both run in the same process and share `ir` in globals.

**Fallback (Option B):** if `inspect.getsource()` is unavailable (e.g. the
bootstrap is generated from a frozen/bundled install), fall back to ro-binding
the install location. `sandbox_bridge` discovers the install location via
`open_edit.__path__[0]`, passes it to the Rust binary as `--open-edit-root`,
and the bwrap invocation does `--ro-bind <root> /open_edit --setenv PYTHONPATH
/open_edit`. This works for venv, system pip, and most conda installs; it
assumes pydantic and other transitive deps live in the same site-packages.

### 4.3 `open_edit/agent/sandbox_bridge.py`

```python
import inspect
import json
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from open_edit.agent.exceptions import FreeFormResult, SandboxError
from open_edit.agent.libs import parse_header, version_supported, lib_version_supported
from open_edit.ir.api import IR
from open_edit.ir.apply import apply_operation, derive_timeline
from open_edit.ir.types import (
    OperationUnion, Project, Asset,
    AddClipOp, TrimClipOp, MoveClipOp, RemoveClipOp,
    AddEffectOp, SetKeyframeOp, SetAudioGainOp,
)
from open_edit.pydantic_compat import TypeAdapter
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.job_lock import JobLock, JobLockBusy

# Pin Python at module import time.
PINNED_PYTHON_BIN = sys.executable
# C5: major.minor only ("3.14"), not full "3.14.5". The child parses it
# back to a tuple for comparison.
EXPECTED_PY_VERSION = '.'.join(platform.python_version().split('.')[:2])
# H9: hard caps so FreeFormCodeOp.timeout_sec can't hold the JobLock forever.
MAX_FREEFORM_TIMEOUT_SEC = 300
MAX_FREEFORM_MEM_MB = 4096


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
    """Run free-form Python. ALWAYS returns FreeFormResult, never raises.

    C7: the outer try/except is the contract enforcer. Any unexpected
    exception is caught and mapped to FreeFormResult.fail('internal_error').
    """
    # H9: enforce hard caps
    timeout = min(int(timeout), MAX_FREEFORM_TIMEOUT_SEC)
    mem_mb = min(int(mem_mb), MAX_FREEFORM_MEM_MB)

    try:
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
                    code, workdir, project_id, parent_op_id,
                    timeout, mem_mb, cpu_sec,
                )
        except JobLockBusy:
            return FreeFormResult.fail("busy", "another free-form run is in progress")
        except subprocess.TimeoutExpired:
            return FreeFormResult.fail("parent_watchdog_timeout",
                                       "sandbox did not exit within timeout+10s")
    except Exception as e:
        # C7: never-raises contract safety net.
        return FreeFormResult.fail("internal_error", repr(e))


def _resolve_sandbox_bin() -> str | None:
    """H5: resolve at call time, not at module import time."""
    return shutil.which("open-edit-sandbox")


def _run_sandboxed(code, workdir, project_id, parent_op_id, timeout, mem_mb, cpu_sec):
    sandbox_bin = _resolve_sandbox_bin()
    if sandbox_bin is None:
        return FreeFormResult.fail(
            "sandbox_binary_missing",
            "'open-edit-sandbox' not found on PATH; build with "
            "'cd open_edit/sandbox && cargo build --release' and install to $PATH",
        )

    run_id = _new_id()
    scratch = workdir / '.sandbox' / f'run_{run_id}'
    scratch.mkdir(parents=True, exist_ok=True)
    code_path = scratch / 'code.py'
    ops_path = scratch / 'ops.jsonl'
    bootstrap_path = scratch / '_bootstrap.py'

    code_path.write_text(code)
    bootstrap_path.write_text(_render_bootstrap(project_id, parent_op_id))

    assets_dir = workdir / 'assets'
    source_dirs = sorted(p for p in assets_dir.iterdir() if p.is_dir()) if assets_dir.exists() else []
    meta_file = workdir / 'edit_graph.db'

    # H4: --code flag removed. The Rust binary reads /scratch/code.py directly.
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

    # 5. Read + validate ops.jsonl (Pydantic + referential, incrementally)
    try:
        ops, _ = _validate_ops_incrementally(ops_path, workdir)
    except _ValidationError as e:
        ops_path.unlink(missing_ok=True)
        return FreeFormResult.fail("invalid_op", str(e))

    return FreeFormResult.ok(ops=ops, duration_s=rust.get('duration_s', 0.0))


class _ValidationError(Exception):
    pass


def _validate_ops_incrementally(ops_path: Path, workdir: Path) -> tuple[list, object]:
    """C6: validate each op against a working-copy timeline, then apply the op
    to the working copy. This way, a script that does `cid = ir.add_clip(...);
    ir.trim_clip(cid, ...)` validates successfully.

    Returns (ops, final_timeline). Raises _ValidationError on any failure.
    """
    # C7: defensively catch all exceptions from project load.
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
            op_dict = json.loads(line)
            op = TypeAdapter(OperationUnion).validate_python(op_dict)
            _validate_references(op, timeline, project.assets)
            timeline = apply_operation(timeline, op)
            ops.append(op)
        except (json.JSONDecodeError, ValidationError, ReferenceError) as e:
            raise _ValidationError(f"line {line_num}: {e}") from e

    return ops, timeline


def _load_project_for_validation(workdir: Path) -> Project:
    """Load the project from workdir/edit_graph.db for referential checks.

    L10: load the real project_id from db metadata (not synthesized default).
    """
    db_path = workdir / 'edit_graph.db'
    if not db_path.exists():
        raise _ValidationError(f"project db not found: {db_path}")
    store = EditGraphStore(db_path)
    assets = _load_assets_via_store(store)
    return Project(
        project_id=store.project_id,  # L10: real, not synthesized
        name=workdir.name,
        workdir=workdir,
        assets=assets,
        edit_graph=store.load_all(),
    )


def _load_assets_via_store(store: EditGraphStore) -> dict[str, Asset]:
    """M2: iterate edit graph to find referenced asset hashes, then load
    metadata from AssetStore. v1 O(n) in edit graph size; v1.1 will use a
    SQL-backed index for large projects."""
    asset_hashes: set[str] = set()
    for op in store.load_all():
        if isinstance(op, AddClipOp):
            asset_hashes.add(op.asset_hash)
    asset_store = AssetStore()
    assets = {}
    for h in asset_hashes:
        asset = asset_store.get(h)
        if asset is not None:
            assets[h] = asset
    return assets


def _validate_references(op: OperationUnion, timeline, assets) -> None:
    """Raise ReferenceError if op references non-existent entity.

    C6: receives the working-copy timeline, not the project.
    """
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


def _render_bootstrap(project_id: str, parent_op_id: str) -> str:
    """Generate _bootstrap.py with the IR class and op models inlined.

    C2 preferred fix (Option A): vendor IR into the bootstrap. The bootstrap
    is self-contained — no `import open_edit` happens inside the sandbox.
    The op models and the IR class are pulled via inspect.getsource().

    C1: OPS_FILE is hardcoded to /scratch/ops.jsonl because the bwrap
    invocation always mounts scratch at /scratch.
    """
    ir_source = inspect.getsource(IR)
    op_types = [
        "AddClipOp", "RemoveClipOp", "MoveClipOp", "TrimClipOp",
        "AddTransitionOp", "AddEffectOp", "SetKeyframeOp",
        "SetAudioGainOp", "NormalizeAudioOp",
        "GroupEditsOp", "RawMltXmlOp", "FreeFormCodeOp",
    ]
    op_sources = []
    from open_edit.ir import types as _types
    for name in op_types:
        cls = getattr(_types, name)
        op_sources.append(inspect.getsource(cls))
    new_id_source = inspect.getsource(_types.new_id) if hasattr(_types, 'new_id') else ""
    return textwrap.dedent(f'''
        # === _bootstrap.py (auto-generated by sandbox_bridge) ===
        # Self-contained: IR + op models inlined. No import open_edit.
        import json
        from typing import Optional, Union, Literal
        from pydantic import BaseModel, Field
        from datetime import datetime, timezone

        # --- INLINED: open_edit/ir/types.py:new_id ---
        {new_id_source}

        # --- INLINED: op models (12 classes) ---
        {chr(10).join(op_sources)}

        # --- INLINED: open_edit/ir/api.py:IR ---
        {ir_source}

        # === INJECTED CONSTANTS ===
        PROJECT_ID = {project_id!r}
        PARENT_OP_ID = {parent_op_id!r}
        OPS_FILE = "/scratch/ops.jsonl"

        # Write FIRST, then append (H10): if the file write fails, raise so
        # the whole run aborts; no silent loss.
        class _FlushingBuffer(list):
            def append(self, op):
                with open(OPS_FILE, "a") as f:
                    f.write(op.model_dump_json() + "\\n")
                super().append(op)

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

**H6 fix:** `SandboxError` import added. **H8 fix:** header requires quoted
keys and values (`{"numpy": "1.26.4"}`) for `ast.literal_eval` to work.

```python
import ast
import re
import tomllib
from pathlib import Path

# H6: import SandboxError
from open_edit.agent.exceptions import SandboxError

_HEADER_RE = re.compile(
    r'^\s*#\s*ir_api_version:\s*(\S+)\s*;\s*libs:\s*(\{.*?\})\s*$',
    re.MULTILINE,
)

ALLOWED_LIBS_PATH = Path(__file__).parent / "allowed_libs.toml"


def parse_header(code: str) -> tuple[str, dict[str, str]]:
    """Parse `# ir_api_version: X.Y; libs: {"name": "ver", ...}` from code.

    H8: keys and values MUST be quoted strings (Python literal syntax).
    Returns (version, libs_dict). Raises SandboxError on missing/malformed
    header or invalid libs dict.
    """
    m = _HEADER_RE.search(code)
    if not m:
        raise SandboxError(
            "missing or malformed ir_api_version header "
            "(expected: # ir_api_version: X.Y; libs: {\"name\": \"ver\"})"
        )
    version = m.group(1)
    try:
        libs = ast.literal_eval(m.group(2))
    except (ValueError, SyntaxError) as e:
        raise SandboxError(f"libs dict is not valid Python: {e}") from e
    if not isinstance(libs, dict):
        raise SandboxError(f"libs must be a dict, got {type(libs).__name__}")
    for k, v in libs.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise SandboxError(f"libs keys/values must be strings: {libs!r}")
    return version, libs


def version_supported(declared: str) -> bool:
    manifest = _load_manifest()
    return declared in manifest.get("ir_api_versions", [])


def lib_version_supported(name: str, ver: str) -> bool:
    manifest = _load_manifest()
    return ver in manifest.get("libs", {}).get(name, [])


def _load_manifest() -> dict:
    """L8: load from TOML (tomllib stdlib in 3.11+)."""
    with open(ALLOWED_LIBS_PATH, "rb") as f:
        return tomllib.load(f)
```

### 4.6 `open_edit/agent/allowed_libs.toml` — the manifest

L8: TOML format (Python 3.11+ has `tomllib` in stdlib). A future "librarian"
tool (probably a v1.1 sub-phase) will populate it from the actual
`site-packages`.

```toml
# open_edit/agent/allowed_libs.toml
# Each entry under [ir_api_versions] is a supported ir_api_version string.
# Each [libs.<name>] section lists the supported versions for that library.

ir_api_versions = ["0.1"]

[libs.numpy]
versions = ["1.26.4", "2.1.3"]

[libs.opencv-python]
versions = ["4.8.1.78", "4.10.0.84"]

[libs.pillow]
versions = ["10.4.0", "11.0.0"]
```

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
    workdir: Optional[Path] = None  # NEW in Phase 3; M8: Optional for back-compat
    created_at: str = Field(default_factory=now_iso8601)
    assets: dict[str, Asset] = Field(default_factory=dict)
    edit_graph: list[OperationUnion] = Field(default_factory=list)
```

**M8 rationale:** making `workdir` required would break deserialization of
existing Phase 0+1 `edit_graph.json` files on disk that don't have the field.
Making it `Optional[Path] = None` preserves back-compat. When loading from
`edit_graph.db`, `EditGraphStore.load_all()` (or its caller) synthesizes
`workdir` from the db path's parent directory.

**L6: which fixtures need updating.** The fixtures in
`tests/testdata/*/edit_graph.json` don't need updating (they're JSON test
data, not Python constructors). The Python tests that construct `Project`
directly and need `workdir` added are:
- `tests/test_e2e.py` (1 site)
- `tests/test_something.py` (1-2 sites)
- The new `tmp_project_with_assets` fixture in `tests/test_free_form_e2e.py`

`grep -n "Project(" open_edit/tests/ -r` enumerates them at implementation
time.

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
| `sandbox/Cargo.toml` | 25 | package metadata, deps: clap, nix, libseccomp-rs, anyhow |
| `sandbox/src/main.rs` | 80 | CLI + orchestration |
| `sandbox/src/jail.rs` | 180 | seccomp + rlimits + fork+watcher (C3) + bwrap |
| `sandbox/src/network_denylist.rs` | 30 | the denylist policy, `SCMP_ACT_ERRNO(EPERM)` (H3) |
| `sandbox/tests/integration.rs` | 150 | end-to-end tests, feature-gated (L7) |
| `open_edit/agent/__init__.py` | 3 | package marker |
| `open_edit/agent/sandbox_bridge.py` | 220 | the wrapper; uses `inspect.getsource()` for Option A |
| `open_edit/agent/exceptions.py` | 25 | FreeFormResult, SandboxError, _ValidationError |
| `open_edit/agent/libs.py` | 60 | header parsing, TOML manifest lookup (H6, H8, L8) |
| `open_edit/agent/allowed_libs.toml` | 20 | ir_api_version + libs manifest (TOML) |
| `tests/test_sandbox_bridge.py` | 100 | unit tests (mock Rust binary) |
| `tests/test_ir_api.py` | 100 | unit tests of IR methods |
| `tests/test_free_form_e2e.py` | 250 | 5 e2e tests: 50-line, chained, render, failure, ro (L1-L4) |
| `open_edit/ir/api.py` (REWRITE) | 250 | 12 methods (replaces 25-line stub) |

**L7: cargo feature gate.** Integration tests in `sandbox/tests/integration.rs`
require bwrap. Gate them with a `#[cfg(feature = "integration")]` attribute
so `cargo test` (without features) still works on dev machines without bwrap.
Run integration tests with `cargo test --features integration` in CI.

```toml
# sandbox/Cargo.toml
[features]
integration = []
```

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
import errno
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
    """A project with one asset pre-ingested, suitable for free-form runs.

    L9: create a real (small) video file at the stored_path so the
    asset is actually accessible inside the sandbox.
    """
    from open_edit.ir.types import Project, Asset
    # Create a real 1-byte placeholder file. Real video files are in
    # tests/testdata/raw_videos; this fixture just needs the path to exist
    # so AssetStore.get() returns a valid Asset.
    stored = tmp_path / "assets" / "ab" / "abc123" / "clip.mp4"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"\x00")
    asset = Asset(
        asset_hash="abc123",
        original_path=Path("/tmp/clip.mp4"),
        stored_path=str(stored),
        type="video",
        duration_sec=10.0,
        fps=30.0,
        width=1920,
        height=1080,
        codec="h264",
        has_audio=True,
    )
    return Project(
        name="test",
        workdir=tmp_path,
        assets={asset.asset_hash: asset},
    )


def test_pyagent_run_python_50_lines(tmp_project_with_assets):
    """The design's "Done when" criterion: 50-line script → 50 child ops."""
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


def test_chained_ops_succeed(tmp_project_with_assets):
    """L4: covers C6 — `ir.add_clip(...)` returns cid, `ir.trim_clip(cid, ...)` works."""
    code = textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        cid = ir.add_clip(
            asset_hash="abc123",
            track_id="video_main",
            position_sec=0.0,
        )
        ir.trim_clip(cid, in_point_sec=1.0, out_point_sec=2.0)
    ''')
    op = FreeFormCodeOp(edit_id="e1",
                        project_id=tmp_project_with_assets.project_id,
                        code=code)
    updated = apply_operation(tmp_project_with_assets, op)
    child_ops = [o for o in updated.edit_graph
                 if getattr(o, 'parent_id', None) == "e1"]
    assert len(child_ops) == 2
    assert isinstance(child_ops[0], AddClipOp)
    assert isinstance(child_ops[1], TrimClipOp)
    assert child_ops[1].clip_id == child_ops[0].clip_id  # chained


def test_free_form_then_render(tmp_project_with_assets, tmp_path):
    """L2: free-form script that adds 5 clips, then full render, asserts mp4 > 0 bytes."""
    code = textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        for i in range(5):
            ir.add_clip(
                asset_hash="abc123",
                track_id="video_main",
                position_sec=i * 2.0,
            )
    ''')
    op = FreeFormCodeOp(edit_id="e1",
                        project_id=tmp_project_with_assets.project_id,
                        code=code)
    updated = apply_operation(tmp_project_with_assets, op)

    timeline = derive_timeline(updated)
    xml = emit_timeline(timeline)
    out_path = tmp_path / "out.mp4"
    result = melt_render(xml, out_path)  # Phase 2 helper
    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_free_form_failure_does_not_corrupt_graph(tmp_project_with_assets):
    """L3: a free-form script that raises an exception does NOT corrupt the edit graph."""
    pre_ops = list(tmp_project_with_assets.edit_graph)
    code = textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        ir.add_clip(asset_hash="abc123", track_id="video_main", position_sec=0.0)
        raise RuntimeError("boom")
    ''')
    op = FreeFormCodeOp(edit_id="e1",
                        project_id=tmp_project_with_assets.project_id,
                        code=code)
    with pytest.raises(ApplyError) as exc_info:
        apply_operation(tmp_project_with_assets, op)
    assert "boom" in str(exc_info.value) or "nonzero_exit" in str(exc_info.value)
    # edit graph is unchanged
    assert list(tmp_project_with_assets.edit_graph) == pre_ops
    # no ops.jsonl files in .sandbox area
    sandbox_dir = tmp_project_with_assets.workdir / ".sandbox"
    if sandbox_dir.exists():
        for run_dir in sandbox_dir.iterdir():
            assert not (run_dir / "ops.jsonl").exists()


def test_source_ro_blocks_writes(tmp_project_with_assets):
    """L1: ro-bound source raises OSError (EROFS), not PermissionError (EACCES).

    The kernel returns EROFS for a ro-bind write attempt; Python wraps
    it as OSError(errno.EROFS). PermissionError is for EACCES specifically.
    """
    code = textwrap.dedent('''
        # ir_api_version: 0.1; libs: {}
        # find a source dir and try to write to it
        import os
        try:
            with open("/mnt/src0/clip.mp4", "w") as f:
                f.write("x")
        except OSError as e:
            ir.add_clip(
                asset_hash="abc123",
                track_id="video_main",
                position_sec=0.0,
                label=f"errno={e.errno}",
            )
    ''')
    op = FreeFormCodeOp(edit_id="e1",
                        project_id=tmp_project_with_assets.project_id,
                        code=code)
    updated = apply_operation(tmp_project_with_assets, op)
    child_ops = [o for o in updated.edit_graph
                 if getattr(o, 'parent_id', None) == "e1"]
    assert len(child_ops) == 1
    # EROFS=30 on Linux; the label captures it
    assert "30" in child_ops[0].label  # EROFS
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

### 8.4 CI configuration (L5)

```yaml
# .github/workflows/test.yml — Phase 3 job
jobs:
  test-sandbox:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install system deps
        run: |
          sudo apt-get update
          sudo apt-get install -y bubblewrap libseccomp-dev

      - name: Set up Rust
        uses: dtolnay/rust-toolchain@stable

      - name: Build sandbox
        run: cd open_edit/sandbox && cargo build --release

      - name: Install sandbox binary
        run: |
          sudo cp open_edit/sandbox/target/release/open-edit-sandbox /usr/local/bin/

      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"

      - name: Install Python deps
        run: pip install -e open_edit/[test]

      - name: Test (with integration)
        run: |
          cd open_edit/sandbox && cargo test --features integration
          cd ../../ && pytest open_edit/tests/ -v
```

---

## 9. Acceptance criteria (this spec is "done when")

1. `cd open_edit/sandbox && cargo test --features integration` passes (Layer 1 + Layer 2 tests, including all 6 Rust integration tests in §7.1).
2. `cd open_edit && pytest tests/test_ir_api.py tests/test_sandbox_bridge.py tests/test_free_form_e2e.py` passes (Layer 3 + Layer 4 tests, **skipped on environments without bwrap**). All 5 free-form e2e tests in §6 pass: `test_pyagent_run_python_50_lines`, `test_chained_ops_succeed`, `test_free_form_then_render`, `test_free_form_failure_does_not_corrupt_graph`, `test_source_ro_blocks_writes`.
3. The 50-line script in `test_pyagent_run_python_50_lines` produces 50 child ops in the edit graph, each with the correct `parent_id` and Pydantic-valid.
4. The chained-ops test (`test_chained_ops_succeed`) passes: `ir.add_clip(...)` returns `cid`, `ir.trim_clip(cid, ...)` is accepted by the validator.
5. A free-form script that raises an exception does NOT corrupt the edit graph; the pre-run state is byte-identical after the failed run.
6. A free-form script that references a nonexistent asset_hash is rejected with a clear `invalid_op` error pointing at the offending line number.
7. The atomic commit gate: non-zero exit, timeout, or invalid op → `ops.jsonl` is unlinked, no partial writes reach the edit graph.
8. The preflight header is required; a script without `# ir_api_version: X.Y; libs: {}` is rejected before the sandbox spawns. A script with unquoted libs dict (`{numpy: 1.26.4}`) is rejected with `libs dict is not valid Python` (H8).
9. The `_apply_free_form_code` branch in `apply.py` calls `sandbox_bridge` and appends child ops to the edit graph with the correct `parent_id` (stamped at IR method build time, not mutated in apply.py).
10. The `Project.workdir` retroactive change: `workdir: Optional[Path] = None` (M8), back-compat preserved.
11. **H9:** `run_free_form` enforces hard caps of `MAX_FREEFORM_TIMEOUT_SEC=300` and `MAX_FREEFORM_MEM_MB=4096` regardless of input values.
12. **C1/C2:** the bootstrap is self-contained (Option A: `inspect.getsource()`-inlined IR and op models) and writes to the in-sandbox path `/scratch/ops.jsonl` (not the host path). `import open_edit` is NOT called inside the sandbox.
13. **C3:** the Rust binary enforces wall-clock timeout via fork+watcher; if the timeout fires, the reported reason is `timeout`, not `parent_watchdog_timeout`.
14. **C4:** the bwrap invocation uses a single `--dev /dev`, not two `--dev` flags with file paths.
15. **C5:** the Python version check parses the string back to a tuple; comparing tuple to string is never done.
16. **C6/C7:** `_validate_ops_incrementally` validates each op against a working-copy timeline and applies the op to the working copy. `run_free_form` never raises (top-level `try/except Exception`).
17. **H1:** `--mem` default is 2048 MB; tests for numpy/opencv import work without OOM.
18. **H2:** the bwrap invocation includes `/lib64`, `/proc`, `/bin`, `/sbin` (via symlinks).
19. **H3:** the seccomp denylist uses `SCMP_ACT_ERRNO(EPERM)`; the child sees `PermissionError` not `SIGSYS`.
20. **H4:** `--code` CLI flag is removed; the Rust binary reads `/scratch/code.py` directly.
21. **H5:** `SANDBOX_BIN` is resolved at call time, not at module import.
22. **H6:** `libs.py` imports `SandboxError`.
23. **H7:** all Phase 0+1 modules the bridge depends on (`pydantic_compat`, `EditGraphStore`, `JobLock`, `AssetStore`, all 12 op types, `Project`, `Asset`, `apply_operation`, `derive_timeline`) are verified to exist before the bridge is implemented. **Verified 2026-07-21: all imports work.**
24. **H10:** `_FlushingBuffer.append` writes to ops.jsonl FIRST, then appends to the in-memory list. A failed write raises an exception, aborting the run. No silent loss.
25. **H11:** the v1 trust model section (§1) explicitly acknowledges `CAP_SYS_ADMIN` in the new userns. Defense-in-depth cap drop is deferred to v1.1.

**No `open_edit/sandbox/observations/strace_*.txt` is consumed by the v1
binary.** The Phase 0 strace fixtures are kept as documentation of what
syscalls melt/ffmpeg/ffprobe make, and will be the starting point for the
v1.1 allowlist work.

---

## 10. v1.1 hardening (deferred)

The following are explicitly out of v1 scope. They are listed here so v1.1
work has a clear backlog.

- **Tightened seccomp allowlist** derived from strace of a typical free-form
  Python run (the Phase 0 strace fixtures cover melt/ffmpeg/ffprobe only).
  v1 ships a network-only denylist.
- **Seccomp on `execve`/`execveat`/`memfd_create`** (M5) with
  `SCMP_ACT_KILL_PROCESS`. v1 does not block these.
- **Cap drop post-fork pre-exec** (H11) via the `caps` crate. v1 accepts
  the `CAP_SYS_ADMIN`-in-new-userns footgun as part of the trust model.
- **Landlock for finer-grained filesystem access** (M4). v1.1 will add
  landlock via the `landlock` crate for path-level access control beyond
  the bwrap `ro-bind`/`--bind` model. **Landlock is filesystem-only**; it
  does NOT replace `--unshare-net` for network isolation. The v1.1
  architecture keeps bwrap (or a manual `netns(2)` syscall) for network
  isolation and adds landlock for filesystem granularity.
- **`--with-hwaccel` flag** for `/dev/dri/*` and `/dev/shm` (VAAPI/DRM).
  No v1 demo uses this.
- **cgroup v2 `memory.max`** for RESIDENT-memory capping (H1 v1.1
  direction). v1 uses `RLIMIT_AS` (virtual address space, default 2 GB).
- **Librarian tool** to populate `allowed_libs.toml` from `site-packages`.
  v1 has a hand-written manifest.
- **Per-project allowlist** (different projects may have different lib sets).
- **Adversarial testing** (sandbox escape attempts as a CI step). v1 tests
  positive safety properties only.
- **Resource accounting** (track CPU/memory used per run; report to user).
- **`/dev/shm` bind** (M6) to support `multiprocessing.shared_memory`. v1
  demos don't use multiprocessing.
- **Drop `_FlushingBuffer`'s in-memory list** once the JSONL write is
  confirmed durable; the in-memory list is currently a debug aid.
- **Incremental timeline index** (M1) for O(1) reference validation in
  projects with >5k ops.
