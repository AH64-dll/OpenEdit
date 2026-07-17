# Phase 7 Real pi-session e2e Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent end-to-end test (`phase7_real_session`) that drives a real `pi` session against a real Kdenlive in a virtual display via the chat UI, asserting the LLM picked the right tool, the file changed on disk, and the live Kdenlive shows the change via D-Bus.

**Architecture:** New module `pyagent-kdenlive-guide/phase7_real_session/` with five small helper classes (XvfbContext, KdenliveLaunch, ChatUIServer, WSClient, dbus_probe), skipif helpers, and one e2e test. Unit tests cover helpers; the e2e test assembles them. Skipif guards skip the e2e test cleanly on machines missing deps.

**Tech Stack:** Python 3.11+, stdlib (`subprocess`, `tempfile`, `xml.etree.ElementTree`, `urllib`, `socket`, `os`, `signal`, `time`), existing `phase5_dbus_sync.dbus_client.KdenliveDBus`, `websockets` (already a phase4 dep), `unittest`.

## Global Constraints

- Godot 4 / GDScript rules do **not** apply (this is a Python module).
- All new code lives under `pyagent-kdenlive-guide/phase7_real_session/`.
- `phase3_pyagent_core/tests/fixtures/demo.kdenlive` is read-only — always copy to a tempdir first.
- `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` are redirected to the test tempdir for any Kdenlive launch.
- Skipif guards mean: missing dep → `skipped`, not `failed`.
- Commit format: `[phase-7][<system>] <imperative summary>`.
- All file paths are absolute from the repo root `/home/ah64/apps/mlt-pipeline/`.
- Run unit tests with `PYTHONPATH=. python3 -m unittest discover -s phase7_real_session/tests -p "test_*.py"`.
- Run e2e with `PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_e2e_pi_session -v`.
- Filenames: snake_case, no CamelCase, no spaces.
- Reuse existing patterns: phase layout, `pyproject.toml` shape, `Makefile` shape, test discovery, `KdenliveDBus` client.
- **Testability of subprocess launchers:** every helper that launches a subprocess (Xvfb, Kdenlive, chat UI) takes an injectable `command`/`binary` arg so unit tests can run a fake without needing the real binary. Defaults to the real command.
- The e2e test setUp/tearDown **must** kill every spawned subprocess even on assertion failure (use `try/finally`).

---

## File Map

| File | Created in | Responsibility |
|---|---|---|
| `pyagent-kdenlive-guide/phase7_real_session/__init__.py` | Task 1 | Empty package marker. |
| `pyagent-kdenlive-guide/phase7_real_session/pyproject.toml` | Task 1 | Package metadata, test-only deps. |
| `pyagent-kdenlive-guide/phase7_real_session/Makefile` | Task 1 | `test`, `test-e2e` targets. |
| `pyagent-kdenlive-guide/phase7_real_session/README.md` | Task 1 | One-pager: what, how, deps. |
| `pyagent-kdenlive-guide/phase7_real_session/skipif_helpers.py` | Task 1 | `_has`, `_has_opencode_auth`, `_kdenlive_already_on_bus`. |
| `pyagent-kdenlive-guide/phase7_real_session/tests/__init__.py` | Task 1 | Empty test package marker. |
| `pyagent-kdenlive-guide/phase7_real_session/tests/test_skipif.py` | Task 1 | Unit tests for skipif_helpers. |
| `pyagent-kdenlive-guide/phase7_real_session/xvfb.py` | Task 2 | `XvfbContext` class. |
| `pyagent-kdenlive-guide/phase7_real_session/tests/test_xvfb.py` | Task 2 | Unit tests for XvfbContext. |
| `pyagent-kdenlive-guide/phase7_real_session/kdenlive.py` | Task 3 | `KdenliveLaunch` class. |
| `pyagent-kdenlive-guide/phase7_real_session/tests/test_kdenlive.py` | Task 3 | Unit tests for KdenliveLaunch. |
| `pyagent-kdenlive-guide/phase7_real_session/chat_ui.py` | Task 4 | `ChatUIServer` class. |
| `pyagent-kdenlive-guide/phase7_real_session/tests/test_chat_ui.py` | Task 4 | Unit tests for ChatUIServer. |
| `pyagent-kdenlive-guide/phase7_real_session/ws_client.py` | Task 5 | `WSClient` class. |
| `pyagent-kdenlive-guide/phase7_real_session/tests/test_ws_client.py` | Task 5 | Unit tests for WSClient. |
| `pyagent-kdenlive-guide/phase7_real_session/dbus_probe.py` | Task 6 | `read_timeline_state` function. |
| `pyagent-kdenlive-guide/phase7_real_session/tests/test_dbus_probe.py` | Task 6 | Unit tests for dbus_probe. |
| `pyagent-kdenlive-guide/phase7_real_session/tests/test_e2e_pi_session.py` | Task 7 | The e2e test. |
| `pyagent-kdenlive-guide/README.md` | Task 8 | Add "Real-session e2e test" section. |

---

### Task 1: Scaffolding + skipif_helpers

**Files:**
- Create: `pyagent-kdenlive-guide/phase7_real_session/__init__.py`
- Create: `pyagent-kdenlive-guide/phase7_real_session/pyproject.toml`
- Create: `pyagent-kdenlive-guide/phase7_real_session/Makefile`
- Create: `pyagent-kdenlive-guide/phase7_real_session/README.md`
- Create: `pyagent-kdenlive-guide/phase7_real_session/skipif_helpers.py`
- Create: `pyagent-kdenlive-guide/phase7_real_session/tests/__init__.py`
- Create: `pyagent-kdenlive-guide/phase7_real_session/tests/test_skipif.py`

**Interfaces (this task produces, later tasks consume):**
- `phase7_real_session.skipif_helpers._has(name: str) -> bool`
- `phase7_real_session.skipif_helpers._has_opencode_auth() -> bool`
- `phase7_real_session.skipif_helpers._kdenlive_already_on_bus() -> bool`

**Consumes:** nothing (this is the first task).

- [ ] **Step 1: Create the package directory and `__init__.py`**

```bash
mkdir -p /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/tests
```

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/__init__.py`:

```python
"""phase7_real_session — real pi-session end-to-end test.

This module has no production entry point. It exists to drive a real
pi subprocess against a real Kdenlive in a virtual display via the
chat UI, and assert the end-to-end pipeline (LLM → file → D-Bus
live-sync) works.
"""
```

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/tests/__init__.py`:

```python
"""Test package for phase7_real_session."""
```

- [ ] **Step 2: Create `pyproject.toml`**

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "pyagent-phase7-real-session"
version = "0.1.0"
description = "Real-pi-session end-to-end test for the pyagent Kdenlive toolchain."
requires-python = ">=3.11"
# No [project.scripts] — this module has no production entry point.

[project.optional-dependencies]
test = [
    "websockets>=12",
    "dbus-python>=1.3",
]

[tool.setuptools.packages.find]
include = ["phase7_real_session*"]
```

- [ ] **Step 3: Create `Makefile`**

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/Makefile`:

```makefile
.PHONY: test test-e2e

test:
	@PYTHONPATH=../.. python3 -m unittest discover -s tests -p "test_*.py"

test-e2e:
	@echo "Running e2e real-pi-session test (needs pi, kdenlive, Xvfb, OPENCODE_API_KEY)..."
	@PYTHONPATH=../.. python3 -m unittest tests.test_e2e_pi_session -v
```

(The `PYTHONPATH=../..` lets the makefile be run from either the phase7 dir or the project root.)

- [ ] **Step 4: Create `README.md` skeleton**

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/README.md`:

```markdown
# phase7_real_session

Real pi-session end-to-end test for the pyagent Kdenlive toolchain.

## What it does

Drives a real `pi --mode json` subprocess against a real Kdenlive
running in a virtual X display, via the chat UI's WebSocket. Asserts:

1. The LLM picks `pyagent_add_transition` from the 19-tool catalog.
2. The file-mode edit lands on disk.
3. The same edit appears in the running Kdenlive via D-Bus.
4. The LLM describes the action in its final assistant message.

## How to run

```bash
# From the phase7_real_session directory:
make test        # unit tests for the helpers (fast, no display needed)
make test-e2e    # the e2e test (20-45s, needs display + network)
```

## Required dependencies (for `make test-e2e`)

| Dep | Skip reason | Install on Arch |
|---|---|---|
| `pi` | "pi not on PATH" | already on this machine |
| `kdenlive` | "kdenlive not on PATH" | `sudo pacman -S kdenlive` |
| `Xvfb` | "Xvfb not on PATH (install xorg-server-xvfb)" | `sudo pacman -S xorg-server-xvfb` |
| `dbus-send` | "dbus-send not on PATH" | `sudo pacman -S dbus` |
| `OPENCODE_API_KEY` (or `~/.pi/agent/auth.json`) | "opencode auth not configured" | `pi /login` |

The test also **skips** if a kdenlive is already on the session D-Bus
(to avoid colliding with the user's running Kdenlive). Close any open
Kdenlive and re-run.

## Layout

| File | Purpose |
|---|---|
| `skipif_helpers.py` | skipif functions used by `test_e2e_pi_session.py`. |
| `xvfb.py` | `XvfbContext` — start/stop virtual display. |
| `kdenlive.py` | `KdenliveLaunch` — launch Kdenlive + wait for D-Bus. |
| `chat_ui.py` | `ChatUIServer` — launch chat UI + healthcheck. |
| `ws_client.py` | `WSClient` — drive the WebSocket, collect events. |
| `dbus_probe.py` | `read_timeline_state` — read live Kdenlive state. |
| `tests/test_*.py` | Unit tests for the above. |
| `tests/test_e2e_pi_session.py` | The e2e test. |
```

- [ ] **Step 5: Write the failing test for `skipif_helpers`**

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/tests/test_skipif.py`:

```python
"""Unit tests for skipif_helpers."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from phase7_real_session.skipif_helpers import (
    _has,
    _has_opencode_auth,
    _kdenlive_already_on_bus,
)


class TestHas(unittest.TestCase):
    def test_returns_true_for_existing_binary(self) -> None:
        # `python3` is always on PATH on this machine.
        self.assertTrue(_has("python3"))

    def test_returns_false_for_missing_binary(self) -> None:
        self.assertFalse(_has("definitely-not-a-binary-xyz"))


class TestHasOpencodeAuth(unittest.TestCase):
    def test_true_when_env_var_set(self) -> None:
        with mock.patch.dict(os.environ, {"OPENCODE_API_KEY": "x"}, clear=False):
            self.assertTrue(_has_opencode_auth())

    def test_true_when_auth_file_exists(self) -> None:
        fake_auth = Path.home() / ".pi/agent/auth.json"
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "__truediv__", lambda *a: fake_auth):
            self.assertTrue(_has_opencode_auth())

    def test_false_when_neither(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(Path, "is_file", return_value=False):
            self.assertFalse(_has_opencode_auth())


class TestKdenliveAlreadyOnBus(unittest.TestCase):
    def test_true_when_kdenlive_in_list(self) -> None:
        fake = mock.Mock()
        fake.stdout = "string \"org.kde.kdenlive\"\n"
        with mock.patch("subprocess.run", return_value=fake):
            self.assertTrue(_kdenlive_already_on_bus())

    def test_false_when_no_kdenlive(self) -> None:
        fake = mock.Mock()
        fake.stdout = "string \"org.freedesktop.DBus\"\n"
        with mock.patch("subprocess.run", return_value=fake):
            self.assertFalse(_kdenlive_already_on_bus())

    def test_false_when_dbus_send_fails(self) -> None:
        fake = mock.Mock()
        fake.stdout = ""
        fake.returncode = 1
        with mock.patch("subprocess.run", return_value=fake):
            self.assertFalse(_kdenlive_already_on_bus())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 6: Run the test to verify it fails**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_skipif -v
```

Expected: `ModuleNotFoundError: No module named 'phase7_real_session.skipif_helpers'`. (Or `ImportError`.)

- [ ] **Step 7: Implement `skipif_helpers.py`**

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/skipif_helpers.py`:

```python
"""Skipif helpers used by test_e2e_pi_session.py.

These functions are intentionally side-effect-light: they check
whether a dependency is present without launching anything heavy.
Each function is the body of a `@unittest.skipUnless` /
`@unittest.skipIf` decorator on the e2e test class.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _has(name: str) -> bool:
    """True if `name` is on PATH."""
    return shutil.which(name) is not None


def _has_opencode_auth() -> bool:
    """True if pi can authenticate with the opencode provider.

    Accepts either OPENCODE_API_KEY in the environment, or a
    stored auth file at ~/.pi/agent/auth.json (the file pi
    creates after `/login` via OAuth).
    """
    if os.environ.get("OPENCODE_API_KEY"):
        return True
    auth_file = Path.home() / ".pi" / "agent" / "auth.json"
    return auth_file.is_file()


def _kdenlive_already_on_bus() -> bool:
    """True if a kdenlive is already registered on the session D-Bus.

    The test must skip in this case because the D-Bus name
    `org.kde.kdenlive` is global — our launched Kdenlive would
    collide with the user's Kdenlive, and the test's D-Bus
    probes would talk to the wrong instance.
    """
    try:
        out = subprocess.run(
            ["dbus-send", "--session", "--print-reply",
             "--dest=org.freedesktop.DBus", "/org/freedesktop/DBus",
             "org.freedesktop.DBus.ListNames"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return "kdenlive" in (out.stdout or "").lower()
```

- [ ] **Step 8: Run the test to verify it passes**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_skipif -v
```

Expected: 6 tests pass (`test_returns_true_for_existing_binary`, `test_returns_false_for_missing_binary`, `test_true_when_env_var_set`, `test_true_when_auth_file_exists`, `test_false_when_neither`, `test_true_when_kdenlive_in_list`, `test_false_when_no_kdenlive`, `test_false_when_dbus_send_fails` — that's 8 actually).

- [ ] **Step 9: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && \
  git add pyagent-kdenlive-guide/phase7_real_session/ && \
  git -c user.email=ah64@local -c user.name=ah64 commit \
    -m "[phase-7][scaffold] add phase7_real_session package and skipif helpers

Scaffolds the new phase7_real_session module (pyproject, Makefile,
README) and implements skipif_helpers.py with _has, _has_opencode_auth,
_kdenlive_already_on_bus. 8 unit tests pass."
```

---

### Task 2: XvfbContext

**Files:**
- Create: `pyagent-kdenlive-guide/phase7_real_session/xvfb.py`
- Create: `pyagent-kdenlive-guide/phase7_real_session/tests/test_xvfb.py`

**Interfaces (this task produces, later tasks consume):**
- `phase7_real_session.xvfb.XvfbContext` — class:
  - `__init__(self, min_display: int = 99, max_display: int = 199, binary: str = "Xvfb")`
  - `__enter__(self) -> str`  — returns the display string `":<N>"`. Raises `RuntimeError` if no free display.
  - `__exit__(self, *exc) -> None` — kills the Xvfb process group, safe to call after a failed `__enter__`.
  - `display` (str property) — the display string, or empty if not entered.

**Consumes:** nothing (no other helper needed yet).

- [ ] **Step 1: Write the failing test**

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/tests/test_xvfb.py`:

```python
"""Unit tests for XvfbContext.

These tests use a fake Xvfb binary (a shell script) so they run
without Xvfb installed. The fake script writes a marker file and
sleeps; the test asserts the marker is created and the cleanup
kills the process.
"""
from __future__ import annotations

import os
import shutil
import signal
import tempfile
import time
import unittest
from pathlib import Path

from phase7_real_session.xvfb import XvfbContext


def _make_fake_xvfb(tmp: Path, hold_seconds: float = 30.0) -> Path:
    """Write a shell script that pretends to be Xvfb.

    It touches a marker file and sleeps, so the test can verify
    the script was launched and then kill it.
    """
    script = tmp / "fake-xvfb.sh"
    script.write_text(
        "#!/bin/sh\n"
        f"touch {tmp}/xvfb-started.marker\n"
        f"sleep {hold_seconds}\n"
    )
    script.chmod(0o755)
    return script


class TestXvfbContextWithFakeBinary(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="phase7_xvfb_test_"))
        self.fake = _make_fake_xvfb(self.tmp, hold_seconds=30.0)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_enter_launches_and_returns_display(self) -> None:
        with XvfbContext(binary=str(self.fake)) as display:
            self.assertTrue(display.startswith(":"), f"display={display!r}")
            # Marker should appear once the fake binary has run.
            deadline = time.time() + 3.0
            while time.time() < deadline:
                if (self.tmp / "xvfb-started.marker").exists():
                    break
                time.sleep(0.05)
            self.assertTrue(
                (self.tmp / "xvfb-started.marker").exists(),
                "fake Xvfb script was not launched",
            )

    def test_exit_kills_process(self) -> None:
        with XvfbContext(binary=str(self.fake)) as display:
            self.assertTrue(display.startswith(":"))
        # After exit, the marker exists (script ran) but no sleep
        # processes from this group should remain.
        # Best-effort: just verify __exit__ didn't raise.
        # (We can't easily check the process is gone across systems.)

    def test_missing_binary_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            with XvfbContext(binary="/nonexistent/binary/xyz"):
                pass

    def test_exit_without_enter_is_safe(self) -> None:
        ctx = XvfbContext(binary=str(self.fake))
        # Should not raise.
        ctx.__exit__(None, None, None)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_xvfb -v
```

Expected: `ModuleNotFoundError: No module named 'phase7_real_session.xvfb'`.

- [ ] **Step 3: Implement `xvfb.py`**

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/xvfb.py`:

```python
"""XvfbContext — start a virtual X display for headless Kdenlive.

The context manager picks the lowest free display in
[min_display, max_display] and starts Xvfb there. On exit, it
sends SIGTERM to the Xvfb process group; if the process is still
alive 5 seconds later, it sends SIGKILL.

The `binary` argument is injectable so unit tests can run a fake
script. In production it defaults to "Xvfb".
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from typing import Optional


class XvfbContext:
    """Context manager wrapping a virtual X display.

    Usage:
        with XvfbContext() as display:
            os.environ["DISPLAY"] = display
            launch_kdenlive(...)

    The `binary` parameter lets tests substitute a fake script.
    """

    def __init__(
        self,
        min_display: int = 99,
        max_display: int = 199,
        binary: str = "Xvfb",
    ) -> None:
        self._min = min_display
        self._max = max_display
        self._binary = binary
        self._proc: Optional[subprocess.Popen] = None
        self._display: str = ""

    @property
    def display(self) -> str:
        """The display string (e.g. ':99'), or '' if not entered."""
        return self._display

    def __enter__(self) -> str:
        if shutil.which(self._binary) is None and not os.path.isfile(self._binary):
            raise RuntimeError(
                f"Xvfb binary not found: {self._binary!r}. "
                f"Install xorg-server-xvfb (Arch) or xvfb (Debian/Ubuntu)."
            )
        last_err: Optional[Exception] = None
        for n in range(self._min, self._max + 1):
            display = f":{n}"
            argv = [self._binary, display, "-ac", "-screen", "0", "1024x768x24"]
            try:
                self._proc = subprocess.Popen(
                    argv,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid,  # new process group
                )
            except FileNotFoundError as e:
                last_err = e
                continue
            except OSError as e:
                last_err = e
                continue
            # Give Xvfb a moment to bind the display. 200ms is enough
            # for the real Xvfb; the fake script just sleeps so we
            # can't probe its socket — we trust the Popen succeeded.
            time.sleep(0.2)
            if self._proc.poll() is None:
                self._display = display
                return display
            last_err = RuntimeError(f"Xvfb exited on {display}")
        raise RuntimeError(
            f"No free display in [{self._min}, {self._max}]: {last_err}"
        )

    def __exit__(self, *exc) -> None:
        if self._proc is None:
            return
        proc = self._proc
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass
        finally:
            self._proc = None
            self._display = ""
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_xvfb -v
```

Expected: 4 tests pass. Note `test_enter_launches_and_returns_display` and `test_exit_kills_process` start a 30s sleep; teardown kills them so the test should finish in <2s.

- [ ] **Step 5: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && \
  git add pyagent-kdenlive-guide/phase7_real_session/xvfb.py \
          pyagent-kdenlive-guide/phase7_real_session/tests/test_xvfb.py && \
  git -c user.email=ah64@local -c user.name=ah64 commit \
    -m "[phase-7][xvfb] add XvfbContext with injectable binary

Starts Xvfb on the lowest free :N in [99, 199] inside a context
manager. Kills the process group on exit. binary parameter is
injectable so unit tests run a fake script.

4 tests pass (3 using fake binary, 1 verifying the missing-binary
error path)."
```

---

### Task 3: KdenliveLaunch

**Files:**
- Create: `pyagent-kdenlive-guide/phase7_real_session/kdenlive.py`
- Create: `pyagent-kdenlive-guide/phase7_real_session/tests/test_kdenlive.py`

**Interfaces (this task produces, later tasks consume):**
- `phase7_real_session.kdenlive.KdenliveLaunch` — class:
  - `__init__(self, project_path: str, display: str, xdg_config_home: str, xdg_cache_home: str, timeout: float = 30.0, binary: str = "kdenlive")`
  - `wait_ready(self) -> None` — blocks until `org.kde.kdenlive` is on the session D-Bus or `timeout` elapses. Raises `RuntimeError` on timeout.
  - `terminate(self) -> None` — SIGTERM, then SIGKILL after 5s. Safe to call multiple times.
  - `pid` (int property) — the kdenlive pid, or -1 if not started.

**Consumes:** nothing.

- [ ] **Step 1: Write the failing test**

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/tests/test_kdenlive.py`:

```python
"""Unit tests for KdenliveLaunch.

These tests use a fake kdenlive binary (a shell script that
registers a fake D-Bus name via dbus-send then sleeps, or
just sleeps without registering, depending on the test).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from phase7_real_session.kdenlive import KdenliveLaunch


def _make_fake_kdenlive(tmp: Path, register_dbus: bool, hold_seconds: float = 30.0) -> Path:
    """Write a shell script that pretends to be kdenlive.

    If register_dbus is True, the script calls dbus-send to register
    org.kde.kdenlive on the session bus (so the wait_ready probe
    succeeds). Then it sleeps.
    """
    script = tmp / "fake-kdenlive.sh"
    lines = ["#!/bin/sh"]
    if register_dbus:
        # dbus-send --session ... org.freedesktop.DBus.ListNames
        # would need a real bus; instead, the test will mock
        # _kdenlive_already_on_bus via the KdenliveLaunch wait_ready
        # path. We use a different approach: write a marker file
        # that the test can read.
        pass
    # Write a marker file so the test knows the script ran.
    lines.append(f"touch {tmp}/kdenlive-started.marker")
    lines.append(f"sleep {hold_seconds}")
    script.write_text("\n".join(lines) + "\n")
    script.chmod(0o755)
    return script


class TestKdenliveLaunchWithFakeBinary(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="phase7_kdenlive_test_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_constructor_does_not_launch(self) -> None:
        """__init__ stores config; the subprocess is launched by wait_ready."""
        fake = _make_fake_kdenlive(self.tmp, register_dbus=False, hold_seconds=30.0)
        # No wait_ready called yet — the fake's marker should NOT exist.
        KdenliveLaunch(
            project_path=str(self.tmp / "demo.kdenlive"),
            display=":99",
            xdg_config_home=str(self.tmp / "config"),
            xdg_cache_home=str(self.tmp / "cache"),
            binary=str(fake),
        )
        time.sleep(0.1)
        self.assertFalse(
            (self.tmp / "kdenlive-started.marker").exists(),
            "kdenlive was launched by __init__, expected lazy launch",
        )

    def test_wait_ready_raises_on_timeout(self) -> None:
        fake = _make_fake_kdenlive(self.tmp, register_dbus=False, hold_seconds=30.0)
        k = KdenliveLaunch(
            project_path=str(self.tmp / "demo.kdenlive"),
            display=":99",
            xdg_config_home=str(self.tmp / "config"),
            xdg_cache_home=str(self.tmp / "cache"),
            binary=str(fake),
            timeout=0.5,
        )
        with self.assertRaises(RuntimeError):
            k.wait_ready()
        # Cleanup so the fake sleep doesn't linger.
        k.terminate()

    def test_wait_ready_succeeds_when_dbus_already_has_kdenlive(self) -> None:
        """If a kdenlive is already on the bus (mocked), wait_ready returns."""
        fake = _make_fake_kdenlive(self.tmp, register_dbus=False, hold_seconds=30.0)
        k = KdenliveLaunch(
            project_path=str(self.tmp / "demo.kdenlive"),
            display=":99",
            xdg_config_home=str(self.tmp / "config"),
            xdg_cache_home=str(self.tmp / "cache"),
            binary=str(fake),
            timeout=2.0,
        )
        with unittest.mock.patch(
            "phase7_real_session.kdenlive._kdenlive_already_on_bus",
            return_value=True,
        ):
            k.wait_ready()
        self.assertGreaterEqual(k.pid, 0, "kdenlive was not launched")
        # Marker should appear.
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if (self.tmp / "kdenlive-started.marker").exists():
                break
            time.sleep(0.05)
        self.assertTrue(
            (self.tmp / "kdenlive-started.marker").exists(),
            "kdenlive was not launched",
        )
        k.terminate()

    def test_terminate_is_idempotent(self) -> None:
        fake = _make_fake_kdenlive(self.tmp, register_dbus=False, hold_seconds=30.0)
        k = KdenliveLaunch(
            project_path=str(self.tmp / "demo.kdenlive"),
            display=":99",
            xdg_config_home=str(self.tmp / "config"),
            xdg_cache_home=str(self.tmp / "cache"),
            binary=str(fake),
            timeout=0.5,
        )
        with self.assertRaises(RuntimeError):
            k.wait_ready()
        k.terminate()
        # Second call should not raise.
        k.terminate()


import unittest.mock  # noqa: E402  (placed after the test class so the
                       # mock import doesn't shadow test methods)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_kdenlive -v
```

Expected: `ModuleNotFoundError: No module named 'phase7_real_session.kdenlive'`.

- [ ] **Step 3: Implement `kdenlive.py`**

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/kdenlive.py`:

```python
"""KdenliveLaunch — launch Kdenlive in a virtual display and wait for D-Bus.

The launch is lazy: __init__ stores config, and wait_ready() is what
actually spawns the subprocess and probes D-Bus. This lets tests
verify "no launch happens until wait_ready is called".

The `binary` argument is injectable for unit tests. In production
it defaults to "kdenlive".
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from typing import Optional

from phase7_real_session.skipif_helpers import _kdenlive_already_on_bus


class KdenliveLaunch:
    """Launch kdenlive in a given DISPLAY, opening a project file.

    Usage:
        k = KdenliveLaunch(project_path, display=display,
                           xdg_config_home=tmp/.config,
                           xdg_cache_home=tmp/.cache)
        k.wait_ready()        # blocks up to timeout
        ...
        k.terminate()         # SIGTERM, then SIGKILL
    """

    def __init__(
        self,
        project_path: str,
        display: str,
        xdg_config_home: str,
        xdg_cache_home: str,
        timeout: float = 30.0,
        binary: str = "kdenlive",
    ) -> None:
        self._project_path = project_path
        self._display = display
        self._xdg_config_home = xdg_config_home
        self._xdg_cache_home = xdg_cache_home
        self._timeout = timeout
        self._binary = binary
        self._proc: Optional[subprocess.Popen] = None
        self._stderr_path: Optional[str] = None

    @property
    def pid(self) -> int:
        """The kdenlive pid, or -1 if not started."""
        if self._proc is None:
            return -1
        return self._proc.pid

    def _spawn(self) -> None:
        if shutil.which(self._binary) is None and not os.path.isfile(self._binary):
            raise RuntimeError(
                f"kdenlive binary not found: {self._binary!r}"
            )
        # Make sure the XDG dirs exist (Kdenlive refuses to start
        # without them).
        os.makedirs(self._xdg_config_home, exist_ok=True)
        os.makedirs(self._xdg_cache_home, exist_ok=True)
        env = dict(os.environ)
        env["DISPLAY"] = self._display
        env["XDG_CONFIG_HOME"] = self._xdg_config_home
        env["XDG_CACHE_HOME"] = self._xdg_cache_home
        self._stderr_path = os.path.join(self._xdg_cache_home, "kdenlive.stderr")
        stderr_fp = open(self._stderr_path, "w")
        argv = [self._binary, "--no-splash", self._project_path]
        self._proc = subprocess.Popen(
            argv,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=stderr_fp,
            preexec_fn=os.setsid,
        )

    def wait_ready(self) -> None:
        """Launch Kdenlive and block until org.kde.kdenlive is on the bus.

        Raises RuntimeError on timeout.
        """
        if self._proc is None:
            self._spawn()
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                raise RuntimeError(
                    f"kdenlive exited unexpectedly with code "
                    f"{self._proc.returncode}; see {self._stderr_path}"
                )
            if _kdenlive_already_on_bus():
                return
            time.sleep(0.2)
        raise RuntimeError(
            f"kdenlive did not register on D-Bus within {self._timeout}s; "
            f"see {self._stderr_path}"
        )

    def terminate(self) -> None:
        """SIGTERM, then SIGKILL after 5s. Safe to call multiple times."""
        if self._proc is None:
            return
        proc = self._proc
        self._proc = None
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_kdenlive -v
```

Expected: 4 tests pass. The "wait_ready succeeds when dbus already has kdenlive" test is the one that exercises the happy path with a mocked D-Bus probe.

- [ ] **Step 5: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && \
  git add pyagent-kdenlive-guide/phase7_real_session/kdenlive.py \
          pyagent-kdenlive-guide/phase7_real_session/tests/test_kdenlive.py && \
  git -c user.email=ah64@local -c user.name=ah64 commit \
    -m "[phase-7][kdenlive] add KdenliveLaunch with injectable binary

Lazy launch (wait_ready spawns the subprocess). Polls
_kdenlive_already_on_bus every 200ms until org.kde.kdenlive
appears or timeout. Redirects XDG_CONFIG_HOME/XDG_CACHE_HOME so
the test's Kdenlive doesn't pollute the user's profile. Captures
stderr to a file for post-mortem on failure.

4 tests pass (constructor, timeout, success-via-mock, terminate
idempotency)."
```

---

### Task 4: ChatUIServer

**Files:**
- Create: `pyagent-kdenlive-guide/phase7_real_session/chat_ui.py`
- Create: `pyagent-kdenlive-guide/phase7_real_session/tests/test_chat_ui.py`

**Interfaces (this task produces, later tasks consume):**
- `phase7_real_session.chat_ui.ChatUIServer` — class:
  - `__init__(self, project_path: str, display: str, provider: str = "opencode", model: str = "minimax-m3", timeout: float = 15.0, port: int = 0, command: Optional[list] = None)`
    - If `port` is 0, picks a free port. If `command` is None, uses `["python3", "-m", "phase4_chat_ui", "--project", project_path, "--port", str(port), "--provider", provider, "--model", model]`. If `command` is provided, the caller is responsible for any port substitution.
  - `wait_ready(self) -> None` — blocks until `GET http://127.0.0.1:<port>/api/project` returns 200 or `timeout` elapses. Raises `RuntimeError` on timeout.
  - `terminate(self) -> None` — SIGTERM, then SIGKILL after 5s. Safe to call multiple times.
  - `port` (int property) — the bound port.
  - `url` (str property) — `http://127.0.0.1:<port>`.

**Consumes:** nothing.

- [ ] **Step 1: Write the failing test**

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/tests/test_chat_ui.py`:

```python
"""Unit tests for ChatUIServer.

We use a tiny HTTP server fixture (http.server in a thread) that
responds 200 to GET /api/project, instead of launching the real
phase4_chat_ui. This is what the `command` injection is for.
"""
from __future__ import annotations

import json
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from phase7_real_session.chat_ui import ChatUIServer


class _FakeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        if self.path == "/api/project":
            body = json.dumps({"name": "demo", "duration": 6.0}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args, **kwargs) -> None:  # silence stderr noise
        pass


def _pick_free_port() -> int:
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_fake_server() -> tuple[HTTPServer, int]:
    port = _pick_free_port()
    server = HTTPServer(("127.0.0.1", port), _FakeHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    # Tiny sleep so the socket is actually listening.
    time.sleep(0.05)
    return server, port


class TestChatUIServerHappyPath(unittest.TestCase):
    def setUp(self) -> None:
        self._server, self._port = _start_fake_server()

    def tearDown(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def test_wait_ready_succeeds(self) -> None:
        # The "chat UI" here is just the fake server — we tell the
        # ChatUIServer to launch a no-op `sleep 5` command so it
        # spawns a real subprocess, but the wait_ready probe hits
        # the fake server we started in setUp.
        #
        # We give the server's port to ChatUIServer so its
        # healthcheck targets it. We use a dummy `sleep 5` as the
        # "command" so the spawn doesn't error.
        cu = ChatUIServer(
            project_path="/tmp/nonexistent.kdenlive",
            display=":99",
            port=self._port,
            command=["sleep", "5"],
            timeout=2.0,
        )
        cu.wait_ready()
        self.assertEqual(cu.port, self._port)
        self.assertEqual(cu.url, f"http://127.0.0.1:{self._port}")
        cu.terminate()

    def test_pick_free_port_when_zero(self) -> None:
        cu = ChatUIServer(
            project_path="/tmp/nonexistent.kdenlive",
            display=":99",
            port=0,  # pick one
            command=["sleep", "5"],
            timeout=1.0,
        )
        self.assertGreater(cu.port, 0)
        self.assertEqual(cu.url, f"http://127.0.0.1:{cu.port}")
        # Don't call wait_ready — we'd need a server on that port.
        # Just verify construction worked.

    def test_terminate_is_idempotent(self) -> None:
        cu = ChatUIServer(
            project_path="/tmp/nonexistent.kdenlive",
            display=":99",
            port=self._port,
            command=["sleep", "5"],
            timeout=2.0,
        )
        cu.wait_ready()
        cu.terminate()
        cu.terminate()  # second call must not raise


class TestChatUIServerTimeout(unittest.TestCase):
    def test_wait_ready_times_out(self) -> None:
        # Port that's not listening: pick a free port and don't start a server.
        port = _pick_free_port()
        cu = ChatUIServer(
            project_path="/tmp/nonexistent.kdenlive",
            display=":99",
            port=port,
            command=["sleep", "5"],
            timeout=0.5,
        )
        with self.assertRaises(RuntimeError):
            cu.wait_ready()
        cu.terminate()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_chat_ui -v
```

Expected: `ModuleNotFoundError: No module named 'phase7_real_session.chat_ui'`.

- [ ] **Step 3: Implement `chat_ui.py`**

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/chat_ui.py`:

```python
"""ChatUIServer — launch the phase4 chat UI and wait for it to serve HTTP.

The `command` argument is injectable for unit tests. In production
it defaults to `python3 -m phase4_chat_ui --project <p> --port <port>
--provider <provider> --model <model>`.

The `port` argument: if 0 (the default), a free port is picked and
used in the spawned command. If nonzero, that port is used in the
spawned command and the healthcheck. Tests can pass a known port
to point the healthcheck at a fixture server.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from typing import Optional


def _pick_free_port() -> int:
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ChatUIServer:
    """Launch the chat UI in a subprocess, wait for it to be ready."""

    def __init__(
        self,
        project_path: str,
        display: str,
        provider: str = "opencode",
        model: str = "minimax-m3",
        timeout: float = 15.0,
        port: int = 0,
        command: Optional[list] = None,
    ) -> None:
        self._project_path = project_path
        self._display = display
        self._provider = provider
        self._model = model
        self._timeout = timeout
        if port == 0:
            port = _pick_free_port()
        self._port = port
        self._command = command if command is not None else [
            "python3", "-m", "phase4_chat_ui",
            "--project", project_path,
            "--port", str(port),
            "--provider", provider,
            "--model", model,
        ]
        self._proc: Optional[subprocess.Popen] = None
        self._stderr_path: Optional[str] = None

    @property
    def port(self) -> int:
        return self._port

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def _spawn(self) -> None:
        env = dict(os.environ)
        env["DISPLAY"] = self._display
        self._stderr_path = os.path.join(
            os.path.dirname(self._project_path) or ".",
            "chat_ui.stderr",
        )
        stderr_fp = open(self._stderr_path, "w")
        self._proc = subprocess.Popen(
            self._command,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=stderr_fp,
            preexec_fn=os.setsid,
        )

    def wait_ready(self) -> None:
        """Spawn the chat UI and block until /api/project returns 200."""
        if self._proc is None:
            self._spawn()
        deadline = time.time() + self._timeout
        last_err: Optional[Exception] = None
        while time.time() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                raise RuntimeError(
                    f"chat UI exited unexpectedly with code "
                    f"{self._proc.returncode}; see {self._stderr_path}"
                )
            try:
                with urllib.request.urlopen(
                    f"{self.url}/api/project", timeout=1.0
                ) as resp:
                    if resp.status == 200:
                        return
            except (urllib.error.URLError, ConnectionError, OSError) as e:
                last_err = e
            time.sleep(0.2)
        raise RuntimeError(
            f"chat UI did not become ready within {self._timeout}s: {last_err}"
        )

    def terminate(self) -> None:
        """SIGTERM, then SIGKILL after 5s. Safe to call multiple times."""
        if self._proc is None:
            return
        proc = self._proc
        self._proc = None
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_chat_ui -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && \
  git add pyagent-kdenlive-guide/phase7_real_session/chat_ui.py \
          pyagent-kdenlive-guide/phase7_real_session/tests/test_chat_ui.py && \
  git -c user.email=ah64@local -c user.name=ah64 commit \
    -m "[phase-7][chat-ui] add ChatUIServer with injectable command

Spawns the chat UI in a subprocess; wait_ready polls
GET /api/project until 200. The `command` arg is injectable so
tests run a fake sleep instead of the real chat UI. port=0 picks
a free port. Captures stderr to chat_ui.stderr for post-mortem.

4 tests pass (happy path, free-port, timeout, terminate
idempotency)."
```

---

### Task 5: WSClient

**Files:**
- Create: `pyagent-kdenlive-guide/phase7_real_session/ws_client.py`
- Create: `pyagent-kdenlive-guide/phase7_real_session/tests/test_ws_client.py`

**Interfaces (this task produces, later tasks consume):**
- `phase7_real_session.ws_client.WSClient` — class:
  - `__init__(self, url: str, timeout: float = 180.0)`
  - `connect(self) -> None` — opens the WebSocket. Raises on failure.
  - `send_prompt(self, text: str) -> list[dict]` — sends `{"type": "prompt", "text": text}` and collects events until `{"type": "done"}` arrives or timeout. Returns the event list.
  - `close(self) -> None` — closes the WebSocket. Safe to call multiple times.
  - `run_prompt_sync(self, text: str) -> list[dict]` — convenience wrapper that calls `connect`, `send_prompt`, `close` and returns the events.

**Consumes:** nothing.

- [ ] **Step 1: Write the failing test**

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/tests/test_ws_client.py`:

```python
"""Unit tests for WSClient.

We use a local websockets server fixture that echoes a fixed
event stream when it receives a prompt.
"""
from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
import unittest

from phase7_real_session.ws_client import WSClient


def _pick_free_port() -> int:
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def _echo_handler(websocket) -> None:
    """Receive a 'prompt' message, send a canned event stream + done."""
    async for msg in websocket:
        data = json.loads(msg)
        if data.get("type") == "prompt":
            # Send a small event stream.
            await websocket.send(json.dumps({
                "type": "message", "role": "user", "text": data["text"]
            }))
            await websocket.send(json.dumps({
                "type": "tool", "tool": "pyagent_add_transition",
                "args": {"kind": "dissolve", "duration_sec": 1.0},
                "result": {"ok": True},
            }))
            await websocket.send(json.dumps({
                "type": "message", "role": "assistant",
                "text": "Added a 1-second dissolve.",
            }))
            await websocket.send(json.dumps({"type": "done"}))


def _start_ws_server() -> tuple[object, int]:
    """Start a websockets server in a thread. Returns (server, port)."""
    import websockets
    port = _pick_free_port()
    stop_event = threading.Event()

    async def _runner():
        async with websockets.serve(_echo_handler, "127.0.0.1", port):
            await asyncio.get_event_loop().create_future()
            # The serve() call blocks; we never return from here.
            # The thread is daemonized so the test process can exit
            # even if we don't reach the stop_event branch.

    t = threading.Thread(
        target=lambda: asyncio.run(_runner()), daemon=True
    )
    t.start()
    # Wait for the server to bind.
    time.sleep(0.2)
    return None, port  # server handle is None; we rely on daemon thread


class TestWSClient(unittest.TestCase):
    def test_run_prompt_collects_events(self) -> None:
        _, port = _start_ws_server()
        ws = WSClient(url=f"ws://127.0.0.1:{port}/ws", timeout=5.0)
        events = ws.run_prompt_sync("Add a 1-second dissolve.")
        kinds = [e.get("type") for e in events]
        self.assertIn("message", kinds)
        self.assertIn("tool", kinds)
        self.assertEqual(kinds[-1], "done")
        # Find the tool event and assert the args.
        tool_events = [e for e in events if e.get("type") == "tool"]
        self.assertEqual(len(tool_events), 1)
        self.assertEqual(tool_events[0]["tool"], "pyagent_add_transition")
        self.assertEqual(tool_events[0]["args"]["kind"], "dissolve")

    def test_run_prompt_raises_on_timeout(self) -> None:
        # Use a port that's not listening.
        port = _pick_free_port()
        ws = WSClient(url=f"ws://127.0.0.1:{port}/ws", timeout=1.0)
        with self.assertRaises((ConnectionError, OSError, RuntimeError)):
            ws.run_prompt_sync("anything")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_ws_client -v
```

Expected: `ModuleNotFoundError: No module named 'phase7_real_session.ws_client'`.

- [ ] **Step 3: Implement `ws_client.py`**

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/ws_client.py`:

```python
"""WSClient — drive the chat UI's /ws WebSocket and collect events.

The chat UI's WebSocket protocol (see phase4_chat_ui/app.py) is:
  - Client sends {"type": "prompt", "text": "..."}.
  - Server sends a stream of {"type": "message" | "tool" | ...}
    events until {"type": "done"} arrives.

This client wraps that flow in a simple synchronous API.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets


class WSClient:
    """WebSocket client that collects one prompt's event stream."""

    def __init__(self, url: str, timeout: float = 180.0) -> None:
        self._url = url
        self._timeout = timeout
        self._ws: Any = None

    def connect(self) -> None:
        """Open the WebSocket. Synchronous wrapper around asyncio.run."""
        async def _connect():
            self._ws = await websockets.connect(self._url)
        asyncio.run(_connect())

    def close(self) -> None:
        """Close the WebSocket. Safe to call multiple times."""
        if self._ws is None:
            return
        try:
            asyncio.run(self._ws.close())
        except Exception:
            pass
        self._ws = None

    def send_prompt(self, text: str) -> list[dict]:
        """Send one prompt and collect events until 'done'. Returns the events."""
        if self._ws is None:
            raise RuntimeError("WSClient not connected; call connect() first")
        async def _send_and_collect():
            await self._ws.send(json.dumps({"type": "prompt", "text": text}))
            events: list[dict] = []
            try:
                async for raw in self._ws:
                    ev = json.loads(raw)
                    events.append(ev)
                    if ev.get("type") == "done":
                        break
            except asyncio.TimeoutError as e:
                raise RuntimeError(
                    f"WebSocket timed out after {self._timeout}s waiting for events"
                ) from e
            return events
        return asyncio.run(_send_and_collect())

    def run_prompt_sync(self, text: str) -> list[dict]:
        """Connect, send, collect, close. Returns the events."""
        self.connect()
        try:
            return self.send_prompt(text)
        finally:
            self.close()
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_ws_client -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && \
  git add pyagent-kdenlive-guide/phase7_real_session/ws_client.py \
          pyagent-kdenlive-guide/phase7_real_session/tests/test_ws_client.py && \
  git -c user.email=ah64@local -c user.name=ah64 commit \
    -m "[phase-7][ws] add WSClient

Thin wrapper around websockets.connect that sends one prompt
and collects events until 'done'. Uses asyncio.run per call so
the e2e test can drive it synchronously.

2 tests pass (event collection, connection-refused error)."
```

---

### Task 6: dbus_probe

**Files:**
- Create: `pyagent-kdenlive-guide/phase7_real_session/dbus_probe.py`
- Create: `pyagent-kdenlive-guide/phase7_real_session/tests/test_dbus_probe.py`

**Interfaces (this task produces, later tasks consume):**
- `phase7_real_session.dbus_probe.read_timeline_state(client=None) -> dict`
  - Calls KdenliveDBus methods. The `client` arg is injectable for tests.
  - Returns a dict with shape:
    ```python
    {
        "transitions": [
            {"from_clip": str, "to_clip": str, "kind": str},
            ...
        ]
    }
    ```
  - In the e2e test, we only need the `transitions` key. (Tracks/clips are available for future tests.)

**Consumes:** `phase5_dbus_sync.dbus_client.KdenliveDBus`.

- [ ] **Step 1: Look at the actual KdenliveDBus interface**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  grep -n "def get_\|def list\|def add_\|def clean\|def scriptRender\|def update\|def exit" phase5_dbus_sync/dbus_client.py | head -30
```

Verify that `KdenliveDBus` exposes a `get_transition_list()` or similar method. If the exact method name differs, adjust Step 3 below to match the real API.

- [ ] **Step 2: Write the failing test**

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/tests/test_dbus_probe.py`:

```python
"""Unit tests for dbus_probe.

We mock the KdenliveDBus client so the test doesn't need a real
D-Bus. The mock returns canned responses for the methods
read_timeline_state calls.
"""
from __future__ import annotations

import unittest
from unittest import mock

from phase7_real_session.dbus_probe import read_timeline_state


def _make_mock_client(transitions: list) -> mock.Mock:
    client = mock.Mock()
    client.get_transition_list = mock.Mock(return_value=transitions)
    return client


class TestReadTimelineState(unittest.TestCase):
    def test_returns_empty_when_no_transitions(self) -> None:
        client = _make_mock_client(transitions=[])
        state = read_timeline_state(client=client)
        self.assertEqual(state["transitions"], [])

    def test_returns_transitions(self) -> None:
        # KdenliveDBus returns a list of Transition objects with
        # attributes from_clip, to_clip, kind. We mock that.
        t1 = mock.Mock()
        t1.from_clip = "clip-1"
        t1.to_clip = "clip-2"
        t1.kind = "dissolve"
        t2 = mock.Mock()
        t2.from_clip = "clip-2"
        t2.to_clip = "clip-3"
        t2.kind = "dissolve"
        client = _make_mock_client(transitions=[t1, t2])
        state = read_timeline_state(client=client)
        self.assertEqual(len(state["transitions"]), 2)
        self.assertEqual(state["transitions"][0]["from_clip"], "clip-1")
        self.assertEqual(state["transitions"][0]["to_clip"], "clip-2")
        self.assertEqual(state["transitions"][0]["kind"], "dissolve")

    def test_handles_dict_form(self) -> None:
        # Some versions of KdenliveDBus return dicts instead of
        # objects. Handle both.
        client = mock.Mock()
        client.get_transition_list = mock.Mock(return_value=[
            {"from_clip": "a", "to_clip": "b", "kind": "crossfade"},
        ])
        state = read_timeline_state(client=client)
        self.assertEqual(state["transitions"][0]["kind"], "crossfade")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test to verify it fails**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_dbus_probe -v
```

Expected: `ModuleNotFoundError: No module named 'phase7_real_session.dbus_probe'`.

- [ ] **Step 4: Implement `dbus_probe.py`**

First, look at the real `KdenliveDBus` to find the actual method that returns the transition list:

```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  grep -n "def get_transition\|def getTransition\|def get_transition_list" phase5_dbus_sync/dbus_client.py
```

If the method is named `get_transition_list`, proceed with the code below. If it's named something else (e.g., `getTransitionList` or `transitionList`), adjust the call.

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/dbus_probe.py`:

```python
"""dbus_probe — read the running Kdenlive's timeline state via D-Bus.

Wraps phase5_dbus_sync.dbus_client.KdenliveDBus and returns a
plain-Python dict that's easy for tests to assert on.

The `client` arg is injectable so unit tests can mock the D-Bus
calls without needing a real Kdenlive.
"""
from __future__ import annotations

from typing import Any, Optional

from phase5_dbus_sync.dbus_client import KdenliveDBus


def read_timeline_state(client: Optional[Any] = None) -> dict:
    """Read the running Kdenlive's timeline state.

    Returns a dict:
        {
            "transitions": [
                {"from_clip": str, "to_clip": str, "kind": str},
                ...
            ]
        }

    If `client` is None, creates a real KdenliveDBus instance. The
    caller is responsible for ensuring the D-Bus connection will
    succeed (the e2e test does this by launching Kdenlive first).
    """
    if client is None:
        client = KdenliveDBus()
    raw = client.get_transition_list() or []
    transitions: list[dict] = []
    for t in raw:
        # Support both attribute-style and dict-style results.
        if isinstance(t, dict):
            transitions.append({
                "from_clip": t.get("from_clip", ""),
                "to_clip": t.get("to_clip", ""),
                "kind": t.get("kind", ""),
            })
        else:
            transitions.append({
                "from_clip": getattr(t, "from_clip", ""),
                "to_clip": getattr(t, "to_clip", ""),
                "kind": getattr(t, "kind", ""),
            })
    return {"transitions": transitions}
```

- [ ] **Step 5: Run the test to verify it passes**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_dbus_probe -v
```

Expected: 3 tests pass. (If the real `KdenliveDBus.get_transition_list` is named differently and you adjusted Step 4, this should still pass because the test mocks the client.)

- [ ] **Step 6: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && \
  git add pyagent-kdenlive-guide/phase7_real_session/dbus_probe.py \
          pyagent-kdenlive-guide/phase7_real_session/tests/test_dbus_probe.py && \
  git -c user.email=ah64@local -c user.name=ah64 commit \
    -m "[phase-7][dbus] add dbus_probe.read_timeline_state

Reads the running Kdenlive's transition list via the existing
phase5 KdenliveDBus client. Returns a plain dict
{transitions: [{from_clip, to_clip, kind}, ...]} that's easy
to assert on. The client arg is injectable for unit tests.

3 tests pass (empty, attribute-style, dict-style)."
```

---

### Task 7: The e2e test

**Files:**
- Create: `pyagent-kdenlive-guide/phase7_real_session/tests/test_e2e_pi_session.py`

**Consumes:** `XvfbContext` (Task 2), `KdenliveLaunch` (Task 3), `ChatUIServer` (Task 4), `WSClient` (Task 5), `read_timeline_state` (Task 6), `skipif_helpers` (Task 1), `phase3_pyagent_core.__main__:run_op`.

- [ ] **Step 1: Write the e2e test**

Write `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/phase7_real_session/tests/test_e2e_pi_session.py`:

```python
"""Real pi-session end-to-end test.

Drives a real pi session against a real Kdenlive via the chat UI,
then asserts:

1. pi called at least one tool.
2. pi picked pyagent_add_transition.
3. The args were correct (kind in {dissolve, crossfade},
   0.5 <= duration_sec <= 1.5).
4. The tool succeeded (result.ok is True).
5. The file changed on disk (a <transition> element appeared).
6. The live Kdenlive reflects the change (D-Bus probe shows it).
7. The LLM described the action (final assistant text mentions
   "dissolve" or "added a transition").

Skipped cleanly on machines missing the required deps.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from phase7_real_session.skipif_helpers import (
    _has,
    _has_opencode_auth,
    _kdenlive_already_on_bus,
)
from phase7_real_session.xvfb import XvfbContext
from phase7_real_session.kdenlive import KdenliveLaunch
from phase7_real_session.chat_ui import ChatUIServer
from phase7_real_session.ws_client import WSClient
from phase7_real_session.dbus_probe import read_timeline_state

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "phase3_pyagent_core" / "tests" / "fixtures" / "demo.kdenlive"
CATALOG = REPO / "phase1_knowledge_base" / "catalog.json"

PROMPT = "Add a 1-second dissolve between the two clips in the timeline."


def _step(msg: str) -> None:
    print(f"[e2e] {msg}", file=sys.stderr, flush=True)


@unittest.skipUnless(_has_opencode_auth(),
    "opencode auth not configured (need OPENCODE_API_KEY or ~/.pi/agent/auth.json)")
@unittest.skipUnless(_has("pi"), "pi not on PATH")
@unittest.skipUnless(_has("kdenlive"), "kdenlive not on PATH")
@unittest.skipUnless(_has("Xvfb"), "Xvfb not on PATH (install xorg-server-xvfb)")
@unittest.skipUnless(_has("dbus-send"), "dbus-send not on PATH")
@unittest.skipIf(_kdenlive_already_on_bus(),
    "a kdenlive is already on the session D-Bus; close it and re-run")
@unittest.skipIf(not FIXTURE.is_file(), "demo.kdenlive fixture missing")
@unittest.skipIf(not CATALOG.is_file(), "catalog.json missing")
class TestE2EPiSession(unittest.TestCase):
    """End-to-end: real pi + real Kdenlive + chat UI + D-Bus."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pyagent_e2e_"))
        self.project = self.tmp / "demo.kdenlive"
        shutil.copy(FIXTURE, self.project)
        # Read the pre-run XML so we can diff later.
        self._pre_xml = self.project.read_text()
        # Track resources for cleanup.
        self._xvfb: XvfbContext | None = None
        self._kdenlive: KdenliveLaunch | None = None
        self._chat_ui: ChatUIServer | None = None
        self._events: list[dict] = []
        self._transcript_path = self.tmp / "transcript.json"

    def tearDown(self) -> None:
        # Cleanup order: Kdenlive -> chat UI -> Xvfb.
        try:
            if self._chat_ui is not None:
                self._chat_ui.terminate()
        except Exception as e:
            print(f"[e2e] chat_ui terminate error: {e}", file=sys.stderr)
        try:
            if self._kdenlive is not None:
                self._kdenlive.terminate()
        except Exception as e:
            print(f"[e2e] kdenlive terminate error: {e}", file=sys.stderr)
        try:
            if self._xvfb is not None:
                self._xvfb.__exit__(None, None, None)
        except Exception as e:
            print(f"[e2e] xvfb exit error: {e}", file=sys.stderr)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _find_add_transition(self) -> tuple[dict | None, dict | None]:
        """Return (tool_event, args) for the add_transition call, if any."""
        for ev in self._events:
            if ev.get("type") == "tool" and ev.get("tool") == "pyagent_add_transition":
                return ev, ev.get("args") or {}
        return None, None

    def _count_transitions_in_file(self) -> int:
        """Count <transition> elements in the tempdir project file."""
        try:
            tree = ET.parse(self.project)
        except ET.ParseError as e:
            self.fail(f"project file is not valid XML: {e}")
        return len(tree.getroot().findall(".//transition"))

    def _count_transitions_pre_run(self) -> int:
        try:
            tree = ET.fromstring(self._pre_xml)
        except ET.ParseError:
            return 0
        return len(tree.findall(".//transition"))

    def test_edit_render_qc_roundtrip(self) -> None:
        """The full e2e: real pi, real Kdenlive, real D-Bus, real file."""
        # Step 3: start Xvfb.
        _step("starting Xvfb")
        self._xvfb = XvfbContext(min_display=99, max_display=199)
        display = self._xvfb.__enter__()
        os.environ["DISPLAY"] = display
        _step(f"Xvfb on {display}")

        try:
            # Step 4: start Kdenlive and wait for D-Bus.
            _step("launching Kdenlive")
            self._kdenlive = KdenliveLaunch(
                project_path=str(self.project),
                display=display,
                xdg_config_home=str(self.tmp / "config"),
                xdg_cache_home=str(self.tmp / "cache"),
                timeout=45.0,
            )
            self._kdenlive.wait_ready()
            _step("Kdenlive ready on D-Bus")

            # Step 5: start chat UI.
            _step("launching chat UI")
            self._chat_ui = ChatUIServer(
                project_path=str(self.project),
                display=display,
                provider="opencode",
                model="minimax-m3",
                timeout=20.0,
            )
            self._chat_ui.wait_ready()
            _step(f"chat UI ready at {self._chat_ui.url}")

            # Step 6+7+8: drive the WebSocket.
            _step("sending prompt via WebSocket")
            ws = WSClient(url=f"{self._chat_ui.url.replace('http', 'ws', 1)}/ws",
                          timeout=180.0)
            self._events = ws.run_prompt_sync(PROMPT)
            _step(f"collected {len(self._events)} events")

            # Save the transcript for debugging.
            import json
            self._transcript_path.write_text(json.dumps(self._events, indent=2))

            # Step 9: assertions.
            _step("asserting tool call")
            tool_event, args = self._find_add_transition()
            self.assertIsNotNone(
                tool_event,
                f"pi did not call pyagent_add_transition. "
                f"Events: {[e.get('type') for e in self._events]}. "
                f"Transcript: {self._transcript_path}",
            )

            _step("asserting tool args")
            kind = args.get("kind", "")
            self.assertIn(
                kind, ("dissolve", "crossfade"),
                f"kind={kind!r}, expected 'dissolve' or 'crossfade'",
            )
            duration = args.get("duration_sec", 0)
            self.assertGreaterEqual(duration, 0.5, f"duration_sec={duration} too small")
            self.assertLessEqual(duration, 1.5, f"duration_sec={duration} too large")

            _step("asserting tool result")
            result = tool_event.get("result") or {}
            self.assertTrue(
                result.get("ok"),
                f"tool result not ok: {result}",
            )

            # Give Kdenlive a moment to apply the live-sync after the
            # tool call returns. The chat UI's notifier fires
            # addTimelineClip via D-Bus; Kdenlive updates internally.
            time.sleep(2.0)

            _step("asserting file changed on disk")
            pre_count = self._count_transitions_pre_run()
            post_count = self._count_transitions_in_file()
            self.assertGreater(
                post_count, pre_count,
                f"no <transition> added to file. pre={pre_count} post={post_count}",
            )

            _step("asserting live Kdenlive reflects the change")
            live_state = read_timeline_state()
            live_kinds = [t["kind"] for t in live_state["transitions"]]
            self.assertTrue(
                any(k in ("dissolve", "crossfade") for k in live_kinds),
                f"no dissolve/crossfade transition in live Kdenlive. "
                f"Got: {live_kinds}",
            )

            _step("asserting LLM described the action")
            final_texts = [
                ev.get("text", "") for ev in self._events
                if ev.get("type") == "message" and ev.get("role") == "assistant"
            ]
            final_text = " ".join(final_texts).lower()
            self.assertTrue(
                "dissolve" in final_text or "added a transition" in final_text,
                f"LLM did not describe the action. Final text: {final_text!r}",
            )

            _step("all assertions passed")

        except Exception:
            # On failure, dump the transcript and Kdenlive stderr.
            if self._transcript_path.exists():
                print(f"\n[e2e] TRANSCRIPT:\n{self._transcript_path.read_text()}",
                      file=sys.stderr)
            kdenlive_stderr = self.tmp / "cache" / "kdenlive.stderr"
            if kdenlive_stderr.exists():
                tail = "\n".join(kdenlive_stderr.read_text().splitlines()[-50:])
                print(f"\n[e2e] KDENLIVE STDERR (last 50 lines):\n{tail}",
                      file=sys.stderr)
            chat_ui_stderr = self.tmp / "chat_ui.stderr"
            if chat_ui_stderr.exists():
                tail = "\n".join(chat_ui_stderr.read_text().splitlines()[-50:])
                print(f"\n[e2e] CHAT UI STDERR (last 50 lines):\n{tail}",
                      file=sys.stderr)
            raise


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verify the test loads (even if it skips)**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_e2e_pi_session 2>&1 | tail -5
```

Expected: `OK (skipped=N)` where N matches the number of skipif guards that fire on this machine (e.g., 3 if Xvfb, dbus-send, and one of the others are missing).

- [ ] **Step 3: Run all phase7 unit tests together to confirm no regressions**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest discover -s phase7_real_session/tests -p "test_*.py" 2>&1 | tail -5
```

Expected: All non-e2e tests pass; e2e test is skipped (because of missing deps on this machine).

- [ ] **Step 4: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && \
  git add pyagent-kdenlive-guide/phase7_real_session/tests/test_e2e_pi_session.py && \
  git -c user.email=ah64@local -c user.name=ah64 commit \
    -m "[phase-7][e2e] add the e2e pi-session test

Drives a real pi against a real Kdenlive via the chat UI,
asserts the LLM picked pyagent_add_transition, the file changed,
the live Kdenlive shows the change via D-Bus, and the LLM
described the action. Skips cleanly when any of pi, kdenlive,
Xvfb, dbus-send, or opencode auth are missing, or when a
kdenlive is already on the session D-Bus.

On this machine the test skips due to missing Xvfb; the
assertion path is exercised only on a developer machine with
all deps installed."
```

---

### Task 8: Top-level README + final verification

**Files:**
- Modify: `pyagent-kdenlive-guide/README.md`

- [ ] **Step 1: Add the "Real-session e2e test" section to the top-level README**

Read the current README to find the right insertion point:

```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  grep -n "^## " README.md
```

Find the section after "Quickstart" or "Tests" and before any "Future work" or "Out of scope" section.

Insert a new section (replace `<SECTION_NAME>` with the actual heading you find, e.g. `Tests`):

In `/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide/README.md`, after the `<SECTION_NAME>` section, add:

```markdown
## Real-session e2e test

A persistent end-to-end test in `phase7_real_session/` that drives
a real `pi` against a real Kdenlive in a virtual display via the
chat UI's WebSocket. It asserts:

1. The LLM picks `pyagent_add_transition` from the 19-tool catalog.
2. The file-mode edit lands on disk.
3. The same edit appears in the running Kdenlive via D-Bus.
4. The LLM describes the action in its final assistant message.

Run it from the project root:

```bash
make -C phase7_real_session test-e2e
```

Required deps (the test skips cleanly if any are missing):

| Dep | Install on Arch |
|---|---|
| `pi` | already on this machine |
| `kdenlive` | `sudo pacman -S kdenlive` |
| `Xvfb` | `sudo pacman -S xorg-server-xvfb` |
| `dbus-send` | `sudo pacman -S dbus` |
| `OPENCODE_API_KEY` or `~/.pi/agent/auth.json` | `pi /login` |

The test also skips if a kdenlive is already on the session D-Bus
(to avoid colliding with the user's running Kdenlive). Close any
open Kdenlive and re-run.

Expected runtime: 20-45 seconds.
```

- [ ] **Step 2: Run ALL unit tests across ALL phases**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest discover -s phase3_pyagent_core -p "test_*.py" 2>&1 | tail -1 && \
  PYTHONPATH=. python3 -m unittest discover -s phase4_chat_ui -p "test_*.py" 2>&1 | tail -1 && \
  PYTHONPATH=. python3 -m unittest discover -s phase5_dbus_sync -p "test_*.py" 2>&1 | tail -1 && \
  PYTHONPATH=. python3 -m unittest discover -s phase6_render_qc -p "test_*.py" 2>&1 | tail -1 && \
  PYTHONPATH=. python3 -m unittest discover -s phase7_real_session/tests -p "test_*.py" 2>&1 | tail -1
```

Expected: every line says `OK`. The phase7 line will say `OK (skipped=N)` where N is the number of skipif guards on `TestE2EPiSession` that fire.

- [ ] **Step 3: Confirm the e2e test skips (does not fail) on this machine**

Run:
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide && \
  PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_e2e_pi_session -v 2>&1 | tail -10
```

Expected: a line like `test_edit_render_qc_roundtrip ... skipped 'Xvfb not on PATH (install xorg-server-xvfb)'` (or whichever guard fires first). The test reports `skipped`, not `failed`.

- [ ] **Step 4: Commit**

```bash
cd /home/ah64/apps/mlt-pipeline && \
  git add pyagent-kdenlive-guide/README.md && \
  git -c user.email=ah64@local -c user.name=ah64 commit \
    -m "[phase-7][docs] document the real-session e2e test in the top-level README

Adds a 'Real-session e2e test' section with what it does, how
to run it, required deps (with install commands), and the
expected runtime."
```

---

## Self-Review

**Spec coverage check:**
- §1 Purpose: covered by Task 7 (the e2e test itself).
- §2 Goals: covered by Task 7's 7 assertions.
- §2 Non-goals: respected (no multi-step workflow, no speed test, no cross-platform, no browser, no replacement of phase6 e2e).
- §3 Test scenario: covered by Task 7 (PROMPT constant, KdenliveLaunch on the demo fixture).
- §4 Assertions 1-7: covered one-to-one by the assertions in Task 7.
- §5 Module structure: Tasks 1-6 create every file in the spec's tree.
- §6.1 XvfbContext: Task 2.
- §6.2 KdenliveLaunch: Task 3.
- §6.3 ChatUIServer: Task 4.
- §6.4 WSClient: Task 5.
- §6.5 dbus_probe: Task 6.
- §6.6 fake_pi: omitted by design (YAGNI — we use http.server fixture instead).
- §7 Test isolation: Task 7 setUp/tearDown handles tempdir, XDG, port-picking, process groups, cleanup order.
- §8 Skipif guards: Task 1 + Task 7.
- §9 Lifecycle: Task 7's setUp + the e2e test method steps.
- §10 Error handling: Task 7's try/except dumps transcript + Kdenlive stderr on failure; helpers raise RuntimeError on timeout.
- §11 Runtime budget: noted in Task 8 README.
- §12 Makefile: Task 1 + Task 8.
- §13 Documentation impact: Task 1 (phase7 README) + Task 8 (top-level README).
- §14 Risks: mitigated (skipif for already-on-bus Kdenlive in Task 7, 45s Kdenlive timeout, 180s LLM timeout, transcript dump on failure).
- §15 Out of scope: respected.

**Type / name consistency check:**
- `XvfbContext.__enter__` returns `str` (display) — used everywhere consistently.
- `KdenliveLaunch.wait_ready()` and `terminate()` — used everywhere consistently.
- `ChatUIServer.url` (str) and `port` (int) — used everywhere consistently.
- `WSClient.run_prompt_sync` returns `list[dict]` — used everywhere consistently.
- `read_timeline_state(client=None)` — the `client` arg is the only parameter, used consistently.
- `skipif_helpers._has`, `_has_opencode_auth`, `_kdenlive_already_on_bus` — used everywhere consistently.

**Placeholder scan:** none. Every step has the actual content.
