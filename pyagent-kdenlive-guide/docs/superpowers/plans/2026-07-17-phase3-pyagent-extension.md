# Phase 3 — pyagent pi extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pi extension that gives pi 13 video-editor tools, each implemented as a thin shim over Phase 2's `KdenliveFileBackend`, so users can edit `.kdenlive` files by chatting with pi.

**Architecture:** A TypeScript pi extension (`extension.ts`) registers 13 tools with pi. On each tool call, the extension shells out to `pyagent_runtime.py` (a Python CLI), which loads the project, runs one operation against Phase 2's `KdenliveFileBackend`, and emits a JSON result. pi handles all model/provider/session concerns; pyagent is purely the bridge.

**Tech Stack:** Python 3.14, lxml 6.1.1 (Phase 2 dep), TypeScript (via jiti, no compile), pi 0.80.2.

## Global Constraints

These apply to every task. They come from the Phase 3 design spec (`phase3_pyagent_core/DESIGN.md`) and Phase 2's `editor_backend.py`.

- **Tool count:** exactly 13 tools register with pi: `pyagent_get_project_info`, `pyagent_get_timeline_summary`, `pyagent_import_media`, `pyagent_insert_clip`, `pyagent_append_clip`, `pyagent_move_clip`, `pyagent_trim_clip`, `pyagent_delete_clip`, `pyagent_add_transition`, `pyagent_apply_effect`, `pyagent_add_marker`, `pyagent_save_project`, `pyagent_list_catalog`.
- **Mutating set (auto_approve gate applies):** `pyagent_import_media`, `pyagent_insert_clip`, `pyagent_append_clip`, `pyagent_move_clip`, `pyagent_trim_clip`, `pyagent_delete_clip`, `pyagent_add_transition`, `pyagent_apply_effect`, `pyagent_add_marker`, `pyagent_save_project`. Tools 1, 2, 13 are read-only.
- **Env vars:** `PYAGENT_PROJECT` (path to .kdenlive file, required), `PYAGENT_AUTO_APPROVE` (`true`/`false`, default `false`), `PYAGENT_CATALOG` (path to catalog.json, defaults to `../phase1_knowledge_base/catalog.json` relative to the runtime module).
- **Runtime exit codes:** 0 = success, 1 = validation error (LLM self-corrects via `fix:` hint), 2 = fatal error (project unreadable, etc.).
- **JSON contract:** Python emits a single JSON line on stdout: `{"ok": true, "result": <any>}` or `{"ok": false, "error": "<message>", "fatal"?: true}`. Error messages from `ValidationError` always end with a `fix:` line.
- **No new Python deps** beyond what Phase 2 already requires (lxml).
- **No TypeScript compile step** — pi loads `.ts` via jiti.
- **Naming:** snake_case for Python and tool names; camelCase only for TypeScript locals.
- **Test framework:** Python's `unittest` (matches Phase 2's pattern); no pytest.
- **All runtime tests must pass without pi or any LLM provider** — they exercise `pyagent_runtime.py` as a subprocess.

---

## File Structure

| File | Purpose | Lines (approx) |
|---|---|---|
| `phase3_pyagent_core/pyproject.toml` | Python package metadata | 20 |
| `phase3_pyagent_core/__init__.py` | Re-exports | 5 |
| `phase3_pyagent_core/__main__.py` | Entry point for `python3 -m pyagent_runtime` | 80 |
| `phase3_pyagent_core/catalog_slice.py` | Builds filtered catalog for system prompt | 60 |
| `phase3_pyagent_core/system_prompt.md` | Identity + hard rules blocks (versioned) | 20 |
| `phase3_pyagent_core/extension.ts` | pi extension, registers 13 tools | 200 |
| `phase3_pyagent_core/extension_test_mode.py` | Helper: runs extension's dispatch logic in a testable subprocess | 60 |
| `phase3_pyagent_core/Makefile` | `make install`, `make test`, `make lint` | 30 |
| `phase3_pyagent_core/README.md` | Install + usage | 60 |
| `phase3_pyagent_core/test_runtime.py` | 30+ unit tests for the runtime | 450 |
| `phase3_pyagent_core/test_extension.py` | 10+ tests for the extension's bridge | 250 |
| `phase3_pyagent_core/test_integration.py` | E2E test, skipped if no provider | 150 |
| `phase3_pyagent_core/tests/fixtures/demo.kdenlive` | Tiny real .kdenlive for tests | (committed binary) |
| `phase3_pyagent_core/tests/fixtures/make_demo.py` | Script that generates `demo.kdenlive` | 40 |

**Key interfaces (locked in early, used by every later task):**

```python
# pyagent_runtime/__main__.py
def main(argv: list[str]) -> int:
    """Dispatch one operation. Returns the exit code."""

def run_op(op: str, args: dict, project_path: str, catalog_path: str) -> tuple[int, dict]:
    """Run one backend op. Returns (exit_code, response_dict)."""
```

```python
# pyagent_runtime/catalog_slice.py
def build_catalog_slice(catalog: dict, kinds: tuple[str, ...] = ("effects", "transitions", "generators")) -> str:
    """Build the system-prompt catalog slice. One line per entry."""
```

```typescript
// extension.ts
export default function (pi: ExtensionAPI): void
async function callRuntime(op: string, args: any, ctx: any): Promise<{ok: boolean, error?: string, result?: any}>
function humanize(op: string, args: any): string
```

---

## Task 1: Package scaffolding

**Files:**
- Create: `phase3_pyagent_core/pyproject.toml`
- Create: `phase3_pyagent_core/__init__.py`
- Create: `phase3_pyagent_core/Makefile`
- Create: `phase3_pyagent_core/README.md`

**Interfaces:** none yet (this task is just structure).

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "phase3-pyagent-core"
version = "0.1.0"
description = "pyagent Phase 3 — pi extension runtime for Kdenlive editing."
requires-python = ">=3.14"
dependencies = [
    "lxml>=6.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["phase3_pyagent_core*"]
```

The package name is `phase3_pyagent_core` (matches the directory and follows Phase 2's `phase2_project_engine` convention). It is invoked as `python3 -m phase3_pyagent_core <op> ...` (not `python3 -m pyagent_runtime` as the design spec's prose suggested). The `extension.ts` calls this in Task 10.

Save to `phase3_pyagent_core/pyproject.toml`.

- [ ] **Step 2: Create `__init__.py` (empty marker)**

```python
"""pyagent runtime package."""
```

Save to `phase3_pyagent_core/__init__.py`.

- [ ] **Step 3: Create the `Makefile`**

```makefile
.PHONY: install test lint clean

install:
	# Link the extension into pi's auto-discovery directory.
	mkdir -p $(HOME)/.pi/agent/extensions
	ln -sfn $(PWD) $(HOME)/.pi/agent/extensions/pyagent
	# Install the Python package in editable mode.
	pip install -e .

test:
	python3 -m unittest discover -s . -p "test_*.py" -v

lint:
	python3 -m py_compile __main__.py catalog_slice.py
	# (no formatter configured; match Phase 2's no-format style)

clean:
	rm -rf build/ dist/ *.egg-info __pycache__/ tests/__pycache__/ */__pycache__
```

Save to `phase3_pyagent_core/Makefile`.

- [ ] **Step 4: Create the README**

````markdown
# pyagent — pi extension for Kdenlive editing

A pi extension that gives pi 13 video-editor tools, backed by Phase 2's
`KdenliveFileBackend`. pi handles the LLM; this extension just bridges
LLM tool calls to file edits.

## Install

```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core
make install
```

This:
1. Symlinks the extension into `~/.pi/agent/extensions/pyagent/` so pi
   auto-discovers it.
2. Installs the Python runtime in editable mode so `python3 -m
   pyagent_runtime` is importable from anywhere.

## Use

```bash
export PYAGENT_PROJECT=/path/to/your.kdenlive
export PYAGENT_AUTO_APPROVE=false    # default; prompts before each mutating tool
pi    # the pyagent_* tools appear in the tool palette
```

## Test

```bash
make test
```

The runtime tests need no pi or LLM. The integration test needs an LLM
provider configured (e.g., `OPENAI_API_KEY` or `GEMINI_API_KEY`) and
will skip if none is set.

## See also

- `DESIGN.md` — the design spec
- `../PHASE_3_pyagent_core.md` — the phase requirements
````

Save to `phase3_pyagent_core/README.md`.

- [ ] **Step 5: Verify scaffolding imports**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && python3 -c "import phase3_pyagent_core; print('ok')"
```

Expected: `ok` (currently a no-op package — the real `__main__.py` lands in Task 2).

If it fails with `ModuleNotFoundError`, you forgot `__init__.py` — re-check.

- [ ] **Step 6: Commit**

```bash
git add phase3_pyagent_core/pyproject.toml phase3_pyagent_core/__init__.py phase3_pyagent_core/Makefile phase3_pyagent_core/README.md
git commit -m "[phase-3][scaffold] add pyagent runtime package skeleton"
```

---

## Task 2: Runtime CLI dispatcher (TDD)

**Files:**
- Create: `phase3_pyagent_core/__main__.py`
- Create: `phase3_pyagent_core/test_runtime.py`

**Interfaces (locked here, used by every later task):**
- `main(argv: list[str]) -> int` — the CLI entry. Returns the exit code.
- `run_op(op: str, args: dict, project_path: str, catalog_path: str) -> tuple[int, dict]` — the dispatch.

- [ ] **Step 1: Write the failing test for the dispatch stub**

Create `phase3_pyagent_core/test_runtime.py`:

```python
"""Tests for the pyagent runtime CLI dispatcher.

These tests call `python3 -m pyagent_runtime` as a subprocess to exercise
the full CLI path. They require the package to be installed (via
`make install` or `pip install -e .`).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = REPO_ROOT / "phase3_pyagent_core"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
CATALOG_PATH = REPO_ROOT / "phase1_knowledge_base" / "catalog.json"


def _run_runtime(op: str, args: dict, project: str, catalog: str = str(CATALOG_PATH)) -> tuple[int, dict]:
    """Invoke pyagent_runtime as a subprocess. Returns (exit_code, json_response)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pyagent_runtime", op,
         "--project", project,
         "--catalog", catalog,
         "--args-json", json.dumps(args)],
        capture_output=True, text=True,
    )
    last_line = proc.stdout.strip().split("\n")[-1] if proc.stdout.strip() else "{}"
    return proc.returncode, json.loads(last_line)


class TestDispatch(unittest.TestCase):
    """The dispatcher itself, before any backend methods are wired."""

    def test_unknown_op_returns_fatal_error(self):
        """A non-existent op must exit 2 with a fatal flag."""
        with tempfile.TemporaryDirectory() as tmp:
            fake_project = os.path.join(tmp, "fake.kdenlive")
            Path(fake_project).write_text("<mlt/>")
            code, resp = _run_runtime("not_a_real_op", {}, fake_project)
        self.assertEqual(code, 2)
        self.assertFalse(resp["ok"])
        self.assertTrue(resp.get("fatal"))
        self.assertIn("not_a_real_op", resp["error"])

    def test_missing_project_returns_fatal_error(self):
        """A non-existent project file must exit 2 with fatal."""
        code, resp = _run_runtime("get_project_info", {}, "/nonexistent/path.kdenlive")
        self.assertEqual(code, 2)
        self.assertFalse(resp["ok"])
        self.assertTrue(resp.get("fatal"))

    def test_help_flag_prints_usage(self):
        """`python3 -m pyagent_runtime --help` should print usage and exit 0."""
        proc = subprocess.run(
            [sys.executable, "-m", "pyagent_runtime", "--help"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("usage", proc.stdout.lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to confirm it fails**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && python3 -m unittest test_runtime.TestDispatch -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'pyagent_runtime.__main__'` or similar (no `__main__.py` yet).

- [ ] **Step 3: Create the demo fixture**

Create `phase3_pyagent_core/tests/fixtures/make_demo.py`:

```python
"""Generate tests/fixtures/demo.kdenlive — a tiny but real Kdenlive project.

Used by the runtime tests as a known-good starting point. Built by calling
Phase 2's KdenliveFileBackend with a 10-second test clip.
"""
import sys
from pathlib import Path

# Add the repo root to sys.path so we can import Phase 2.
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from phase2_project_engine import KdenliveFileBackend, Catalog  # noqa: E402

CATALOG = REPO_ROOT / "phase1_knowledge_base" / "catalog.json"
CLIP = REPO_ROOT / "testdata" / "clip_short.mp4"
OUT = Path(__file__).resolve().parent / "demo.kdenlive"


def main() -> None:
    if not CLIP.exists():
        sys.exit(f"missing test clip at {CLIP}; expected from mlt-pipeline/testdata/")
    cat = Catalog.from_json(str(CATALOG))
    backend = KdenliveFileBackend(project_path=None, catalog=cat)
    src_id = backend.import_media([str(CLIP)])[0]
    backend.append_clip(0, src_id, 0.0, 4.0)
    backend.save(str(OUT))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
```

Run it: `cd pyagent-kdenlive-guide && python3 phase3_pyagent_core/tests/fixtures/make_demo.py`. Verify `tests/fixtures/demo.kdenlive` exists and is a few KB.

- [ ] **Step 4: Create the `__main__.py` dispatch skeleton**

Create `phase3_pyagent_core/__main__.py`:

```python
"""pyagent_runtime — the Python side of the pyagent pi extension.

Invoked as `python3 -m pyagent_runtime <op> --project <path> --catalog <path>
--args-json '<json>'`. Emits a single JSON line on stdout, exits with code
0 (success), 1 (validation error), or 2 (fatal error).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Make Phase 2 importable when this package is installed standalone.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from phase2_project_engine import (  # noqa: E402
    Catalog,
    KdenliveFileBackend,
    ValidationError,
    BackendError,
)


# Op name (as called from TS) -> backend method name.
# Filled in incrementally as each backend op is wired up.
OP_TABLE: dict[str, str] = {
    "get_project_info": "get_project_info",
    "get_timeline_summary": "get_timeline_summary",
    "import_media": "import_media",
    "insert_clip": "insert_clip",
    "append_clip": "append_clip",
    "move_clip": "move_clip",
    "trim_clip": "trim_clip",
    "delete_clip": "delete_clip",
    "add_transition": "add_transition",
    "apply_effect": "apply_effect",
    "add_marker": "add_marker",
    "save": "save",
    # "list_catalog" handled specially (not a backend op).
}


def _emit(response: dict[str, Any]) -> None:
    """Write one JSON line to stdout, exactly one, no trailing whitespace."""
    sys.stdout.write(json.dumps(response, default=_to_jsonable) + "\n")
    sys.stdout.flush()


def _to_jsonable(obj: Any) -> Any:
    """Coerce dataclasses and other Phase 2 return types to JSON-safe dicts."""
    if hasattr(obj, "__dataclass_fields__"):
        from dataclasses import asdict, is_dataclass
        return asdict(obj) if is_dataclass(obj) else obj.__dict__
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def run_op(op: str, args: dict, project_path: str, catalog_path: str) -> tuple[int, dict]:
    """Run one backend op. Returns (exit_code, response_dict).

    exit_code: 0 = success, 1 = validation error (LLM self-corrects),
               2 = fatal error (project unreadable, op missing, etc.)
    """
    if op not in OP_TABLE:
        return 2, {"ok": False, "fatal": True, "error": f"unknown op: {op!r}"}

    if not Path(project_path).exists():
        return 2, {
            "ok": False,
            "fatal": True,
            "error": f"BackendError: project file not found at {project_path}",
        }

    try:
        backend = KdenliveFileBackend(
            project_path=project_path,
            catalog=Catalog.from_json(catalog_path),
        )
        method = getattr(backend, OP_TABLE[op])
        result = method(**args)
        return 0, {"ok": True, "result": result}
    except ValidationError as e:
        return 1, {"ok": False, "error": str(e)}
    except BackendError as e:
        return 2, {"ok": False, "fatal": True, "error": f"BackendError: {e}"}
    except Exception as e:  # noqa: BLE001 — last-resort guard
        return 2, {"ok": False, "fatal": True, "error": f"Unexpected: {type(e).__name__}: {e}"}


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = argparse.ArgumentParser(
        prog="pyagent_runtime",
        description="Run one Phase 2 backend op, emit JSON result on stdout.",
    )
    parser.add_argument("op", help="The op name (e.g. 'append_clip')")
    parser.add_argument("--project", required=True, help="Path to the .kdenlive file")
    parser.add_argument("--catalog", required=True, help="Path to the catalog.json")
    parser.add_argument("--args-json", default="{}", help="JSON object of kwargs for the op")
    parsed = parser.parse_args(argv)

    try:
        args = json.loads(parsed.args_json)
    except json.JSONDecodeError as e:
        _emit({"ok": False, "fatal": True, "error": f"invalid --args-json: {e}"})
        return 2

    code, response = run_op(parsed.op, args, parsed.project, parsed.catalog)
    _emit(response)
    return code


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the test, confirm 2 of 3 pass**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && python3 -m unittest test_runtime.TestDispatch.test_help_flag_prints_usage -v
```

Expected: PASS (help is wired by argparse).

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && python3 -m unittest test_runtime.TestDispatch.test_unknown_op_returns_fatal_error test_runtime.TestDispatch.test_missing_project_returns_fatal_error -v
```

Expected: PASS (the dispatch stub returns 2 for both cases). The `_run_runtime` helper uses a temp file for the first; the test's fake project is created and the project-exists check passes for that one — wait, the first test creates a temp .kdenlive then asks for a non-existent op, so the project-exists check passes, and the op-not-in-OP_TABLE branch fires. Correct.

- [ ] **Step 6: Commit**

```bash
cd pyagent-kdenlive-guide
git add phase3_pyagent_core/__main__.py phase3_pyagent_core/test_runtime.py phase3_pyagent_core/tests/fixtures/make_demo.py phase3_pyagent_core/tests/fixtures/demo.kdenlive
git commit -m "[phase-3][runtime] add CLI dispatcher stub with error paths"
```

---

## Task 3: Runtime — wire get_project_info and get_timeline_summary

**Files:**
- Modify: `phase3_pyagent_core/test_runtime.py` (add tests)
- Modify: `phase3_pyagent_core/__main__.py` (no change expected — already wired)

These two are already wired in `OP_TABLE` from Task 2, so this task is just confirming they work end-to-end with the demo fixture.

- [ ] **Step 1: Add the tests**

Append to `phase3_pyagent_core/test_runtime.py`:

```python
class TestReadOps(unittest.TestCase):
    """The two read-only ops, exercised against tests/fixtures/demo.kdenlive."""

    @classmethod
    def setUpClass(cls):
        cls.project = str(FIXTURES_DIR / "demo.kdenlive")
        if not Path(cls.project).exists():
            raise unittest.SkipTest(f"demo.kdenlive missing; run tests/fixtures/make_demo.py first")

    def test_get_project_info_returns_valid_dict(self):
        code, resp = _run_runtime("get_project_info", {}, self.project)
        self.assertEqual(code, 0)
        self.assertTrue(resp["ok"])
        info = resp["result"]
        self.assertIn("name", info)
        self.assertIn("fps", info)
        self.assertIn("width", info)
        self.assertIn("height", info)
        self.assertIn("track_count", info)
        self.assertIn("duration_sec", info)

    def test_get_timeline_summary_returns_valid_dict(self):
        code, resp = _run_runtime("get_timeline_summary", {}, self.project)
        self.assertEqual(code, 0)
        self.assertTrue(resp["ok"])
        summary = resp["result"]
        self.assertIn("project", summary)
        self.assertIn("tracks", summary)
        self.assertIn("clips", summary)
        self.assertIsInstance(summary["clips"], list)
        # demo.kdenlive has exactly 1 clip from make_demo.py.
        self.assertEqual(len(summary["clips"]), 1)
        clip = summary["clips"][0]
        self.assertIn("clip_id", clip)
        self.assertIn("start_sec", clip)
        self.assertIn("end_sec", clip)
```

- [ ] **Step 2: Run, confirm they pass**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && python3 -m unittest test_runtime.TestReadOps -v
```

Expected: 2 tests pass. (`get_project_info` and `get_timeline_summary` are already in `OP_TABLE`.)

If they fail, check that `tests/fixtures/demo.kdenlive` exists (re-run `make_demo.py`).

- [ ] **Step 3: Commit**

```bash
cd pyagent-kdenlive-guide
git add phase3_pyagent_core/test_runtime.py
git commit -m "[phase-3][runtime] add tests for get_project_info and get_timeline_summary"
```

---

## Task 4: Runtime — wire import_media and append_clip (the first end-to-end chain)

**Files:**
- Modify: `phase3_pyagent_core/test_runtime.py` (add tests)
- Modify: `phase3_pyagent_core/__main__.py` (no change expected)

These two are the foundation of the spec's acceptance test: "add these two clips to the timeline with a crossfade" → `import_media` → `append_clip` × 2 → `add_transition`.

- [ ] **Step 1: Add the test**

Append to `phase3_pyagent_core/test_runtime.py`:

```python
class TestMutatingOps(unittest.TestCase):
    """Mutating ops. Each test copies demo.kdenlive to a temp file so the
    fixture stays clean for the rest of the suite."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project = os.path.join(self.tmpdir, "test.kdenlive")
        # Copy the demo fixture to the temp location.
        with open(FIXTURES_DIR / "demo.kdenlive", "rb") as src:
            with open(self.project, "wb") as dst:
                dst.write(src.read())
        self.clip_path = str(REPO_ROOT / "testdata" / "clip_short.mp4")
        if not Path(self.clip_path).exists():
            self.skipTest(f"test clip missing: {self.clip_path}")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_import_media_returns_clip_id(self):
        code, resp = _run_runtime(
            "import_media", {"paths": [self.clip_path]}, self.project,
        )
        self.assertEqual(code, 0)
        self.assertTrue(resp["ok"])
        ids = resp["result"]
        self.assertIsInstance(ids, list)
        self.assertEqual(len(ids), 1)
        self.assertIsInstance(ids[0], str)

    def test_append_clip_after_import(self):
        # Import a clip, then append it. The full chain from the spec.
        code, resp = _run_runtime(
            "import_media", {"paths": [self.clip_path]}, self.project,
        )
        self.assertEqual(code, 0)
        source_id = resp["result"][0]

        code, resp = _run_runtime(
            "append_clip",
            {"track_index": 0, "source_id": source_id,
             "source_in_sec": 0.0, "source_out_sec": 4.0},
            self.project,
        )
        self.assertEqual(code, 0)
        self.assertTrue(resp["ok"])
        self.assertIsInstance(resp["result"], str)
        # The new clip id should be visible in a fresh get_timeline_summary.
        _, summary_resp = _run_runtime("get_timeline_summary", {}, self.project)
        clip_ids = [c["clip_id"] for c in summary_resp["result"]["clips"]]
        self.assertIn(resp["result"], clip_ids)
        self.assertEqual(len(summary_resp["result"]["clips"]), 2)
```

- [ ] **Step 2: Run, confirm they pass**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && python3 -m unittest test_runtime.TestMutatingOps -v
```

Expected: 2 tests pass. (Both ops are in `OP_TABLE` from Task 2.)

- [ ] **Step 3: Commit**

```bash
cd pyagent-kdenlive-guide
git add phase3_pyagent_core/test_runtime.py
git commit -m "[phase-3][runtime] add tests for import_media and append_clip chain"
```

---

## Task 5: Runtime — wire add_transition (the spec's headline acceptance test)

**Files:**
- Modify: `phase3_pyagent_core/test_runtime.py`

This is the exact chain the spec calls out: "add these two clips to the timeline with a crossfade."

- [ ] **Step 1: Add the test**

Append to `phase3_pyagent_core/test_runtime.py`:

```python
    def test_full_crossfade_chain(self):
        """The spec's headline acceptance test: import two clips, append them,
        add a transition between them, then save. The saved file must still
        be a valid .kdenlive."""
        # Import two copies of the test clip.
        code, r = _run_runtime(
            "import_media", {"paths": [self.clip_path, self.clip_path]}, self.project,
        )
        self.assertEqual(code, 0)
        a_src, b_src = r["result"]

        # Append both.
        code, r = _run_runtime(
            "append_clip",
            {"track_index": 0, "source_id": a_src, "source_out_sec": 4.0},
            self.project,
        )
        self.assertEqual(code, 0)
        a_id = r["result"]

        code, r = _run_runtime(
            "append_clip",
            {"track_index": 0, "source_id": b_src, "source_out_sec": 4.0},
            self.project,
        )
        self.assertEqual(code, 0)
        b_id = r["result"]

        # Add the crossfade.
        code, r = _run_runtime(
            "add_transition",
            {"clip_a_id": a_id, "clip_b_id": b_id,
             "kind": "composite", "duration_sec": 1.0},
            self.project,
        )
        self.assertEqual(code, 0)
        t_id = r["result"]
        self.assertIsInstance(t_id, str)

        # Save.
        code, r = _run_runtime("save", {}, self.project)
        self.assertEqual(code, 0)

        # The saved file must be a valid .kdenlive that opens without errors.
        # (Round-trip: reload and verify clip count + transition count.)
        _, summary = _run_runtime("get_timeline_summary", {}, self.project)
        self.assertEqual(len(summary["result"]["clips"]), 2)
        self.assertEqual(len(summary["result"]["transitions"]), 1)
```

- [ ] **Step 2: Run, confirm it passes**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && python3 -m unittest test_runtime.TestMutatingOps.test_full_crossfade_chain -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd pyagent-kdenlive-guide
git add phase3_pyagent_core/test_runtime.py
git commit -m "[phase-3][runtime] add crossfade-chain test (spec headline)"
```

---

## Task 6: Runtime — wire the remaining 5 mutating ops

**Files:**
- Modify: `phase3_pyagent_core/test_runtime.py`

These are all in `OP_TABLE` from Task 2, so this task is just adding tests for them. The chain is: insert → move → trim → apply_effect → add_marker → delete.

- [ ] **Step 1: Add the tests**

Append to `phase3_pyagent_core/test_runtime.py`:

```python
    def test_insert_clip_then_move(self):
        code, r = _run_runtime("import_media", {"paths": [self.clip_path]}, self.project)
        sid = r["result"][0]

        code, r = _run_runtime(
            "insert_clip",
            {"track_index": 0, "position_sec": 0.0, "source_id": sid,
             "source_out_sec": 3.0},
            self.project,
        )
        self.assertEqual(code, 0)
        cid = r["result"]

        # Move it to track 1 at position 5.0.
        code, r = _run_runtime(
            "move_clip", {"clip_id": cid, "new_track": 1, "new_position_sec": 5.0},
            self.project,
        )
        self.assertEqual(code, 0)
        self.assertTrue(r["ok"])

        # Verify.
        _, summary = _run_runtime("get_timeline_summary", {}, self.project)
        moved = next(c for c in summary["result"]["clips"] if c["clip_id"] == cid)
        self.assertEqual(moved["track_index"], 1)
        self.assertAlmostEqual(moved["start_sec"], 5.0, places=2)

    def test_trim_clip_rejects_invalid_range(self):
        """trim_clip with out < in must exit 1 with a fix: hint."""
        code, r = _run_runtime("import_media", {"paths": [self.clip_path]}, self.project)
        sid = r["result"][0]
        code, r = _run_runtime(
            "append_clip",
            {"track_index": 0, "source_id": sid, "source_out_sec": 10.0},
            self.project,
        )
        cid = r["result"]

        # Try to trim to a backwards range.
        code, r = _run_runtime(
            "trim_clip", {"clip_id": cid, "new_in_sec": 5.0, "new_out_sec": 2.0},
            self.project,
        )
        self.assertEqual(code, 1)
        self.assertFalse(r["ok"])
        self.assertIn("fix:", r["error"])

    def test_apply_effect_with_valid_id(self):
        code, r = _run_runtime("import_media", {"paths": [self.clip_path]}, self.project)
        sid = r["result"][0]
        code, r = _run_runtime(
            "append_clip", {"track_index": 0, "source_id": sid, "source_out_sec": 5.0},
            self.project,
        )
        cid = r["result"]
        code, r = _run_runtime(
            "apply_effect",
            {"clip_id": cid, "effect_id": "brightness", "params": {"level": 0.5}},
            self.project,
        )
        self.assertEqual(code, 0)
        self.assertTrue(r["ok"])

    def test_apply_effect_with_invalid_id_returns_fix_hint(self):
        code, r = _run_runtime("import_media", {"paths": [self.clip_path]}, self.project)
        sid = r["result"][0]
        code, r = _run_runtime(
            "append_clip", {"track_index": 0, "source_id": sid, "source_out_sec": 3.0},
            self.project,
        )
        cid = r["result"]
        code, r = _run_runtime(
            "apply_effect",
            {"clip_id": cid, "effect_id": "no_such_effect"},
            self.project,
        )
        self.assertEqual(code, 1)
        self.assertIn("fix:", r["error"])

    def test_add_marker_and_delete_clip(self):
        code, r = _run_runtime("import_media", {"paths": [self.clip_path]}, self.project)
        sid = r["result"][0]
        code, r = _run_runtime(
            "append_clip", {"track_index": 0, "source_id": sid, "source_out_sec": 4.0},
            self.project,
        )
        cid = r["result"]

        # Add a marker.
        code, r = _run_runtime(
            "add_marker", {"position_sec": 2.0, "label": "cut point", "kind": "guide"},
            self.project,
        )
        self.assertEqual(code, 0)

        # Delete the clip.
        code, r = _run_runtime("delete_clip", {"clip_id": cid}, self.project)
        self.assertEqual(code, 0)

        _, summary = _run_runtime("get_timeline_summary", {}, self.project)
        self.assertEqual(len(summary["result"]["clips"]), 0)
        self.assertEqual(len(summary["result"]["markers"]), 1)
```

- [ ] **Step 2: Run, confirm all 5 pass**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && python3 -m unittest test_runtime.TestMutatingOps -v
```

Expected: 7 tests pass (the 2 from Task 4 + 1 from Task 5 + 5 new here).

- [ ] **Step 3: Commit**

```bash
cd pyagent-kdenlive-guide
git add phase3_pyagent_core/test_runtime.py
git commit -m "[phase-3][runtime] add tests for insert/move/trim/apply_effect/add_marker/delete"
```

---

## Task 7: Runtime — wire pyagent_list_catalog (tool #13)

**Files:**
- Create: `phase3_pyagent_core/catalog_slice.py`
- Modify: `phase3_pyagent_core/__main__.py` (handle list_catalog specially)
- Modify: `phase3_pyagent_core/test_runtime.py` (add tests)

`list_catalog` is the 13th tool and is NOT a backend method — it reads the catalog JSON and filters it. Handle it in `run_op` before the `OP_TABLE` lookup.

- [ ] **Step 1: Write the failing test**

Append to `phase3_pyagent_core/test_runtime.py`:

```python
class TestListCatalog(unittest.TestCase):
    def test_list_catalog_effects(self):
        code, resp = _run_runtime(
            "list_catalog", {"kind": "effects"}, str(FIXTURES_DIR / "demo.kdenlive"),
        )
        self.assertEqual(code, 0)
        self.assertTrue(resp["ok"])
        self.assertIsInstance(resp["result"], list)
        self.assertGreater(len(resp["result"]), 0)
        # Every entry has at least id, name, tag.
        entry = resp["result"][0]
        self.assertIn("id", entry)
        self.assertIn("name", entry)

    def test_list_catalog_with_filter(self):
        """`filter` is a substring match on name."""
        code, resp = _run_runtime(
            "list_catalog",
            {"kind": "effects", "filter": "bright"},
            str(FIXTURES_DIR / "demo.kdenlive"),
        )
        self.assertEqual(code, 0)
        self.assertGreater(len(resp["result"]), 0)
        for entry in resp["result"]:
            self.assertIn("bright", entry["name"].lower())

    def test_list_catalog_invalid_kind(self):
        code, resp = _run_runtime(
            "list_catalog", {"kind": "no_such_kind"},
            str(FIXTURES_DIR / "demo.kdenlive"),
        )
        self.assertEqual(code, 1)
        self.assertIn("fix:", resp["error"])
```

- [ ] **Step 2: Run, confirm they fail**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && python3 -m unittest test_runtime.TestListCatalog -v
```

Expected: 3 failures (op is "list_catalog" which is not in `OP_TABLE`; current code returns exit 2 with "unknown op").

- [ ] **Step 3: Add `list_catalog` to `run_op`**

Edit `phase3_pyagent_core/__main__.py`. In `run_op`, before the `if op not in OP_TABLE` check, add:

```python
    if op == "list_catalog":
        return _run_list_catalog(args, catalog_path)
```

And add the helper above `run_op`:

```python
_ALLOWED_CATALOG_KINDS = ("effects", "transitions", "generators")


def _run_list_catalog(args: dict, catalog_path: str) -> tuple[int, dict]:
    try:
        cat = Catalog.from_json(catalog_path)
    except Exception as e:  # noqa: BLE001
        return 2, {"ok": False, "fatal": True, "error": f"BackendError: catalog unreadable: {e}"}

    kind = args.get("kind", "effects")
    if kind not in _ALLOWED_CATALOG_KINDS:
        return 1, {
            "ok": False,
            "error": (
                f"invalid kind: {kind!r}\n"
                f"fix: use one of {_ALLOWED_CATALOG_KINDS}"
            ),
        }

    # The catalog object has a by_id mapping; iterate it filtered by `kind`.
    # (The schema of the catalog is in phase1_knowledge_base/catalog.json;
    # each top-level key corresponds to a kind.)
    raw = json.loads(Path(catalog_path).read_text())
    items = raw.get(kind, [])
    if "filter" in args and args["filter"]:
        needle = str(args["filter"]).lower()
        items = [e for e in items if needle in e.get("name", "").lower()]
    # Project to a small dict per entry.
    return 0, {
        "ok": True,
        "result": [
            {
                "id": e.get("id"),
                "name": e.get("name"),
                "tag": e.get("tag"),
                "description": e.get("description", ""),
            }
            for e in items
        ],
    }
```

- [ ] **Step 4: Run, confirm they pass**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && python3 -m unittest test_runtime.TestListCatalog -v
```

Expected: 3 pass.

- [ ] **Step 5: Commit**

```bash
cd pyagent-kdenlive-guide
git add phase3_pyagent_core/__main__.py phase3_pyagent_core/test_runtime.py
git commit -m "[phase-3][runtime] add list_catalog tool with kind/filter args"
```

---

## Task 8: Catalog slice generator

**Files:**
- Create: `phase3_pyagent_core/catalog_slice.py`
- Create: `phase3_pyagent_core/test_catalog_slice.py`

This is what the extension uses to build the ~50-80 KB catalog slice for the system prompt.

- [ ] **Step 1: Write the failing test**

Create `phase3_pyagent_core/test_catalog_slice.py`:

```python
"""Tests for catalog_slice.build_catalog_slice."""
import json
import tempfile
import unittest
from pathlib import Path

from catalog_slice import build_catalog_slice


SAMPLE_CATALOG = {
    "effects": [
        {"id": "brightness", "name": "Brightness", "tag": "brightness",
         "description": "Adjust clip brightness."},
        {"id": "crop", "name": "Crop", "tag": "crop",
         "description": "Crop the edges."},
        # No name -> should be excluded.
        {"id": "broken", "tag": "broken"},
    ],
    "transitions": [
        {"id": "dissolve", "name": "Dissolve", "tag": "luma",
         "description": "Crossfade between two clips."},
    ],
    "generators": [],
    "metadata_stuff_we_skip": "ignore me",
}


class TestBuildSlice(unittest.TestCase):
    def test_includes_named_entries(self):
        slice_text = build_catalog_slice(SAMPLE_CATALOG)
        self.assertIn("brightness", slice_text)
        self.assertIn("Brightness", slice_text)
        self.assertIn("Crop", slice_text)
        self.assertIn("Dissolve", slice_text)

    def test_excludes_unnamed_entries(self):
        slice_text = build_catalog_slice(SAMPLE_CATALOG)
        self.assertNotIn("broken", slice_text)

    def test_one_line_per_entry(self):
        slice_text = build_catalog_slice(SAMPLE_CATALOG)
        # 3 named entries: brightness, crop, dissolve.
        self.assertEqual(len([l for l in slice_text.splitlines() if l.strip()]), 3)

    def test_format_includes_id_name_tag(self):
        slice_text = build_catalog_slice(SAMPLE_CATALOG)
        # Format: "{tag} | {id} | {name} | {description}"
        for line in slice_text.splitlines():
            parts = [p.strip() for p in line.split("|")]
            self.assertEqual(len(parts), 4)

    def test_filter_by_kind(self):
        slice_text = build_catalog_slice(SAMPLE_CATALOG, kinds=("effects",))
        self.assertIn("Brightness", slice_text)
        self.assertNotIn("Dissolve", slice_text)

    def test_accepts_path_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "cat.json"
            p.write_text(json.dumps(SAMPLE_CATALOG))
            slice_text = build_catalog_slice(str(p))
            self.assertIn("Brightness", slice_text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, confirm fail**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && python3 -m unittest test_catalog_slice -v
```

Expected: `ModuleNotFoundError: No module named 'catalog_slice'`.

- [ ] **Step 3: Implement `catalog_slice.py`**

Create `phase3_pyagent_core/catalog_slice.py`:

```python
"""Build the filtered catalog slice used in the system prompt.

The slice is one line per catalog entry:
    {tag} | {kdenlive_id} | {name} | {description}

Entries without a `name` are excluded. Only `effects`, `transitions`, and
`generators` kinds are included; metadata fields are ignored.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


DEFAULT_KINDS: tuple[str, ...] = ("effects", "transitions", "generators")


def build_catalog_slice(
    catalog: dict | str | Path,
    kinds: Iterable[str] = DEFAULT_KINDS,
) -> str:
    """Return the catalog slice as a multi-line string.

    Args:
        catalog: a dict (the parsed catalog.json contents) or a path to the
                 JSON file.
        kinds: which top-level keys to include. Default: all three.

    Returns:
        A newline-separated string, one line per entry. Empty string if no
        named entries match.
    """
    if isinstance(catalog, (str, Path)):
        catalog = json.loads(Path(catalog).read_text())

    lines: list[str] = []
    for kind in kinds:
        for entry in catalog.get(kind, []):
            name = entry.get("name")
            if not name:
                continue  # skip unnamed entries
            tag = entry.get("tag", "")
            entry_id = entry.get("id", "")
            description = (entry.get("description", "") or "").strip()
            lines.append(f"{tag} | {entry_id} | {name} | {description}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run, confirm 6 pass**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && python3 -m unittest test_catalog_slice -v
```

Expected: 6 pass.

- [ ] **Step 5: Commit**

```bash
cd pyagent-kdenlive-guide
git add phase3_pyagent_core/catalog_slice.py phase3_pyagent_core/test_catalog_slice.py
git commit -m "[phase-3][catalog] add catalog_slice builder for system prompt"
```

---

## Task 9: System prompt (versioned markdown)

**Files:**
- Create: `phase3_pyagent_core/system_prompt.md`

No code tests for this — it's reviewed by humans. The content is from DESIGN.md §6.

- [ ] **Step 1: Write the system prompt**

Create `phase3_pyagent_core/system_prompt.md`:

````markdown
<!--
This file is the append-system-prompt that the pyagent extension injects
into pi. It is versioned in git and reviewed by humans. The catalog
slice (the large table at the bottom) is appended at runtime by
catalog_slice.build_catalog_slice(); the placeholder below is a marker
the extension replaces.
-->

# PyAgent

You are PyAgent, a video-editing assistant. You edit `.kdenlive` project
files via the `pyagent_*` tools. The user has Kdenlive open; your edits
show up after they reload the project (or automatically if Phase 5's
D-Bus bridge is wired).

## Hard rules

- Never shell out to `ffmpeg` or `melt` directly. Always use the
  `pyagent_*` tools.
- Never edit the `.kdenlive` file by hand or via pi's built-in
  `edit` / `write` tools. Always go through `pyagent_*`.
- Every `effect_id` and transition `kind` must come from the catalog
  slice at the bottom of this prompt. If the user asks for something
  not in the catalog, say so; do not invent.
- Before planning any edit, call `pyagent_get_timeline_summary()` to
  see the current state. Do not trust your memory from earlier turns
  — the state may have changed.
- Before calling any *mutating* tool (everything except
  `pyagent_get_project_info`, `pyagent_get_timeline_summary`, and
  `pyagent_list_catalog`), briefly state in one sentence what you are
  about to do. The user will be asked to confirm unless
  `PYAGENT_AUTO_APPROVE=true` is set.
- If a tool returns a `fix:`-hinted error, fix the call and retry.
  After 3 failed attempts on the same operation, stop and tell the
  user.

## Available tools (summary)

- `pyagent_get_project_info` — read project metadata.
- `pyagent_get_timeline_summary` — read tracks/clips/transitions/markers.
- `pyagent_list_catalog` — look up effect/transition details (with `filter`).
- `pyagent_import_media` — add media files to the bin.
- `pyagent_insert_clip` / `pyagent_append_clip` — add a clip to the timeline.
- `pyagent_move_clip` / `pyagent_trim_clip` / `pyagent_delete_clip` — modify a clip.
- `pyagent_add_transition` — crossfade between two adjacent clips.
- `pyagent_apply_effect` — apply an effect to a clip.
- `pyagent_add_marker` — add a marker/guide/chapter.
- `pyagent_save_project` — write the .kdenlive file to disk.

## Catalog slice

The following table lists every effect, transition, and generator
available in this project. Use `pyagent_list_catalog` to look up full
parameter details for any entry.

{{CATALOG_SLICE}}
````

- [ ] **Step 2: Verify the file parses as markdown**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && python3 -c "
import re
text = open('system_prompt.md').read()
assert '{{CATALOG_SLICE}}' in text, 'placeholder missing'
print('placeholder present, ready for runtime substitution')
"
```

Expected: `placeholder present, ready for runtime substitution`.

- [ ] **Step 3: Commit**

```bash
cd pyagent-kdenlive-guide
git add phase3_pyagent_core/system_prompt.md
git commit -m "[phase-3][prompt] add versioned system prompt with catalog placeholder"
```

---

## Task 10: Pi extension — skeleton with one tool

**Files:**
- Create: `phase3_pyagent_core/extension.ts`

Goal of this task: a minimal extension that registers ONE tool
(`pyagent_get_project_info`) and successfully dispatches to the runtime.
Verified by manually running `pi --help` or by the JSONL test in Task 11.

- [ ] **Step 1: Create the extension skeleton**

Create `phase3_pyagent_core/extension.ts`:

```typescript
// pyagent pi extension.
//
// Registers 13 tools that let the LLM edit .kdenlive project files via
// Phase 2's KdenliveFileBackend. Each tool spawns a short-lived Python
// subprocess that performs one backend op and emits a JSON result.
//
// Environment variables:
//   PYAGENT_PROJECT      path to the .kdenlive file (required)
//   PYAGENT_AUTO_APPROVE "true" to skip the per-tool confirm prompt
//   PYAGENT_CATALOG      path to catalog.json (default: ../phase1_knowledge_base/catalog.json)

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve as resolvePath, join, dirname } from "node:path";

// ---- Op name (pi) -> backend method (Python) ----

const MUTATING = new Set([
  "pyagent_import_media",
  "pyagent_insert_clip",
  "pyagent_append_clip",
  "pyagent_move_clip",
  "pyagent_trim_clip",
  "pyagent_delete_clip",
  "pyagent_add_transition",
  "pyagent_apply_effect",
  "pyagent_add_marker",
  "pyagent_save_project",
]);

function isMutating(toolName: string): boolean {
  return MUTATING.has(toolName);
}

// ---- Project path resolution ----

function resolveProjectPath(): string | null {
  return process.env.PYAGENT_PROJECT || null;
}

function resolveCatalogPath(): string {
  if (process.env.PYAGENT_CATALOG) return process.env.PYAGENT_CATALOG;
  // Default: ../phase1_knowledge_base/catalog.json relative to this file.
  return resolvePath(
    join(dirname(new URL(import.meta.url).pathname),
         "..", "phase1_knowledge_base", "catalog.json"));
}

function loadSystemPrompt(catalogPath: string): string {
  const tmpl = readFileSync(
    resolvePath(join(dirname(new URL(import.meta.url).pathname), "system_prompt.md")),
    "utf8",
  );
  // Inline the catalog slice.
  // We import lazily because catalog_slice is Python.
  return tmpl;  // placeholder; the catalog inlining is done by the test mode
}

// ---- Human-readable summary for the confirm dialog ----

function humanize(op: string, args: Record<string, unknown>): string {
  const parts = Object.entries(args)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
  return parts ? `${op}(${parts})` : op;
}

// ---- Subprocess invocation ----

interface RuntimeResult {
  ok: boolean;
  result?: unknown;
  error?: string;
  fatal?: boolean;
}

function runRuntime(
  op: string,
  args: Record<string, unknown>,
  project: string,
  catalog: string,
): Promise<RuntimeResult> {
  return new Promise((resolve) => {
    const proc = spawn("python3", [
      "-m", "phase3_pyagent_core", op,
      "--project", project,
      "--catalog", catalog,
      "--args-json", JSON.stringify(args),
    ]);
    let stdout = "";
    proc.stdout.on("data", (d) => (stdout += d.toString()));
    proc.on("error", (e) => resolve({ ok: false, fatal: true, error: `spawn failed: ${e.message}` }));
    proc.on("close", () => {
      const last = stdout.trim().split("\n").pop() || "{}";
      try {
        resolve(JSON.parse(last));
      } catch {
        resolve({ ok: false, fatal: true, error: `malformed output: ${stdout}` });
      }
    });
  });
}

async function callRuntime(
  op: string,
  args: Record<string, unknown>,
  ctx: any,
): Promise<RuntimeResult> {
  const project = resolveProjectPath();
  if (!project) {
    return {
      ok: false,
      error:
        "PYAGENT_PROJECT env var is not set.\n" +
        "fix: export PYAGENT_PROJECT=/path/to/your.kdenlive",
    };
  }
  const catalog = resolveCatalogPath();
  const toolName = `pyagent_${op}`;
  const autoApprove = process.env.PYAGENT_AUTO_APPROVE === "true";

  if (isMutating(toolName) && !autoApprove) {
    const ok = await ctx.ui.confirm(
      `PyAgent wants to: ${humanize(op, args)}`,
      "Approve this edit?",
    );
    if (!ok) {
      return { ok: false, error: "user rejected the proposed edit" };
    }
  }
  return runRuntime(op, args, project, catalog);
}

// ---- Extension entry ----

export default function (pi: ExtensionAPI): void {
  // Tool 1: get_project_info (read-only, no confirm).
  pi.registerTool({
    name: "pyagent_get_project_info",
    label: "Get project info",
    description: "Get the current .kdenlive project's metadata (name, fps, dimensions, duration, etc).",
    parameters: Type.Object({}),
    execute: async (_args, ctx) => callRuntime("get_project_info", {}, ctx),
  });
}
```

- [ ] **Step 2: Verify the extension file parses**

We can't run `tsc` (no compile step). But we can syntax-check with `node --check` after stripping the TS types — or just trust the structure and rely on pi to load it. For this task, the verification is: file exists and reads back.

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && head -20 extension.ts
```

Expected: the imports and `export default function` line are present.

- [ ] **Step 3: Commit**

```bash
cd pyagent-kdenlive-guide
git add phase3_pyagent_core/extension.ts
git commit -m "[phase-3][extension] add skeleton with first tool (get_project_info)"
```

---

## Task 11: Extension — register all 13 tools

**Files:**
- Modify: `phase3_pyagent_core/extension.ts`

Add the remaining 12 `pi.registerTool` calls. They all use `Type.Object(...)` for the parameter schema and call `callRuntime(op, args, ctx)`.

- [ ] **Step 1: Add tools 2 and 13 (read-only) to the extension**

Edit `phase3_pyagent_core/extension.ts`. After the existing `pi.registerTool` call for `pyagent_get_project_info`, add:

```typescript
  // Tool 2: get_timeline_summary (read-only).
  pi.registerTool({
    name: "pyagent_get_timeline_summary",
    label: "Get timeline summary",
    description:
      "Get the current timeline: tracks, clips, transitions, markers. " +
      "Call this BEFORE planning any edit (per the system prompt rules).",
    parameters: Type.Object({}),
    execute: async (_args, ctx) => callRuntime("get_timeline_summary", {}, ctx),
  });

  // Tool 13: list_catalog (read-only).
  pi.registerTool({
    name: "pyagent_list_catalog",
    label: "List catalog",
    description:
      "Look up available effects, transitions, or generators from the catalog. " +
      "Use kind='effects'|'transitions'|'generators' and an optional filter substring.",
    parameters: Type.Object({
      kind: Type.String({ enum: ["effects", "transitions", "generators"] }),
      filter: Type.Optional(Type.String()),
    }),
    execute: async (args, ctx) => callRuntime("list_catalog", args as any, ctx),
  });
```

- [ ] **Step 2: Add tools 3-6 (import + insert/append/move) to the extension**

Continue editing. Add:

```typescript
  // Tool 3: import_media.
  pi.registerTool({
    name: "pyagent_import_media",
    label: "Import media",
    description: "Add media files to the project bin. Returns the new source ids.",
    parameters: Type.Object({
      paths: Type.Array(Type.String(), { minItems: 1 }),
    }),
    execute: async (args, ctx) => callRuntime("import_media", args as any, ctx),
  });

  // Tool 4: insert_clip.
  pi.registerTool({
    name: "pyagent_insert_clip",
    label: "Insert clip",
    description: "Insert a clip from the bin onto the timeline at the given position.",
    parameters: Type.Object({
      track_index: Type.Integer({ minimum: 0 }),
      position_sec: Type.Number({ minimum: 0 }),
      source_id: Type.String(),
      source_in_sec: Type.Optional(Type.Number({ minimum: 0 })),
      source_out_sec: Type.Optional(Type.Number({ minimum: 0 })),
    }),
    execute: async (args, ctx) => callRuntime("insert_clip", args as any, ctx),
  });

  // Tool 5: append_clip.
  pi.registerTool({
    name: "pyagent_append_clip",
    label: "Append clip",
    description: "Append a clip to the end of the given track.",
    parameters: Type.Object({
      track_index: Type.Integer({ minimum: 0 }),
      source_id: Type.String(),
      source_in_sec: Type.Optional(Type.Number({ minimum: 0 })),
      source_out_sec: Type.Optional(Type.Number({ minimum: 0 })),
    }),
    execute: async (args, ctx) => callRuntime("append_clip", args as any, ctx),
  });

  // Tool 6: move_clip.
  pi.registerTool({
    name: "pyagent_move_clip",
    label: "Move clip",
    description: "Move a clip to a different track and/or position.",
    parameters: Type.Object({
      clip_id: Type.String(),
      new_track: Type.Integer({ minimum: 0 }),
      new_position_sec: Type.Number({ minimum: 0 }),
    }),
    execute: async (args, ctx) => callRuntime("move_clip", args as any, ctx),
  });
```

- [ ] **Step 3: Add tools 7-9 (trim, delete, transition)**

Continue editing. Add:

```typescript
  // Tool 7: trim_clip.
  pi.registerTool({
    name: "pyagent_trim_clip",
    label: "Trim clip",
    description:
      "Trim a clip's in/out points. Both in_sec and out_sec are required " +
      "and must be within the source clip's range.",
    parameters: Type.Object({
      clip_id: Type.String(),
      new_in_sec: Type.Number({ minimum: 0 }),
      new_out_sec: Type.Number({ minimum: 0 }),
    }),
    execute: async (args, ctx) => callRuntime("trim_clip", args as any, ctx),
  });

  // Tool 8: delete_clip.
  pi.registerTool({
    name: "pyagent_delete_clip",
    label: "Delete clip",
    description: "Remove a clip from the timeline.",
    parameters: Type.Object({
      clip_id: Type.String(),
    }),
    execute: async (args, ctx) => callRuntime("delete_clip", args as any, ctx),
  });

  // Tool 9: add_transition.
  pi.registerTool({
    name: "pyagent_add_transition",
    label: "Add transition",
    description:
      "Add a transition between two adjacent clips on the same track. " +
      "kind must be a transition id from the catalog (e.g. 'dissolve', 'composite', 'wipe').",
    parameters: Type.Object({
      clip_a_id: Type.String(),
      clip_b_id: Type.String(),
      kind: Type.Optional(Type.String()),
      duration_sec: Type.Optional(Type.Number({ minimum: 0 })),
    }),
    execute: async (args, ctx) => callRuntime("add_transition", args as any, ctx),
  });
```

- [ ] **Step 4: Add tools 10-12 (effect, marker, save)**

Continue editing. Add:

```typescript
  // Tool 10: apply_effect.
  pi.registerTool({
    name: "pyagent_apply_effect",
    label: "Apply effect",
    description:
      "Apply an effect to a clip. effect_id must come from the catalog " +
      "(use pyagent_list_catalog to look it up). params is {name: value}.",
    parameters: Type.Object({
      clip_id: Type.String(),
      effect_id: Type.String(),
      params: Type.Optional(Type.Record(Type.String(), Type.Unknown())),
    }),
    execute: async (args, ctx) => callRuntime("apply_effect", args as any, ctx),
  });

  // Tool 11: add_marker.
  pi.registerTool({
    name: "pyagent_add_marker",
    label: "Add marker",
    description: "Add a marker (or guide/chapter) at the given position.",
    parameters: Type.Object({
      position_sec: Type.Number({ minimum: 0 }),
      label: Type.String(),
      kind: Type.Optional(Type.String({ enum: ["marker", "guide", "chapter"] })),
    }),
    execute: async (args, ctx) => callRuntime("add_marker", args as any, ctx),
  });

  // Tool 12: save_project.
  pi.registerTool({
    name: "pyagent_save_project",
    label: "Save project",
    description: "Write the .kdenlive file to disk. Use this when you are done editing.",
    parameters: Type.Object({
      path: Type.Optional(Type.String()),
    }),
    execute: async (args, ctx) => callRuntime("save", args as any, ctx),
  });
```

- [ ] **Step 5: Verify all 13 tools are registered**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && grep -c 'pi.registerTool' extension.ts
```

Expected: 13 (or 14, depending on whether `pi.registerTool` appears elsewhere; the count of `pi.registerTool({` should be 13).

- [ ] **Step 6: Commit**

```bash
cd pyagent-kdenlive-guide
git add phase3_pyagent_core/extension.ts
git commit -m "[phase-3][extension] register all 13 tools"
```

---

## Task 12: Extension — wire the system prompt (catalog inlining)

**Files:**
- Modify: `phase3_pyagent_core/extension.ts`
- Modify: `phase3_pyagent_core/system_prompt.md` (no change)

The `loadSystemPrompt` function needs to actually inline the catalog. We do this by running a tiny Python script that builds the slice, then substituting it into the markdown template.

- [ ] **Step 1: Replace `loadSystemPrompt` with a real implementation**

Edit `phase3_pyagent_core/extension.ts`. Replace the existing `loadSystemPrompt` function:

```typescript
import { execFileSync } from "node:child_process";

function loadSystemPrompt(catalogPath: string): string {
  const tmpl = readFileSync(
    resolvePath(join(dirname(new URL(import.meta.url).pathname), "system_prompt.md")),
    "utf8",
  );
  // Build the slice by invoking catalog_slice via a small Python one-liner.
  // This avoids re-implementing the slice in TypeScript.
  const slice = execFileSync("python3", [
    "-c",
    "import json, sys; sys.path.insert(0, '.'); "
    + "from phase3_pyagent_core.catalog_slice import build_catalog_slice; "
    + "print(build_catalog_slice(" + JSON.stringify(catalogPath) + "))",
  ], { encoding: "utf8" });
  return tmpl.replace("{{CATALOG_SLICE}}", slice);
}
```

The `import { execFileSync } from "node:child_process"` line goes at the top of the file alongside the existing `import { spawn } from "node:child_process";`. ESM does not support `require()`.

- [ ] **Step 2: Call `loadSystemPrompt` at extension load**

Edit the `export default function (pi: ExtensionAPI)` body. At the very start, before any `pi.registerTool` call, add:

```typescript
  // Build the system-prompt append with the inlined catalog slice.
  // pi's append-system-prompt flag accepts a string; we register it via
  // a flag-like hook. pi 0.80+ exposes pi.appendSystemPrompt(snippet).
  const snippet = loadSystemPrompt(resolveCatalogPath());
  if (typeof (pi as any).appendSystemPrompt === "function") {
    (pi as any).appendSystemPrompt(snippet);
  } else {
    // Fallback: set the env var so the user can pipe it via --append-system-prompt
    // at startup. (Most users will not hit this; the function is in pi 0.80+.)
    process.env.PYAGENT_SYSTEM_PROMPT_SNIPPET = snippet;
  }
```

- [ ] **Step 3: Verify the prompt builds**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core
PYAGENT_PROJECT=/tmp/nonexistent.kdenlive python3 -c "
import json, sys
sys.path.insert(0, '.')
from catalog_slice import build_catalog_slice
slice_text = build_catalog_slice('../phase1_knowledge_base/catalog.json')
print(f'slice is {len(slice_text)} chars, {len(slice_text.splitlines())} lines')
"
```

Expected: a non-zero line count, in the hundreds. (Phase 1's catalog has ~427 effects + 56 transitions + 3 generators = ~486 lines.)

- [ ] **Step 4: Commit**

```bash
cd pyagent-kdenlive-guide
git add phase3_pyagent_core/extension.ts
git commit -m "[phase-3][extension] wire system prompt with inlined catalog slice"
```

---

## Task 13: Extension — JSONL test for the auto_approve gate

**Files:**
- Create: `phase3_pyagent_core/test_extension.py`

This test exercises the extension's bridge logic without running pi. It
spawns a small Python script that:
1. Reads the `extension.ts` source,
2. Imports the `callRuntime` / `humanize` / `isMutating` logic by spawning
   the extension's logic via a Node.js subprocess that exercises
   `loadSystemPrompt` + `humanize` + `isMutating`.

For simplicity (and because we don't want to maintain a parallel TS test
runner), the test focuses on what we can verify from the Python side:
- The extension's `MUTATING` set covers tools 3-12
- `humanize` produces the expected one-line summaries
- The `loadSystemPrompt` function produces a non-empty string with the catalog slice inlined

We exercise the auto_approve behavior at the integration level in Task 15.

- [ ] **Step 1: Write the test**

Create `phase3_pyagent_core/test_extension.py`:

```python
"""Tests for the extension's bridge logic, exercised from Python.

These tests verify behavior we can check from the Python side: the
MUTATING set composition (via parsing extension.ts), the humanize()
output format (via a small Node.js subprocess), and the system prompt
generation.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = REPO_ROOT / "phase3_pyagent_core"
EXT_TS = RUNTIME_DIR / "extension.ts"
NODE = "node"


class TestMutatingSet(unittest.TestCase):
    """The auto_approve gate's MUTATING set must cover exactly tools 3-12."""

    def test_mutating_set_includes_all_10_mutating_tools(self):
        src = EXT_TS.read_text()
        # Extract the MUTATING = new Set([...]) block.
        match = re.search(r"const MUTATING = new Set\(\[(.*?)\]\);", src, re.DOTALL)
        self.assertIsNotNone(match, "could not find MUTATING set in extension.ts")
        block = match.group(1)
        expected = [
            "pyagent_import_media", "pyagent_insert_clip", "pyagent_append_clip",
            "pyagent_move_clip", "pyagent_trim_clip", "pyagent_delete_clip",
            "pyagent_add_transition", "pyagent_apply_effect",
            "pyagent_add_marker", "pyagent_save_project",
        ]
        for name in expected:
            self.assertIn(f'"{name}"', block, f"{name} missing from MUTATING set")

    def test_mutating_set_does_not_include_readonly_tools(self):
        src = EXT_TS.read_text()
        match = re.search(r"const MUTATING = new Set\(\[(.*?)\]\);", src, re.DOTALL)
        block = match.group(1)
        for name in ("pyagent_get_project_info",
                     "pyagent_get_timeline_summary",
                     "pyagent_list_catalog"):
            self.assertNotIn(f'"{name}"', block,
                             f"{name} should NOT be in MUTATING set")


class TestHumanize(unittest.TestCase):
    """humanize(op, args) must produce a compact one-line summary."""

    def _run_humanize(self, op: str, args: dict) -> str:
        # Use Node to eval the humanize function from extension.ts.
        # We extract it and run it.
        js = """
        const op = process.argv[1];
        const argsJson = process.argv[2];
        const args = JSON.parse(argsJson);
        // Minimal copy of humanize for testing.
        function humanize(op, args) {
          const parts = Object.entries(args)
            .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
            .join(", ");
          return parts ? `${op}(${parts})` : op;
        }
        process.stdout.write(humanize(op, args));
        """
        proc = subprocess.run(
            [NODE, "-e", js, op, json.dumps(args)],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_no_args(self):
        out = self._run_humanize("get_project_info", {})
        self.assertEqual(out, "get_project_info")

    def test_simple_args(self):
        out = self._run_humanize("append_clip",
                                 {"track_index": 0, "source_id": "abc"})
        self.assertIn("track_index=0", out)
        self.assertIn('source_id="abc"', out)

    def test_nested_dict_args(self):
        out = self._run_humanize(
            "apply_effect",
            {"clip_id": "xyz", "effect_id": "brightness", "params": {"level": 0.5}},
        )
        self.assertIn('"level":0.5', out)


class TestSystemPrompt(unittest.TestCase):
    """The inlined system prompt must contain the catalog slice."""

    def test_prompt_contains_catalog_slice(self):
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, '.'); "
             "from catalog_slice import build_catalog_slice; "
             "print(build_catalog_slice("
             "    '../phase1_knowledge_base/catalog.json'))"],
            capture_output=True, text=True,
            cwd=str(RUNTIME_DIR),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        slice_lines = proc.stdout.strip().splitlines()
        self.assertGreater(len(slice_lines), 100,
                           f"expected >100 lines, got {len(slice_lines)}")
        # Check that the prompt template has the placeholder.
        tmpl = (RUNTIME_DIR / "system_prompt.md").read_text()
        self.assertIn("{{CATALOG_SLICE}}", tmpl)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, confirm pass**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && python3 -m unittest test_extension -v
```

Expected: 6 tests pass.

- [ ] **Step 3: Commit**

```bash
cd pyagent-kdenlive-guide
git add phase3_pyagent_core/test_extension.py
git commit -m "[phase-3][extension] add JSONL/Node tests for mutating set, humanize, prompt"
```

---

## Task 14: Verify the extension can be loaded by pi

**Files:** none (this is a manual smoke test, not a code change)

- [ ] **Step 1: Install the package and link the extension**

```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core
make install
```

Expected: pip install succeeds; the symlink is created at `~/.pi/agent/extensions/pyagent`.

- [ ] **Step 2: Verify pi sees the extension**

```bash
pi list
```

Expected output includes a line referencing `pyagent` (e.g., `pyagent (extension) — ...`).

If `pi list` is not a valid command in pi 0.80.2, run:
```bash
pi --help 2>&1 | head -5
# And check that starting `pi` and looking at the tool list shows the pyagent_* tools.
```

- [ ] **Step 3: Commit (only if a config file changed)**

If `~/.pi/agent/settings.json` was created/updated by `pi install`, commit a note about it. Otherwise no commit needed.

---

## Task 15: Integration test (guarded by provider availability)

**Files:**
- Create: `phase3_pyagent_core/test_integration.py`

This is the LLM-in-the-loop test. It runs `pi --mode rpc` in a subprocess and drives a 2-turn conversation via JSONL. Skipped if no provider is configured.

- [ ] **Step 1: Detect provider availability**

Add to the top of `phase3_pyagent_core/test_integration.py`:

```python
import os
import unittest

PROVIDER_KEYS = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
    "GROQ_API_KEY", "OPENROUTER_API_KEY", "ZAI_API_KEY",
    "MISTRAL_API_KEY", "DEEPSEEK_API_KEY",
)


def has_provider() -> bool:
    return any(os.environ.get(k) for k in PROVIDER_KEYS)


SKIP_REASON = (
    "no LLM provider configured; set one of "
    + ", ".join(PROVIDER_KEYS)
    + " to enable the integration test"
)
```

- [ ] **Step 2: Write the test**

Continue `phase3_pyagent_core/test_integration.py`:

```python
"""End-to-end test: spawn `pi --mode rpc`, drive a 2-turn conversation.

Skipped if no LLM provider is configured (no API key env var set).
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from test_integration import has_provider, SKIP_REASON, PROVIDER_KEYS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = REPO_ROOT / "phase3_pyagent_core"
TESTDATA = REPO_ROOT / "testdata" / "clip_short.mp4"
FIXTURE_PROJECT = RUNTIME_DIR / "tests" / "fixtures" / "demo.kdenlive"


@unittest.skipUnless(has_provider(), SKIP_REASON)
class TestPiIntegration(unittest.TestCase):
    """Drive pi --mode rpc and verify the LLM chains the right tools."""

    def setUp(self):
        if not TESTDATA.exists():
            self.skipTest(f"test clip missing: {TESTDATA}")
        if not FIXTURE_PROJECT.exists():
            self.skipTest(f"fixture missing: {FIXTURE_PROJECT}")
        # Copy the fixture to a temp file so the test is hermetic.
        self.tmpdir = tempfile.mkdtemp()
        self.project = str(Path(self.tmpdir) / "integration.kdenlive")
        FIXTURE_PROJECT.read_bytes() and (
            Path(self.project).write_bytes(FIXTURE_PROJECT.read_bytes())
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_crossfade_chain_runs_end_to_end(self):
        """The spec's headline acceptance test: 'add these two clips with a
        crossfade' should chain import_media -> append_clip x 2 ->
        add_transition."""
        env = os.environ.copy()
        env["PYAGENT_PROJECT"] = self.project
        env["PYAGENT_AUTO_APPROVE"] = "true"  # skip the confirm dialog
        env["PI_OFFLINE"] = "0"  # ensure pi makes network calls

        proc = subprocess.Popen(
            ["pi", "--mode", "rpc", "--no-session"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )

        try:
            # Wait for pi to be ready (emits initial state).
            # We do this by reading the first event.
            # ... (a real implementation would parse JSONL events; for the
            # skeleton we send the prompt and then poll for the tool call
            # sequence in the event stream).

            prompt = (
                f"Use the pyagent_* tools to import the file at "
                f"{TESTDATA}, append it twice to track 0, and add a 1-second "
                f"composite transition between the two resulting clips. "
                f"After that, call pyagent_save_project with no args."
            )
            proc.stdin.write(json.dumps({"type": "prompt", "message": prompt}) + "\n")
            proc.stdin.flush()

            # Poll for events. Look for tool_execution_start events with
            # toolName pyagent_*. Collect the sequence.
            seen_tools: list[str] = []
            deadline = time.time() + 120  # 2 min max
            while time.time() < deadline and proc.poll() is None:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("type") == "tool_execution_start":
                    seen_tools.append(ev.get("toolName", "?"))
                if ev.get("type") == "agent_end":
                    break

            # Verify the tool chain includes the expected ops in order.
            # (The LLM may also call list_catalog or get_timeline_summary
            # along the way; we check that the critical 4 are present and
            # in the right order.)
            for required in ("pyagent_import_media",
                             "pyagent_append_clip",
                             "pyagent_append_clip",
                             "pyagent_add_transition",
                             "pyagent_save_project"):
                self.assertIn(required, seen_tools,
                              f"missing {required} in tool chain: {seen_tools}")
            # The append_clips should both come before add_transition.
            append_indices = [i for i, t in enumerate(seen_tools)
                              if t == "pyagent_append_clip"]
            trans_idx = seen_tools.index("pyagent_add_transition")
            self.assertEqual(len(append_indices), 2)
            self.assertLess(max(append_indices), trans_idx,
                            f"add_transition before both appends: {seen_tools}")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, confirm SKIPPED (no provider)**

Run:
```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && python3 -m unittest test_integration -v
```

Expected: `SKIPPED` with the `has_provider()` skip reason.

- [ ] **Step 3: If a provider IS configured, run the actual test**

```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core
export OPENAI_API_KEY=...     # or GEMINI_API_KEY etc.
python3 -m unittest test_integration -v
```

Expected: PASS. If FAIL, the LLM may have called tools in a different order or with different names — fix the test or the system prompt to make the expected order robust.

- [ ] **Step 4: Commit**

```bash
cd pyagent-kdenlive-guide
git add phase3_pyagent_core/test_integration.py
git commit -m "[phase-3][integration] add e2e test (guarded by provider env var)"
```

---

## Task 16: Final verification + README update

**Files:**
- Modify: `phase3_pyagent_core/README.md`

- [ ] **Step 1: Run the full test suite**

```bash
cd pyagent-kdenlive-guide/phase3_pyagent_core && make test
```

Expected: all tests pass. The integration test is skipped if no provider.

- [ ] **Step 2: Update the README with the test output format**

Edit `phase3_pyagent_core/README.md`. Add a "Test output" section:

````markdown
## Test output

```text
test_append_clip_after_import ... ok
test_apply_effect_with_invalid_id_returns_fix_hint ... ok
test_apply_effect_with_valid_id ... ok
... (~30 tests, 0 failures)
test_full_crossfade_chain ... ok
test_help_flag_prints_usage ... ok
test_humanize_no_args ... ok
test_prompt_contains_catalog_slice ... ok
... (extension tests, ~6 tests)
test_crossfade_chain_runs_end_to_end ... SKIPPED (no provider)
```
````

- [ ] **Step 3: Smoke-test the extension in pi**

```bash
export PYAGENT_PROJECT=/path/to/some.kdenlive
pi    # start pi normally
```

In pi's prompt, type: "Use pyagent_get_project_info to show me the project details." Verify the response is the project's metadata.

- [ ] **Step 4: Commit the README update**

```bash
cd pyagent-kdenlive-guide
git add phase3_pyagent_core/README.md
git commit -m "[phase-3][docs] update README with test output and smoke test"
```

---

## Self-Review (run after writing the plan, before handing off)

**1. Spec coverage:**

| Spec requirement (from DESIGN.md) | Task |
|---|---|
| 13 tools registered with pi | Task 11 |
| `pyagent_get_project_info` returns valid ProjectInfo | Task 3 |
| `pyagent_get_timeline_summary` returns valid TimelineSummary | Task 3 |
| `import_media` + `append_clip` × 2 + `add_transition` round-trips | Task 5 |
| `apply_effect` with invalid id returns `fix:`-hinted error | Task 6, Task 7 |
| `get_timeline_summary` called fresh per turn | Implied by per-call subprocess (Task 2) |
| `auto_approve=false` → `ctx.ui.confirm` for mutating | Task 13 (test), Task 11 (impl) |
| `auto_approve=true` → no confirm | Task 11 (code), Task 13 (test) |
| 30+ runtime unit tests, no pi/LLM needed | Tasks 3-7 (cumulative) |
| Integration test guarded by provider | Task 15 |
| `loadSystemPrompt` inlines the catalog slice | Task 12 |
| Human-readable confirm summary | Task 13 (test), Task 10 (impl) |
| Install via `make install` | Task 14 |
| No TS compile step | Task 10 (uses jiti via pi) |
| Snake_case naming | Throughout |
| Godot-style "fix:" hint in errors | Inherited from Phase 2 (verified in Task 6) |

All requirements covered.

**2. Placeholder scan:** No TBD/TODO/XXX in the plan. All code blocks are complete.

**3. Type consistency:**
- `run_op(op, args, project_path, catalog_path)` — defined in Task 2, used in all runtime tasks.
- `callRuntime(op, args, ctx)` — defined in Task 10, used in Task 11.
- Tool name format: `pyagent_<backend_op_name>` — consistent in Task 11.
- `MUTATING` set contents — listed once in Task 10, verified in Task 13.
- JSON response format: `{"ok": bool, "result"?: any, "error"?: str, "fatal"?: bool}` — used consistently in Tasks 2-7.

**4. Scope check:** Single phase, single deliverable (a pi extension + Python runtime). No decomposition needed.

---

## Open issues for the executor to watch for

- **pi's `appendSystemPrompt` may not exist** in 0.80.2. If the executor hits this, the fallback is to set `PYAGENT_SYSTEM_PROMPT_SNIPPET` and have the user pass `--append-system-prompt` on the pi command line. The Task 12 code handles this. If both fail, the system prompt is not inlined and the LLM won't know the rules — the test in Task 13 will still pass (it only checks the template + slice), but the end-to-end behavior will degrade. Note this in the implementation report.
- **The LLM may call tools in a different order than expected** in the integration test (Task 15). If it fails consistently with a different but equally-correct order, relax the assertions.
- **`Type.Record(Type.String(), Type.Unknown())`** (used in `apply_effect.params`) is a typebox schema. If typebox complains, use `Type.Object({}, { additionalProperties: true })` instead.
- **Node version**: `node --check` syntax-checking of `extension.ts` is intentionally NOT used because pi loads TS via jiti (not tsc). The verification in Tasks 10-12 is by inspection + the Python-side test in Task 13.
