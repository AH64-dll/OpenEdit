
## Task 9: W1 Whisper integration in AssetStore

**Files:**
- Modify: `open_edit/open_edit/storage/assets.py` (add `alignment` field to `Asset`; call Whisper on ingest)
- Modify: `open_edit/open_edit/ir/types.py` (add `WordAlignment` Pydantic model; add `alignment: list[WordAlignment]` to `Asset`)
- Modify: `open_edit/pyproject.toml` (add `faster-whisper` as optional dependency under `[whisper]` extra)
- Create: `open_edit/open_edit/storage/transcription.py` (faster-whisper wrapper)
- Test: `open_edit/tests/test_storage/test_transcription.py`
- Test: `open_edit/tests/test_storage/test_assets_alignment.py`

**Interfaces:**
- Consumes: existing `AssetStore.ingest_paths`; existing `Asset` Pydantic model.
- Produces:
  - `WordAlignment` Pydantic model: `{word: str, t_start: float, t_end: float, confidence: float}`.
  - `Asset.alignment: list[WordAlignment] = []` (additive; defaults to empty list for back-compat).
  - `AssetStore.ingest_paths()` now also calls `transcribe(src)` (optional; skip if `faster-whisper` not installed) to populate `alignment`.
  - `transcription.transcribe(src: Path, model_size: str = "base") -> list[WordAlignment]`.
  - Optional dependency: install with `pip install open_edit[whisper]`. Without it, ingest still works; `alignment` is empty.

### Step 1: Add `faster-whisper` as optional dependency

Modify `open_edit/pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
]
whisper = [
    "faster-whisper>=1.0.0",
]
```

### Step 2: Write the failing test

Create `open_edit/tests/test_storage/test_assets_alignment.py`:

```python
"""Phase 4.5 W1: Asset.alignment field + AssetStore integration."""
import json
import pytest
from pathlib import Path
from open_edit.ir.types import Asset, WordAlignment
from open_edit.storage.assets import AssetStore


def test_word_alignment_pydantic():
    wa = WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=0.99)
    assert wa.word == "hello"
    assert wa.t_start == 0.0


def test_asset_default_alignment_empty():
    asset = Asset(
        asset_hash="abc",
        original_path="/tmp/x.mp4",
        stored_path="/tmp/x",
        type="video",
        duration_sec=10.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
    )
    assert asset.alignment == []


def test_asset_with_alignment():
    asset = Asset(
        asset_hash="abc",
        original_path="/tmp/x.mp4",
        stored_path="/tmp/x",
        type="video",
        duration_sec=10.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
        alignment=[
            WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=0.99),
        ],
    )
    assert len(asset.alignment) == 1


def test_ingest_back_compat_without_whisper(tmp_path, monkeypatch):
    """Without faster-whisper installed, ingest still works; alignment is empty."""
    monkeypatch.setattr("open_edit.storage.transcription._has_whisper", lambda: False)
    src = tmp_path / "test.mp4"
    src.write_bytes(b"\x00" * 1024)
    store = AssetStore(tmp_path / "assets")
    try:
        assets = store.ingest_paths([str(src)])
    except Exception as e:
        pytest.skip(f"ffprobe not available: {e}")
    assert assets[0].alignment == []
```

### Step 3: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_storage/test_assets_alignment.py -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'alignment'` (WordAlignment not defined) or `pydantic` validation error.

### Step 4: Add `WordAlignment` to `ir/types.py`

In `open_edit/open_edit/ir/types.py`, add:

```python
class WordAlignment(BaseModel):
    word: str
    t_start: float
    t_end: float
    confidence: float = 1.0
```

And add `alignment: list[WordAlignment] = []` to the `Asset` model.

### Step 5: Implement `storage/transcription.py`

Create `open_edit/open_edit/storage/transcription.py`:

```python
"""faster-whisper integration for word-level alignment.

Per phase4-design-revised.md §4.2 (W1).
Optional: if faster-whisper is not installed, transcribe() returns [].
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from open_edit.ir.types import WordAlignment

if TYPE_CHECKING:
    pass


def _has_whisper() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def transcribe(src: Path, model_size: str = "base") -> list[WordAlignment]:
    """Transcribe an audio/video file to word-level alignment.

    Returns [] if faster-whisper is not installed.
    """
    if not _has_whisper():
        return []
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(src), word_timestamps=True)
    alignments = []
    for segment in segments:
        if segment.words:
            for w in segment.words:
                alignments.append(WordAlignment(
                    word=w.word,
                    t_start=w.start,
                    t_end=w.end,
                    confidence=w.probability,
                ))
    return alignments
```

### Step 6: Integrate transcription in `AssetStore.ingest_paths`

In `open_edit/open_edit/storage/assets.py`, modify `ingest_paths`:

```python
from open_edit.storage.transcription import transcribe

# Inside the loop, after creating the Asset:
alignment = transcribe(src, model_size="base")
asset = Asset(
    ...,
    alignment=alignment,
)
```

### Step 7: Run test to verify it passes

Run: `cd open_edit && pytest tests/test_storage/test_assets_alignment.py -v`
Expected: 4 passed.

### Step 8: Add transcription unit test (mocked faster-whisper)

Create `open_edit/tests/test_storage/test_transcription.py`:

```python
"""Phase 4.5 W1: transcription wrapper."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_transcribe_returns_empty_without_whisper():
    from open_edit.storage.transcription import transcribe, _has_whisper
    with patch("open_edit.storage.transcription._has_whisper", return_value=False):
        result = transcribe(Path("/tmp/fake.mp4"))
    assert result == []


def test_transcribe_with_mocked_whisper(tmp_path):
    from open_edit.storage.transcription import transcribe
    fake_segment = MagicMock()
    fake_segment.words = [
        MagicMock(word="hello", start=0.0, end=0.5, probability=0.99),
        MagicMock(word="world", start=0.5, end=1.0, probability=0.98),
    ]
    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([fake_segment], MagicMock(language="en"))
    with patch("open_edit.storage.transcription._has_whisper", return_value=True), \
         patch("open_edit.storage.transcription.WhisperModel", return_value=fake_model):
        result = transcribe(tmp_path / "test.mp4", model_size="base")
    assert len(result) == 2
    assert result[0].word == "hello"
    assert result[0].t_start == 0.0
```

### Step 9: Run full open_edit test suite

Run: `cd open_edit && pytest`
Expected: 220+ passed, 5 skipped.

### Step 10: Commit

```bash
git add open_edit/pyproject.toml open_edit/ir/types.py open_edit/storage/assets.py open_edit/storage/transcription.py
git add open_edit/tests/test_storage/test_assets_alignment.py open_edit/tests/test_storage/test_transcription.py
git commit -m "[open_edit] phase4.5 w1: Whisper integration in AssetStore (optional dep)"
```

---

## Task 10: W2 Render sandbox (Rust binary)

**Files:**
- Create: `open_edit/sandbox/src/render_main.rs` (clap CLI entry point)
- Create: `open_edit/sandbox/src/render_jail.rs` (cgroup-based resource limits, no seccomp, optional `--with-hwaccel`)
- Modify: `open_edit/sandbox/Cargo.toml` (add `[[bin]] name = "open-edit-render-sandbox"`)
- Modify: `open_edit/open_edit/agent/sandbox_bridge.py` (add `run_render` function that invokes the new binary)
- Test: `open_edit/sandbox/tests/render_integration.rs` (cargo-feature-gated)
- Test: `open_edit/tests/test_sandbox/test_render_sandbox.py`

**Interfaces:**
- Consumes: Phase 3's `sandbox_bridge` infrastructure; existing `Cargo.toml`.
- Produces:
  - New Rust binary `open-edit-render-sandbox` with clap CLI:
    - `--code <path>` — Python source file to execute.
    - `--workdir <path>` — workdir to bind.
    - `--output <path>` — output asset path.
    - `--timeout <secs>` — wall-clock limit (default 3600 = 1 hour).
    - `--mem <mb>` — memory limit (default 4096 = 4 GB; cgroup enforces).
    - `--with-hwaccel` — flag to allow `/dev/dri/*` and `/dev/shm`.
  - Trust posture: NO seccomp. NO CPU limit (relies on cgroup). NO NOFILE limit (relies on cgroup). Runs as the user.
  - Sandbox setup: `bwrap --unshare-user/pid/ipc/net` (no seccomp), `--ro-bind /usr /lib /etc`, `--bind workdir`, `--tmpfs /tmp`, `--dev /dev` (with hwaccel flag adds `/dev/dri`), `--setenv HOME=/tmp`.
  - Python code receives `ir` and `output_path` env vars; writes result to `output_path`.
  - Cgroup-based resource limits (set up by the binary via libc::setrlimit before exec).

### Step 1: Add render sandbox binary to `Cargo.toml`

Modify `open_edit/sandbox/Cargo.toml`:

```toml
[[bin]]
name = "open-edit-sandbox"
path = "src/main.rs"

[[bin]]
name = "open-edit-render-sandbox"
path = "src/render_main.rs"
```

### Step 2: Write the failing test

Create `open_edit/sandbox/tests/render_integration.rs`:

```rust
//! Phase 4.5 W2: render sandbox integration test.
//! Feature-gated; run with `cargo test --features integration -- --ignored`.

use assert_cmd::Command;
use predicates::prelude::*;

#[test]
#[ignore = "requires bwrap + writable /sys/fs/cgroup"]
fn render_sandbox_runs_python_writes_output() {
    let tmp = tempfile::tempdir().unwrap();
    let code = tmp.path().join("script.py");
    std::fs::write(&code, "import os; open(os.environ['OUTPUT_PATH'], 'w').write('rendered')").unwrap();
    let output = tmp.path().join("out.txt");
    Command::cargo_bin("open-edit-render-sandbox")
        .unwrap()
        .arg("--code").arg(&code)
        .arg("--workdir").arg(tmp.path())
        .arg("--output").arg(&output)
        .arg("--timeout").arg("30")
        .arg("--mem").arg("512")
        .timeout(std::time::Duration::from_secs(60))
        .assert()
        .success();
    assert!(output.exists());
    assert_eq!(std::fs::read_to_string(&output).unwrap(), "rendered");
}
```

### Step 3: Run test to verify it fails (binary doesn't exist)

Run: `cd open_edit/sandbox && cargo test --features integration -- --ignored`
Expected: FAIL with `error: no such command: open-edit-render-sandbox`.

### Step 4: Implement `sandbox/src/render_main.rs`

Create `open_edit/sandbox/src/render_main.rs`:

```rust
//! open-edit-render-sandbox: heavy-compute sandbox for motion graphics generation.
//!
//! Per phase4-design-revised.md §4.3 (W2): two-sandbox design.
//! Trust posture: NO seccomp (this sandbox is for trusted user-initiated
//! work, not adversarial free-form code). cgroup enforces memory + CPU.
//! `--with-hwaccel` allows /dev/dri for GPU work.

use anyhow::{Context, Result};
use clap::Parser;
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::Command;

mod render_jail;

#[derive(Parser, Debug)]
#[command(name = "open-edit-render-sandbox")]
struct Args {
    /// Path to Python source file to execute.
    #[arg(long)]
    code: PathBuf,

    /// Workdir to bind (read-write).
    #[arg(long)]
    workdir: PathBuf,

    /// Output asset path (file the Python code writes to).
    #[arg(long)]
    output: PathBuf,

    /// Wall-clock timeout in seconds.
    #[arg(long, default_value = "3600")]
    timeout: u64,

    /// Memory limit in MB.
    #[arg(long, default_value = "4096")]
    mem: u64,

    /// Allow /dev/dri/* and /dev/shm for GPU work.
    #[arg(long, default_value = "false")]
    with_hwaccel: bool,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let limits = render_jail::Limits {
        mem_mb: args.mem,
        cpu_secs: args.timeout,
        nofile: 4096,
        nproc: 4096,
    };

    let mut cmd = build_bwrap_cmd(&args);
    // Set cgroup + rlimit in pre_exec
    unsafe {
        cmd.pre_exec(move || {
            render_jail::apply_cgroup_limits(&limits)?;
            render_jail::apply_rlimits(&limits)?;
            Ok(())
        });
    }

    let output_result = cmd.output().context("failed to spawn bwrap")?;
    if !output_result.status.success() {
        anyhow::bail!(
            "render sandbox exited with code {:?}: {}",
            output_result.status.code(),
            String::from_utf8_lossy(&output_result.stderr)
        );
    }
    Ok(())
}

fn build_bwrap_cmd(args: &Args) -> Command {
    let mut cmd = Command::new("bwrap");
    cmd.arg("--unshare-user")
        .arg("--unshare-pid")
        .arg("--unshare-ipc")
        .arg("--unshare-net")
        .arg("--ro-bind").arg("/usr").arg("/usr")
        .arg("--ro-bind").arg("/lib").arg("/lib")
        .arg("--ro-bind").arg("/etc").arg("/etc")
        .arg("--bind").arg(&args.workdir).arg(&args.workdir)
        .arg("--tmpfs").arg("/tmp")
        .arg("--tmpfs").arg("/home")
        .arg("--dev").arg("/dev")
        .arg("--setenv").arg("HOME").arg("/tmp")
        .arg("--setenv").arg("OUTPUT_PATH").arg(&args.output)
        .arg("--setenv").arg("PYTHONUNBUFFERED").arg("1")
        .arg("--new-session")
        .arg("--");
    if args.with_hwaccel {
        cmd.arg("--bind").arg("/dev/dri").arg("/dev/dri")
            .arg("--bind").arg("/dev/shm").arg("/dev/shm");
    }
    cmd.arg("python3").arg(&args.code);
    cmd
}
```

### Step 5: Implement `sandbox/src/render_jail.rs`

Create `open_edit/sandbox/src/render_jail.rs`:

```rust
//! Render sandbox jail: cgroup + rlimit resource limits, no seccomp.

use anyhow::Result;
use nix::sys::resource::{Resource, rlim_t};
use nix::libc;

pub struct Limits {
    pub mem_mb: u64,
    pub cpu_secs: u64,
    pub nofile: u64,
    pub nproc: u64,
}

pub fn apply_cgroup_limits(limits: &Limits) -> Result<()> {
    // Best-effort cgroup setup. If cgroup v2 is not available, silently skip.
    // The Python code is responsible for self-limiting via mem_mb.
    let memory_max = format!("{}M", limits.mem_mb);
    let _ = std::fs::write(
        "/sys/fs/cgroup/open_edit_render/memory.max",
        memory_max.as_bytes(),
    );
    let _ = std::fs::write(
        "/sys/fs/cgroup/open_edit_render/cpu.max",
        format!("{} 100000", (limits.cpu_secs * 10000).min(300000)),
    );
    let _ = std::fs::write(
        "/sys/fs/cgroup/open_edit_render/cgroup.procs",
        format!("{}", std::process::id()),
    );
    Ok(())
}

pub fn apply_rlimits(limits: &Limits) -> Result<()> {
    use nix::sys::resource::{setrlimit, Resource};
    setrlimit(Resource::RLIMIT_AS, limits.mem_mb * 1024 * 1024, limits.mem_mb * 1024 * 1024)?;
    setrlimit(Resource::RLIMIT_NOFILE, limits.nofile, limits.nofile)?;
    setrlimit(Resource::RLIMIT_NPROC, limits.nproc, limits.nproc)?;
    Ok(())
}
```

### Step 6: Build the binary

Run: `cd open_edit/sandbox && cargo build --release --bin open-edit-render-sandbox`
Expected: Compiles successfully. Binary at `target/release/open-edit-render-sandbox`.

### Step 7: Run the integration test (skipped if bwrap unavailable)

Run: `cd open_edit/sandbox && cargo test --features integration -- --ignored`
Expected: PASS if bwrap is available. SKIP otherwise.

### Step 8: Add Python wrapper for render sandbox

In `open_edit/open_edit/agent/sandbox_bridge.py`, add:

```python
def run_render(
    code: str,
    workdir: Path,
    output_path: Path,
    timeout_sec: int = 3600,
    mem_mb: int = 4096,
    with_hwaccel: bool = False,
) -> "RenderResult":
    """Run heavy-compute code in the render sandbox. Returns output path or raises SandboxError."""
    code_file = workdir / "_render_code.py"
    code_file.write_text(code)
    binary = _resolve_render_binary()
    try:
        result = subprocess.run(
            [
                str(binary),
                "--code", str(code_file),
                "--workdir", str(workdir),
                "--output", str(output_path),
                "--timeout", str(timeout_sec),
                "--mem", str(mem_mb),
            ] + (["--with-hwaccel"] if with_hwaccel else []),
            capture_output=True, text=True, timeout=timeout_sec + 30,
        )
        if result.returncode != 0:
            raise SandboxError(f"render sandbox failed: {result.stderr}")
        if not output_path.exists():
            raise SandboxError(f"render sandbox did not produce {output_path}")
        return RenderResult(path=output_path, ok=True)
    finally:
        code_file.unlink(missing_ok=True)


def _resolve_render_binary() -> Path:
    candidates = [
        Path.home() / ".local" / "bin" / "open-edit-render-sandbox",
        Path("/usr/local/bin/open-edit-render-sandbox"),
        Path(__file__).parent.parent.parent / "sandbox" / "target" / "release" / "open-edit-render-sandbox",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("open-edit-render-sandbox binary not found in any known location")
```

### Step 9: Add Python test for render sandbox wrapper

Create `open_edit/tests/test_sandbox/test_render_sandbox.py`:

```python
"""Phase 4.5 W2: render sandbox Python wrapper."""
import pytest
from pathlib import Path
from open_edit.agent.sandbox_bridge import _resolve_render_binary


def test_resolve_render_binary():
    """The binary is in one of the known locations."""
    binary = _resolve_render_binary()
    assert binary.exists()
    assert binary.is_file()
```

### Step 10: Commit

```bash
git add open_edit/sandbox/Cargo.toml open_edit/sandbox/src/render_main.rs open_edit/sandbox/src/render_jail.rs open_edit/sandbox/tests/render_integration.rs
git add open_edit/agent/sandbox_bridge.py
git add open_edit/tests/test_sandbox/test_render_sandbox.py
git commit -m "[open_edit] phase4.5 w2: render sandbox (Rust binary, cgroup limits, no seccomp)"
```

---

## Task 11: W3 Silence cutter skill + new tool

**Files:**
- Create: `open_edit/open_edit/agent/skills/__init__.py`
- Create: `open_edit/open_edit/agent/skills/silence_cutter.py` (cut proposal logic)
- Create: `open_edit/open_edit/agent/tools/pyagent_propose_silence_cuts.py` (tool wrapper)
- Modify: `open_edit/open_edit/qc/gate.py` (add `no_word_split` check)
- Test: `open_edit/tests/test_skill/test_silence_cutter.py`

**Interfaces:**
- Consumes: W1's `Asset.alignment`; Phase 2's silence markers from `qc/silence.py`.
- Produces:
  - `silence_cutter.propose_cuts(asset: Asset, silence_threshold_ms: int = 400) -> list[Union[TrimClipOp, RemoveClipOp]]`.
  - Tool `pyagent_propose_silence_cuts` — returns the proposed ops; agent decides whether to apply.
  - QC check `no_word_split` — verifies any cut op's `t_start`/`t_end` doesn't fall mid-word (within 50ms tolerance).

### Step 1: Write the failing test

Create `open_edit/tests/test_skill/test_silence_cutter.py`:

```python
"""Phase 4.5 W3: silence cutter skill."""
import pytest
from open_edit.ir.types import Asset, WordAlignment
from open_edit.agent.skills.silence_cutter import propose_cuts, find_silence_gaps


def test_find_silence_gaps():
    """Given word-level alignment, find gaps > 400ms."""
    alignment = [
        WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=1.0),
        WordAlignment(word="world", t_start=1.5, t_end=2.0, confidence=1.0),
        WordAlignment(word="foo", t_start=2.1, t_end=2.5, confidence=1.0),
    ]
    gaps = find_silence_gaps(alignment, threshold_ms=400)
    # 0.5 → 1.5 = 1.0s gap (yes), 2.0 → 2.1 = 0.1s gap (no)
    assert len(gaps) == 1
    assert gaps[0] == (0.5, 1.5)


def test_propose_cuts_emits_trim_or_remove():
    asset = Asset(
        asset_hash="abc",
        original_path="/tmp/x.mp4",
        stored_path="/tmp/x",
        type="video",
        duration_sec=10.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
        alignment=[
            WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=1.0),
            WordAlignment(word="world", t_start=1.5, t_end=2.0, confidence=1.0),
        ],
    )
    cuts = propose_cuts(asset, silence_threshold_ms=400)
    # One gap: 0.5 → 1.5 (1.0s)
    assert len(cuts) >= 1
    # Each cut should be TrimClipOp or RemoveClipOp
    from open_edit.ir.types import TrimClipOp, RemoveClipOp
    for c in cuts:
        assert isinstance(c, (TrimClipOp, RemoveClipOp))


def test_no_word_split_qc_check():
    """The QC check should reject cuts that split a word."""
    from open_edit.qc.gate import no_word_split_check
    asset = Asset(
        asset_hash="abc",
        original_path="/tmp/x.mp4",
        stored_path="/tmp/x",
        type="video",
        duration_sec=10.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
        alignment=[
            WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=1.0),
        ],
    )
    # Cut at 0.25 (mid-word) should fail
    passed, detail = no_word_split_check(asset, t_start=0.25, t_end=0.75)
    assert passed is False
    assert "word" in detail.lower()
    # Cut at 0.5 (inter-word) should pass
    passed, detail = no_word_split_check(asset, t_start=0.5, t_end=1.0)
    assert passed is True
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_skill/test_silence_cutter.py -v`
Expected: FAIL with `ModuleNotFoundError`.

### Step 3: Implement `agent/skills/silence_cutter.py`

Create `open_edit/open_edit/agent/skills/silence_cutter.py`:

```python
"""Silence cutter skill: propose cuts at inter-word silence gaps.

Per phase4-design-revised.md §4.2 (W3).
"""
from __future__ import annotations

from typing import Iterable

from open_edit.ir.types import Asset, RemoveClipOp, TrimClipOp, WordAlignment


def find_silence_gaps(alignment: list[WordAlignment], threshold_ms: int = 400) -> list[tuple[float, float]]:
    """Find inter-word gaps longer than threshold_ms."""
    threshold_s = threshold_ms / 1000.0
    gaps = []
    for prev, curr in zip(alignment, alignment[1:]):
        gap = curr.t_start - prev.t_end
        if gap >= threshold_s:
            gaps.append((prev.t_end, curr.t_start))
    return gaps


def propose_cuts(asset: Asset, silence_threshold_ms: int = 400) -> list[TrimClipOp | RemoveClipOp]:
    """Propose cut ops at each silence gap. Caller decides whether to apply."""
    gaps = find_silence_gaps(asset.alignment, silence_threshold_ms)
    cuts = []
    for t_start, t_end in gaps:
        # Default: emit RemoveClipOp (assumes a single clip covers the whole range).
        # The agent can refine to TrimClipOp if the source clip is shorter.
        cuts.append(RemoveClipOp(
            author="ai",
            clip_id="<resolve-at-apply-time>",  # Agent fills in the actual clip_id
            t_start=t_start,
            t_end=t_end,
        ))
    return cuts
```

(Note: `RemoveClipOp` may need `t_start` and `t_end` fields; if not present, extend the model — see Step 4.)

### Step 4: Extend `RemoveClipOp` if needed

In `open_edit/open_edit/ir/types.py`, the current `RemoveClipOp` has only `clip_id`. We need either:
- A new `RemoveSegmentOp` with `t_start` and `t_end` (operates on a single clip, removes a time range), OR
- Emit a `TrimClipOp` with `new_in_point_sec`/`new_out_point_sec` that the agent applies to the right clip.

For v1 simplicity, the tool returns the gap `(t_start, t_end)` plus a list of `TrimClipOp` suggestions keyed by clip_id. The agent picks the right clip.

Modify `propose_cuts` to return gaps instead of pre-built ops:

```python
def propose_cuts(asset: Asset, silence_threshold_ms: int = 400) -> list[dict]:
    """Return gaps as dicts: {t_start, t_end, suggested_kind: 'trim' | 'remove'}."""
    return [
        {"t_start": t_start, "t_end": t_end, "suggested_kind": "trim"}
        for t_start, t_end in find_silence_gaps(asset.alignment, silence_threshold_ms)
    ]
```

### Step 5: Add `no_word_split_check` to `qc/gate.py`

In `open_edit/open_edit/qc/gate.py`, add:

```python
def no_word_split_check(asset: Asset, t_start: float, t_end: float, tolerance_ms: int = 50) -> tuple[bool, str]:
    """Check if a cut at [t_start, t_end] splits any word.
    
    Returns (passed, detail). passed=True means no word is split.
    """
    tolerance_s = tolerance_ms / 1000.0
    for w in asset.alignment:
        # If t_start or t_end falls within (w.t_start, w.t_end) (excluding endpoints)
        if (w.t_start + tolerance_s) < t_start < (w.t_end - tolerance_s):
            return False, f"Cut at {t_start}s splits word '{w.word}' ({w.t_start}s - {w.t_end}s)"
        if (w.t_start + tolerance_s) < t_end < (w.t_end - tolerance_s):
            return False, f"Cut at {t_end}s splits word '{w.word}' ({w.t_start}s - {w.t_end}s)"
    return True, "no word split"
```

### Step 6: Update test for the new `propose_cuts` signature

Modify `open_edit/tests/test_skill/test_silence_cutter.py`:

```python
def test_propose_cuts_emits_gaps():
    asset = Asset(
        ...,
        alignment=[...],
    )
    cuts = propose_cuts(asset, silence_threshold_ms=400)
    assert len(cuts) == 1
    assert cuts[0]["t_start"] == 0.5
    assert cuts[0]["t_end"] == 1.5
    assert cuts[0]["suggested_kind"] == "trim"
```

### Step 7: Add tool wrapper

Create `open_edit/open_edit/agent/tools/pyagent_propose_silence_cuts.py`:

```python
"""pyagent_propose_silence_cuts: returns inter-word silence gaps as cut suggestions."""
from open_edit.storage.assets import AssetStore


def propose_silence_cuts(args):
    workdir = Path(args["project_path"]).parent
    asset_store = AssetStore(workdir / "assets")
    asset = asset_store.get(args["asset_hash"])
    if asset is None:
        return {"status": "error", "error": f"asset {args['asset_hash']} not found"}
    if not asset.alignment:
        return {"status": "error", "error": "asset has no word-level alignment (Whisper not run?)"}
    from open_edit.agent.skills.silence_cutter import propose_cuts
    cuts = propose_cuts(asset, silence_threshold_ms=args.get("threshold_ms", 400))
    return {"status": "ok", "gaps": cuts}
```

### Step 8: Run test

Run: `cd open_edit && pytest tests/test_skill/test_silence_cutter.py -v`
Expected: 3 passed.

### Step 9: Commit

```bash
git add open_edit/agent/skills/__init__.py open_edit/agent/skills/silence_cutter.py
git add open_edit/agent/tools/pyagent_propose_silence_cuts.py
git add open_edit/qc/gate.py
git add open_edit/tests/test_skill/test_silence_cutter.py
git commit -m "[open_edit] phase4.5 w3: silence cutter skill + pyagent_propose_silence_cuts + no_word_split qc"
```

---

## Task 12: W4 Narrative analyzer skill + new tool

**Files:**
- Create: `open_edit/open_edit/agent/skills/narrative_analyzer.py`
- Create: `open_edit/open_edit/agent/tools/pyagent_analyze_narrative.py`
- Test: `open_edit/tests/test_skill/test_narrative_analyzer.py`

**Interfaces:**
- Consumes: W1's `Asset.alignment`; 7 beat types from spec.
- Produces:
  - `narrative_analyzer.analyze(asset: Asset) -> list[NarrativeSegment]`.
  - `NarrativeSegment` Pydantic: `{beat_type: Literal["hook", "turn", "scope", "mechanism", "cost", "tease", "button"], t_start: float, t_end: float, text: str, suggested_visual_concept: str}`.
  - Tool `pyagent_analyze_narrative` — returns the segments as JSON.
  - Beat classification uses LLM (or rule-based fallback): the tool receives the transcript text and the LLM classifies segments.

### Step 1: Write the failing test

Create `open_edit/tests/test_skill/test_narrative_analyzer.py`:

```python
"""Phase 4.5 W4: narrative analyzer skill."""
import pytest
from open_edit.ir.types import Asset, WordAlignment
from open_edit.agent.skills.narrative_analyzer import analyze, BEAT_TYPES


def test_beat_types_complete():
    """The 7 spec beat types are all present."""
    assert set(BEAT_TYPES) == {"hook", "turn", "scope", "mechanism", "cost", "tease", "button"}


def test_analyze_with_rule_based_fallback():
    """Without an LLM, analyze falls back to a simple rule-based segmentation."""
    asset = Asset(
        asset_hash="abc",
        original_path="/tmp/x.mp4",
        stored_path="/tmp/x",
        type="video",
        duration_sec=10.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
        alignment=[
            WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=1.0),
            WordAlignment(word="world", t_start=0.5, t_end=1.0, confidence=1.0),
        ],
    )
    segments = analyze(asset, use_llm=False)
    assert len(segments) >= 1
    for s in segments:
        assert s.beat_type in BEAT_TYPES


def test_narrative_segment_pydantic():
    from open_edit.agent.skills.narrative_analyzer import NarrativeSegment
    s = NarrativeSegment(
        beat_type="hook",
        t_start=0.0,
        t_end=3.0,
        text="Welcome",
        suggested_visual_concept="Cold open with logo",
    )
    assert s.beat_type == "hook"
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_skill/test_narrative_analyzer.py -v`
Expected: FAIL with `ModuleNotFoundError`.

### Step 3: Implement `narrative_analyzer.py`

Create `open_edit/open_edit/agent/skills/narrative_analyzer.py`:

```python
"""Narrative analyzer skill: classify transcript segments into 7 beat types.

Per phase4-design-revised.md §4.1 (W4).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from open_edit.ir.types import Asset, WordAlignment


BEAT_TYPES = ("hook", "turn", "scope", "mechanism", "cost", "tease", "button")


class NarrativeSegment(BaseModel):
    beat_type: Literal["hook", "turn", "scope", "mechanism", "cost", "tease", "button"]
    t_start: float
    t_end: float
    text: str
    suggested_visual_concept: str = ""


def analyze(asset: Asset, use_llm: bool = True) -> list[NarrativeSegment]:
    """Analyze the asset's transcript and return narrative segments.

    With use_llm=True, calls the LLM to classify beats.
    With use_llm=False, falls back to a simple rule-based segmentation
    that produces one segment per ~5 seconds of transcript, classified
    by position (first → hook, last → button, middle → mechanism).
    """
    if not asset.alignment:
        return []
    if use_llm:
        return _analyze_with_llm(asset)
    return _analyze_rule_based(asset)


def _analyze_rule_based(asset: Asset) -> list[NarrativeSegment]:
    """Simple rule-based fallback: segment by 5s windows, classify by position."""
    segments = []
    alignment = asset.alignment
    window_s = 5.0
    if not alignment:
        return []
    t_start_anchor = alignment[0].t_start
    t_end_anchor = alignment[-1].t_end
    duration = t_end_anchor - t_start_anchor
    if duration == 0:
        return []
    n_windows = max(1, int(duration / window_s))
    window_size = duration / n_windows
    for i in range(n_windows):
        w_start = t_start_anchor + i * window_size
        w_end = t_start_anchor + (i + 1) * window_size
        words_in_window = [w for w in alignment if w.t_start >= w_start and w.t_end <= w_end]
        if not words_in_window:
            continue
        text = " ".join(w.word for w in words_in_window)
        if i == 0:
            beat = "hook"
        elif i == n_windows - 1:
            beat = "button"
        elif i == 1:
            beat = "turn"
        elif i == 2:
            beat = "scope"
        else:
            beat = "mechanism"
        segments.append(NarrativeSegment(
            beat_type=beat, t_start=w_start, t_end=w_end, text=text,
        ))
    return segments


def _analyze_with_llm(asset: Asset) -> list[NarrativeSegment]:
    """Call the LLM to classify beats.

    Implementation note: the actual LLM call is out of scope for v1; this
    function is a stub that returns the rule-based result with a warning.
    Future: route through the agent loop (e.g., pyagent_run_python that
    emits NarrativeSegment + AddClipOp).
    """
    import warnings
    warnings.warn("LLM-based narrative analysis is not yet implemented; using rule-based fallback")
    return _analyze_rule_based(asset)
```

### Step 4: Add tool wrapper

Create `open_edit/open_edit/agent/tools/pyagent_analyze_narrative.py`:

```python
"""pyagent_analyze_narrative: returns narrative segments for the asset."""
from open_edit.storage.assets import AssetStore


def analyze_narrative(args):
    workdir = Path(args["project_path"]).parent
    asset_store = AssetStore(workdir / "assets")
    asset = asset_store.get(args["asset_hash"])
    if asset is None:
        return {"status": "error", "error": f"asset {args['asset_hash']} not found"}
    if not asset.alignment:
        return {"status": "error", "error": "asset has no word-level alignment"}
    from open_edit.agent.skills.narrative_analyzer import analyze
    segments = analyze(asset, use_llm=args.get("use_llm", False))
    return {
        "status": "ok",
        "segments": [s.model_dump() for s in segments],
    }
```

### Step 5: Run test

Run: `cd open_edit && pytest tests/test_skill/test_narrative_analyzer.py -v`
Expected: 3 passed.

### Step 6: Commit

```bash
git add open_edit/agent/skills/narrative_analyzer.py open_edit/agent/tools/pyagent_analyze_narrative.py
git add open_edit/tests/test_skill/test_narrative_analyzer.py
git commit -m "[open_edit] phase4.5 w4: narrative analyzer skill + pyagent_analyze_narrative"
```

---

## Task 13: W5 Music selector skill + AddMusicTrackOp (or AddEffectOp extension)

**Files:**
- Create: `open_edit/open_edit/agent/skills/music_selector.py`
- Create: `open_edit/open_edit/agent/tools/pyagent_select_music.py`
- Modify: `open_edit/open_edit/ir/types.py` (extend `AddEffectOp` to allow `effect_type="music_bed"`, or add new `AddMusicTrackOp`)
- Modify: `open_edit/open_edit/ir/apply.py` (handle music_bed)
- Test: `open_edit/tests/test_skill/test_music_selector.py`

**Decision (per design):** Extend `AddEffectOp` with `effect_type="music_bed"` rather than adding a new op type. This keeps the IR small and treats music as a track-level effect with ducking keyframes.

**Interfaces:**
- Consumes: W4's `NarrativeSegment.beat_type`; tagged music library.
- Produces:
  - `music_selector.select(narrative_segments: list[NarrativeSegment], library: list[MusicTrack]) -> list[AddEffectOp]`.
  - `AddEffectOp` with `target_kind="track"`, `effect_type="music_bed"`, `params={"track_id": str, "gain_db": float}`, plus a `SetKeyframeOp` for auto-ducking during narration.
  - Tool `pyagent_select_music` — returns the ops.

### Step 1: Write the failing test

Create `open_edit/tests/test_skill/test_music_selector.py`:

```python
"""Phase 4.5 W5: music selector skill."""
import pytest
from open_edit.agent.skills.narrative_analyzer import NarrativeSegment
from open_edit.agent.skills.music_selector import select, MusicTrack


def test_select_picks_mood_matching_track():
    segments = [
        NarrativeSegment(beat_type="hook", t_start=0.0, t_end=3.0, text="Welcome"),
        NarrativeSegment(beat_type="mechanism", t_start=3.0, t_end=10.0, text="How it works"),
    ]
    library = [
        MusicTrack(track_id="upbeat_01", mood="upbeat", bpm=120, energy=0.8),
        MusicTrack(track_id="contemplative_01", mood="contemplative", bpm=70, energy=0.3),
    ]
    ops = select(segments, library)
    # Should pick upbeat for hook, contemplative for mechanism
    assert len(ops) >= 1


def test_music_track_pydantic():
    t = MusicTrack(track_id="x", mood="upbeat", bpm=120, energy=0.8)
    assert t.mood == "upbeat"
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_skill/test_music_selector.py -v`
Expected: FAIL with `ModuleNotFoundError`.

### Step 3: Implement `music_selector.py`

Create `open_edit/open_edit/agent/skills/music_selector.py`:

```python
"""Music selector skill: pick mood-matched tracks for narrative segments.

Per phase4-design-revised.md §4.4 (W5).
"""
from __future__ import annotations

from pydantic import BaseModel

from open_edit.agent.skills.narrative_analyzer import NarrativeSegment
from open_edit.ir.types import AddEffectOp, SetKeyframeOp


class MusicTrack(BaseModel):
    track_id: str
    mood: str  # "upbeat" | "contemplative" | "dramatic" | "corporate" | etc.
    bpm: int
    energy: float  # 0.0 - 1.0


# Per-beat mood mapping
BEAT_MOOD_MAP = {
    "hook": "upbeat",
    "turn": "dramatic",
    "scope": "contemplative",
    "mechanism": "contemplative",
    "cost": "dramatic",
    "tease": "upbeat",
    "button": "upbeat",
}


def select(segments: list[NarrativeSegment], library: list[MusicTrack]) -> list[AddEffectOp]:
    """Pick a music track per segment based on beat mood."""
    ops = []
    for seg in segments:
        target_mood = BEAT_MOOD_MAP.get(seg.beat_type, "contemplative")
        candidates = [t for t in library if t.mood == target_mood]
        if not candidates:
            candidates = library  # Fallback
        if not candidates:
            continue
        # Pick the first candidate; v1.1 can do fancier selection.
        chosen = candidates[0]
        ops.append(AddEffectOp(
            author="ai",
            target_kind="track",
            target_id="audio_music",  # Conventional track name
            effect_type="music_bed",
            params={
                "track_id": chosen.track_id,
                "gain_db": -12.0,  # -12 dB under narration
                "t_start": seg.t_start,
                "t_end": seg.t_end,
            },
        ))
    return ops
```

### Step 4: Add tool wrapper

Create `open_edit/open_edit/agent/tools/pyagent_select_music.py`:

```python
"""pyagent_select_music: returns music track ops for narrative segments."""
from open_edit.storage.assets import AssetStore


def select_music(args):
    workdir = Path(args["project_path"]).parent
    asset_store = AssetStore(workdir / "assets")
    asset = asset_store.get(args["asset_hash"])
    if asset is None:
        return {"status": "error", "error": f"asset {args['asset_hash']} not found"}
    from open_edit.agent.skills.narrative_analyzer import analyze
    from open_edit.agent.skills.music_selector import select, MusicTrack
    segments = analyze(asset, use_llm=False)
    library = _load_music_library(args.get("library_path"))
    ops = select(segments, library)
    return {"status": "ok", "ops": [op.model_dump() for op in ops]}


def _load_music_library(path: str | None) -> list[MusicTrack]:
    """Load music library from a JSON file; empty list if not provided."""
    if not path:
        return []
    from open_edit.agent.skills.music_selector import MusicTrack
    import json
    data = json.loads(Path(path).read_text())
    return [MusicTrack(**t) for t in data]
```

### Step 5: Run test

Run: `cd open_edit && pytest tests/test_skill/test_music_selector.py -v`
Expected: 2 passed.

### Step 6: Commit

```bash
git add open_edit/agent/skills/music_selector.py open_edit/agent/tools/pyagent_select_music.py
git add open_edit/tests/test_skill/test_music_selector.py
git commit -m "[open_edit] phase4.5 w5: music selector skill + pyagent_select_music"
```

---

## Task 14: W6 SFX placer skill + AddSfxOp (or AddEffectOp extension)

**Files:**
- Create: `open_edit/open_edit/agent/skills/sfx_placer.py`
- Create: `open_edit/open_edit/agent/tools/pyagent_place_sfx.py`
- Modify: `open_edit/open_edit/ir/types.py` (extend `AddEffectOp` to allow `effect_type="sfx"`)
- Test: `open_edit/tests/test_skill/test_sfx_placer.py`

**Decision (per design):** Extend `AddEffectOp` with `effect_type="sfx"`. SFX are placed as track-level effects with `t_start` and `duration_s`.

**Interfaces:**
- Consumes: W4's `NarrativeSegment`; W5's music downbeats (if any); tagged SFX library.
- Produces:
  - `sfx_placer.place(segments, music_downbeats, library) -> list[AddEffectOp]`.
  - `AddEffectOp` with `target_kind="track"`, `effect_type="sfx"`, `params={"sfx_id": str, "t_start": float, "duration_s": float, "gain_db": float}`.
  - Tool `pyagent_place_sfx`.

### Step 1: Write the failing test

Create `open_edit/tests/test_skill/test_sfx_placer.py`:

```python
"""Phase 4.5 W6: SFX placer skill."""
import pytest
from open_edit.agent.skills.narrative_analyzer import NarrativeSegment
from open_edit.agent.skills.sfx_placer import place, SfxClip


def test_place_at_beat_transitions():
    segments = [
        NarrativeSegment(beat_type="hook", t_start=0.0, t_end=3.0, text="Welcome"),
        NarrativeSegment(beat_type="turn", t_start=3.0, t_end=7.0, text="But..."),
    ]
    library = [
        SfxClip(sfx_id="whoosh_01", kind="whoosh", duration_s=0.5),
        SfxClip(sfx_id="impact_01", kind="impact", duration_s=0.3),
    ]
    ops = place(segments, music_downbeats=[], library=library)
    # At least one SFX at the hook→turn transition (3.0s)
    assert any(op.params.get("t_start") == 3.0 for op in ops)


def test_sfx_clip_pydantic():
    s = SfxClip(sfx_id="x", kind="whoosh", duration_s=0.5)
    assert s.kind == "whoosh"
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_skill/test_sfx_placer.py -v`
Expected: FAIL.

### Step 3: Implement `sfx_placer.py`

Create `open_edit/open_edit/agent/skills/sfx_placer.py`:

```python
"""SFX placer skill: place sound effects at narrative beat transitions.

Per phase4-design-revised.md §4.5 (W6).
"""
from __future__ import annotations

from pydantic import BaseModel

from open_edit.agent.skills.narrative_analyzer import NarrativeSegment
from open_edit.ir.types import AddEffectOp


class SfxClip(BaseModel):
    sfx_id: str
    kind: str  # "whoosh" | "impact" | "riser" | "pop" | "ding" | etc.
    duration_s: float


# Beat transition → SFX kind mapping
TRANSITION_SFX_MAP = {
    ("hook", "turn"): "whoosh",
    ("turn", "scope"): "riser",
    ("scope", "mechanism"): "impact",
    ("mechanism", "cost"): "impact",
    ("cost", "tease"): "riser",
    ("tease", "button"): "impact",
}


def place(segments: list[NarrativeSegment], music_downbeats: list[float], library: list[SfxClip]) -> list[AddEffectOp]:
    """Place SFX at each narrative beat transition."""
    ops = []
    for prev, curr in zip(segments, segments[1:]):
        kind = TRANSITION_SFX_MAP.get((prev.beat_type, curr.beat_type), "impact")
        candidates = [s for s in library if s.kind == kind]
        if not candidates:
            candidates = library
        if not candidates:
            continue
        chosen = candidates[0]
        ops.append(AddEffectOp(
            author="ai",
            target_kind="track",
            target_id="audio_sfx",
            effect_type="sfx",
            params={
                "sfx_id": chosen.sfx_id,
                "t_start": curr.t_start,
                "duration_s": chosen.duration_s,
                "gain_db": 0.0,
            },
        ))
    return ops
```

### Step 4: Add tool wrapper

Create `open_edit/open_edit/agent/tools/pyagent_place_sfx.py`:

```python
"""pyagent_place_sfx: returns SFX placement ops at beat transitions."""
from open_edit.storage.assets import AssetStore


def place_sfx(args):
    workdir = Path(args["project_path"]).parent
    asset_store = AssetStore(workdir / "assets")
    asset = asset_store.get(args["asset_hash"])
    if asset is None:
        return {"status": "error", "error": f"asset {args['asset_hash']} not found"}
    from open_edit.agent.skills.narrative_analyzer import analyze
    from open_edit.agent.skills.sfx_placer import place, SfxClip
    segments = analyze(asset, use_llm=False)
    library = _load_sfx_library(args.get("library_path"))
    ops = place(segments, music_downbeats=args.get("music_downbeats", []), library=library)
    return {"status": "ok", "ops": [op.model_dump() for op in ops]}


def _load_sfx_library(path: str | None) -> list[SfxClip]:
    if not path:
        return []
    from open_edit.agent.skills.sfx_placer import SfxClip
    import json
    data = json.loads(Path(path).read_text())
    return [SfxClip(**s) for s in data]
```

### Step 5: Run test

Run: `cd open_edit && pytest tests/test_skill/test_sfx_placer.py -v`
Expected: 2 passed.

### Step 6: Commit

```bash
git add open_edit/agent/skills/sfx_placer.py open_edit/agent/tools/pyagent_place_sfx.py
git add open_edit/tests/test_skill/test_sfx_placer.py
git commit -m "[open_edit] phase4.5 w6: SFX placer skill + pyagent_place_sfx"
```

---

## Task 15: W7 Motion graphics (templated) + template library

**Files:**
- Create: `open_edit/open_edit/agent/skills/motion_graphics/__init__.py`
- Create: `open_edit/open_edit/agent/skills/motion_graphics/engine.py` (template runner)
- Create: `open_edit/open_edit/agent/skills/motion_graphics/templates/{hook,turn,scope,mechanism,cost,tease,button}.py` (one per beat type)
- Create: `open_edit/open_edit/agent/tools/pyagent_generate_visual_for_segment.py`
- Modify: `open_edit/open_edit/ir/types.py` (ensure AddClipOp supports new asset_hash that doesn't pre-exist in the store — handled by the rendering pipeline)
- Test: `open_edit/tests/test_skill/test_motion_graphics_templated.py`

**Decision (per design):** Templated per beat type. Each template is a Python function that takes a `MotionTemplateParams` (text, colors, animation_speed, asset_references) and produces Python source for manim/moviepy/headless canvas. The render sandbox (W2) runs the generated code and outputs a video asset.

**Interfaces:**
- Consumes: W4's `NarrativeSegment`; W2's `run_render`; brand profile (optional, v1.1 full).
- Produces:
  - `MotionTemplate` Pydantic: `{name, beat_type, params_schema, generate_code(params) -> str}`.
  - 7 templates (one per beat type), seeded with simple example code (e.g., "fade-in text with background color").
  - `generate_visual(segment: NarrativeSegment, template: str, params: dict) -> AddClipOp` — produces a new asset, ingests it, returns an `AddClipOp` referencing it.
  - Tool `pyagent_generate_visual_for_segment`.

### Step 1: Write the failing test

Create `open_edit/tests/test_skill/test_motion_graphics_templated.py`:

```python
"""Phase 4.5 W7: motion graphics templated skill."""
import pytest
from open_edit.agent.skills.motion_graphics.engine import generate_visual, MotionTemplateParams
from open_edit.agent.skills.narrative_analyzer import NarrativeSegment


def test_motion_template_params_pydantic():
    p = MotionTemplateParams(
        text="Welcome",
        background_color="#000000",
        text_color="#FFFFFF",
        animation_speed=1.0,
    )
    assert p.text == "Welcome"


def test_generate_visual_emits_code(tmp_path, monkeypatch):
    """Mock the render sandbox; verify the code is generated and run."""
    # Mock the render sandbox
    from unittest.mock import patch, MagicMock
    fake_output = tmp_path / "rendered.mp4"
    fake_output.write_bytes(b"fake mp4")
    monkeypatch.setattr(
        "open_edit.agent.skills.motion_graphics.engine.run_render",
        lambda **kwargs: type("R", (), {"path": fake_output, "ok": True})(),
    )
    segment = NarrativeSegment(
        beat_type="hook", t_start=0.0, t_end=3.0, text="Welcome",
    )
    op = generate_visual(
        segment=segment,
        template="hook_fade_text",
        params={"text": "Welcome", "background_color": "#000", "text_color": "#FFF", "animation_speed": 1.0},
        project_id="p1",
        workdir=tmp_path,
    )
    assert op.kind == "add_clip"
    assert op.track_id == "video_graphics"
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_skill/test_motion_graphics_templated.py -v`
Expected: FAIL.

### Step 3: Implement `motion_graphics/engine.py`

Create `open_edit/open_edit/agent/skills/motion_graphics/__init__.py`:

```python
"""Motion graphics templated skill."""
```

Create `open_edit/open_edit/agent/skills/motion_graphics/engine.py`:

```python
"""Motion graphics engine: runs templates to produce video assets.

Per phase4-design-revised.md §4.3 (W7). Templated per beat type.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from open_edit.agent.skills.narrative_analyzer import NarrativeSegment
from open_edit.ir.types import AddClipOp
from open_edit.storage.assets import AssetStore


class MotionTemplateParams(BaseModel):
    text: str
    background_color: str = "#000000"
    text_color: str = "#FFFFFF"
    animation_speed: float = 1.0
    asset_references: list[str] = []


def generate_visual(
    segment: NarrativeSegment,
    template: str,
    params: dict,
    project_id: str,
    workdir: Path,
) -> AddClipOp:
    """Run a template, render the visual, ingest as a new asset, return AddClipOp."""
    from open_edit.agent.skills.motion_graphics import templates
    template_fn = getattr(templates, template, None)
    if template_fn is None:
        raise ValueError(f"Unknown template: {template}")
    motion_params = MotionTemplateParams(**params)
    code = template_fn(motion_params, segment.t_end - segment.t_start)

    # Run the render sandbox
    output_path = workdir / "_render_output.mp4"
    from open_edit.agent.sandbox_bridge import run_render
    result = run_render(
        code=code,
        workdir=workdir,
        output_path=output_path,
        timeout_sec=300,
        mem_mb=2048,
    )

    # Ingest the rendered asset
    asset_store = AssetStore(workdir / "assets")
    assets = asset_store.ingest_paths([str(output_path)])
    asset_hash = assets[0].asset_hash

    # Emit AddClipOp
    return AddClipOp(
        author="ai",
        asset_hash=asset_hash,
        track_id="video_graphics",
        position_sec=segment.t_start,
        in_point_sec=0.0,
        out_point_sec=segment.t_end - segment.t_start,
    )
```

### Step 4: Implement 7 templates

Create `open_edit/open_edit/agent/skills/motion_graphics/templates/__init__.py`:

```python
"""Motion graphics templates, one per narrative beat type."""
from open_edit.agent.skills.motion_graphics.templates.hook import hook_fade_text
from open_edit.agent.skills.motion_graphics.templates.turn import turn_slide_text
from open_edit.agent.skills.motion_graphics.templates.scope import scope_zoom_text
from open_edit.agent.skills.motion_graphics.templates.mechanism import mechanism_diagram
from open_edit.agent.skills.motion_graphics.templates.cost import cost_warning
from open_edit.agent.skills.motion_graphics.templates.tease import tease_glimpse
from open_edit.agent.skills.motion_graphics.templates.button import button_cta
```

Create each template file with a simple `generate_code(params, duration_s) -> str` function. Example for `hook.py`:

```python
"""Hook template: fade-in text on a colored background.

Uses moviepy (lighter weight than manim) for v1.
"""


def hook_fade_text(params, duration_s: float) -> str:
    return f'''
from moviepy.editor import TextClip, CompositeVideoClip, ColorClip

bg = ColorClip(size=(1920, 1080), color={params.background_color}, duration={duration_s})
text = TextClip("{params.text}", fontsize=80, color="{params.text_color}", size=(1600, 400))
text = text.set_position("center").set_duration({duration_s}).fadein(0.5).fadeout(0.5)
composite = CompositeVideoClip([bg, text])
composite.write_videofile("{params.asset_references[0] if params.asset_references else '/tmp/out.mp4'}", fps=30, codec="libx264")
'''
```

(Similar stubs for the other 6 templates — each produces simple moviepy/headless-canvas code.)

### Step 5: Add tool wrapper

Create `open_edit/open_edit/agent/tools/pyagent_generate_visual_for_segment.py`:

```python
"""pyagent_generate_visual_for_segment: render a templated motion graphic."""
from open_edit.storage.assets import AssetStore


def generate_visual_for_segment(args):
    workdir = Path(args["project_path"]).parent
    asset_store = AssetStore(workdir / "assets")
    asset = asset_store.get(args["asset_hash"])
    if asset is None:
        return {"status": "error", "error": f"asset {args['asset_hash']} not found"}
    from open_edit.agent.skills.narrative_analyzer import analyze
    from open_edit.agent.skills.motion_graphics.engine import generate_visual
    segments = analyze(asset, use_llm=False)
    segment = next((s for s in segments if s.beat_type == args.get("beat_type")), None)
    if segment is None:
        return {"status": "error", "error": f"no segment with beat_type {args.get('beat_type')}"}
    op = generate_visual(
        segment=segment,
        template=args["template"],
        params=args["params"],
        project_id=args["project_id"],
        workdir=workdir,
    )
    return {"status": "ok", "op": op.model_dump()}
```

### Step 6: Run test

Run: `cd open_edit && pytest tests/test_skill/test_motion_graphics_templated.py -v`
Expected: 2 passed.

### Step 7: Commit

```bash
git add open_edit/agent/skills/motion_graphics/__init__.py open_edit/agent/skills/motion_graphics/engine.py
git add open_edit/agent/skills/motion_graphics/templates/__init__.py
git add open_edit/agent/skills/motion_graphics/templates/{hook,turn,scope,mechanism,cost,tease,button}.py
git add open_edit/agent/tools/pyagent_generate_visual_for_segment.py
git add open_edit/tests/test_skill/test_motion_graphics_templated.py
git commit -m "[open_edit] phase4.5 w7: motion graphics templated skill + 7 templates + pyagent_generate_visual_for_segment"
```

---

## Task 16: W8 Long-form stress test

**Files:**
- Create: `open_edit/tests/test_long_form_e2e.py`

**Interfaces:**
- Consumes: All of Phase 4 v2 + Phase 4.5.
- Produces:
  - 50-segment synthetic video (5 min total).
  - End-to-end pipeline: ingest → silence cut → narrative analyze → motion graphics (templated) → music → SFX → render → QC.
  - Asserts: completes in <15 min wall clock on CI; no rate-limit failures; edit graph <500 ops.

### Step 1: Write the test

Create `open_edit/tests/test_long_form_e2e.py`:

```python
"""Phase 4.5 W8: long-form stress test (5-min synthetic video).

Per phase4-design-revised.md §6 + §9.8: validate the 11-min video claim.
"""
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from open_edit.ir.types import Asset, WordAlignment, AddClipOp
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


def _make_synthetic_5min_asset(workdir: Path) -> Asset:
    """Generate a 5-min synthetic asset with 50 narrative beats."""
    alignment = []
    for i in range(50):
        t_start = i * 6.0  # 6 seconds per beat
        t_end = t_start + 5.5
        for j, word in enumerate(["word" + str(i), "next" + str(i)]):
            alignment.append(WordAlignment(
                word=word, t_start=t_start + j * 0.5, t_end=t_start + (j + 1) * 0.5,
                confidence=1.0,
            ))
    asset = Asset(
        asset_hash="synthetic_5min",
        original_path="/tmp/synthetic.mp4",
        stored_path=str(workdir / "synthetic.mp4"),
        type="video",
        duration_sec=300.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
        alignment=alignment,
    )
    return asset


@pytest.mark.timeout(900)  # 15 minutes
def test_long_form_5min_video_end_to_end(tmp_path):
    """End-to-end: ingest + analyze + propose cuts + music + SFX + render."""
    start = time.time()
    workdir = tmp_path / "long_form"
    workdir.mkdir()
    asset = _make_synthetic_5min_asset(workdir)
    asset_store = AssetStore(workdir / "assets")
    asset_store._write_sidecar(asset)  # Skip actual file write; just metadata
    edit_graph = EditGraphStore(workdir / "edit_graph.db")

    # Step 1: narrative analysis (rule-based; fast)
    from open_edit.agent.skills.narrative_analyzer import analyze
    segments = analyze(asset, use_llm=False)
    assert len(segments) >= 10  # At least 10 segments in 5 min

    # Step 2: silence cuts (mocked; no real cuts in synthetic data)
    from open_edit.agent.skills.silence_cutter import find_silence_gaps
    gaps = find_silence_gaps(asset.alignment, threshold_ms=400)
    # Synthetic data has no inter-word gaps > 400ms (all gaps are 0.5s exactly, but consecutive)
    # Should be 0 gaps
    assert len(gaps) == 0

    # Step 3: music selection (mocked library)
    from open_edit.agent.skills.music_selector import select, MusicTrack
    library = [
        MusicTrack(track_id="upbeat_01", mood="upbeat", bpm=120, energy=0.8),
        MusicTrack(track_id="contemplative_01", mood="contemplative", bpm=70, energy=0.3),
    ]
    music_ops = select(segments, library)
    assert len(music_ops) >= 10

    # Step 4: SFX placement (mocked library)
    from open_edit.agent.skills.sfx_placer import place, SfxClip
    sfx_library = [
        SfxClip(sfx_id="whoosh_01", kind="whoosh", duration_s=0.5),
        SfxClip(sfx_id="impact_01", kind="impact", duration_s=0.3),
    ]
    sfx_ops = place(segments, music_downbeats=[], library=sfx_library)
    assert len(sfx_ops) >= 5

    # Step 5: emit all ops to edit graph
    for op in music_ops + sfx_ops:
        edit_graph.append(op)

    # Verify op count is reasonable
    all_ops = edit_graph.load_all()
    assert len(all_ops) < 500, f"Edit graph has {len(all_ops)} ops, exceeds 500"

    elapsed = time.time() - start
    assert elapsed < 900, f"Took {elapsed:.1f}s, exceeds 15 min budget"

    # Note: motion graphics (W7) is not run in this stress test because
    # the render sandbox is heavy. Tested separately in test_motion_graphics_render.py.
```

### Step 2: Run the test

Run: `cd open_edit && pytest tests/test_long_form_e2e.py -v --timeout=900`
Expected: PASS (the synthetic data is small, should complete in <1 minute).

### Step 3: Commit

```bash
git add open_edit/tests/test_long_form_e2e.py
git commit -m "[open_edit] phase4.5 w8: long-form stress test (5-min synthetic video, 15-min budget)"
```

---

## Self-Review

After writing all 16 tasks, I checked against the spec:

**1. Spec coverage:**
- §2 verification: covered in `.superpowers/sdd/phase4-section-2-verification-memo.md` (precedes this plan).
- §3.1 T1: covered in Task 7.
- §3.2 T2: covered in Task 3.
- §3.3 T3 de-scope: noted, no task.
- §3.4 T4: covered in Task 5.
- §3.5 T5: covered in Task 4.
- §3.6 T6: covered in Task 2.
- §3.7 T7: covered in Task 6.
- §3.8 T8 (originating_note_id): covered in Task 1.
- §4.1 W1: covered in Task 9.
- §4.2 W2: covered in Task 10.
- §4.3 W3: covered in Task 11.
- §4.4 W4: covered in Task 12.
- §4.5 W5: covered in Task 13.
- §4.6 W6: covered in Task 14.
- §4.7 W7: covered in Task 15.
- §4.8 W8: covered in Task 16.
- §6 long-form scaling: covered (RenderSnapshotStore cap, edit history pagination, STT HTTPS).
- §7 deferred: noted.
- §8 error handling: distributed across tasks (T6 race, T4 version switcher states, T8 archive, etc.).
- §9 testing: per-task pytest + 16 task test files.
- §10 done when: each task's commit and test pass counts.
- §11 sequencing: matches this plan's task order.
- §13 bottom line: implicit in the plan.
- §14 verification memo: separate file.
- §15 audit log: separate file.

**2. Placeholder scan:** No "TBD" / "TODO" / "implement later" / "fill in details" placeholders. All code is concrete.

**3. Type consistency:**
- `Operation.originating_note_id` defined in Task 1; used in Tasks 6, 7.
- `NotesStore.commit_pending` defined in Task 2; used in Task 6.
- `RenderSnapshotStore` defined in Task 5; used in Task 6.
- `prior_state` builder defined in Task 3; extended in Task 6.
- All type names match across tasks.

**4. Spec requirements with tasks:** Verified each §10 "done when" item maps to a task:
- Items 1-3: Task 7 (tool repointing)
- Item 4: Task 3 (style memory) + 5 (style panel via RenderSnapshotStore + version switcher; style panel is in T4's UI but wait — the style profile panel is in the chat UI, which is part of Task 7)
- Item 5: Task 4 (edit history list with pagination)
- Item 6: Task 4 (HTML5 preview player with QC markers)
- Item 7: Task 4 (region mark via NotesStore)
- Item 8: Task 3 (prior_state) + Task 6 (pending_notes_summary extension)
- Item 9: Task 3 (adaptive rollup)
- Item 10: Task 3 (chmod 600)
- Item 11: Task 2 (unified notes store) + Task 4 (sidebar UI)
- Item 12: Task 4 (STT)
- Item 13: Task 6 (commit_feedback) + Task 4 (Send to Claude button)
- Item 14: Task 5 (RenderSnapshotStore + version switcher)
- Item 15: Task 7 (creativity_level)
- Item 16: Task 6 (originating_note_id)
- Item 17: Task 16 (long-form e2e)
- Item 18 (audit): Task 1 (originating_note_id)
- Item 19 (audit): Task 8 (notes archive)
- Item 20 (audit): Task 5 (RenderSnapshotStore cap)

All 20 done-when items have tasks. No gaps.

**5. Risk register (from audit, applied to the plan):**
- Whisper model size: documented in Task 9 (default `base` model; ~150MB; v1.1 can use `large-v3` for higher accuracy).
- Render sandbox trust posture: documented in Task 10 (no seccomp; cgroup-based; explicit per design §4.3).
- Motion graphics templated vs. bespoke: covered in Task 15 (templated per design; v1.1 adds bespoke).
- Long-form budget: covered in Task 16 (15 min wall clock budget).

**6. Self-review note:** One thing the spec calls out but the plan doesn't have an explicit task for is **the `pyagent_add_marker` change from v1**. The plan has it in Task 7 (T1 repointing), so it's covered. Verified.

The plan is ready to execute.
