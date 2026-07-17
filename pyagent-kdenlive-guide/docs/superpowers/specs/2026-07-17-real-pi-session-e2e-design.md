# Real pi-session end-to-end test

**Date:** 2026-07-17
**Status:** Approved
**Phase:** 7 (new module)

## 1. Purpose

Today the strongest end-to-end coverage in `pyagent-kdenlive-guide` is
`phase6_render_qc/test_e2e_pipeline.py`, which exercises the **Phase 3 →
Phase 6** pipeline (file-mode edit, melt render, ffmpeg QC) on a
tempdir copy of the demo fixture. It does **not** exercise the LLM
(`pi`), the chat UI (FastAPI + WebSocket), or a real Kdenlive instance
(D-Bus live-sync). Three load-bearing paths are therefore untested:

1. The LLM correctly chooses a tool from the 19-tool catalog described
   in `phase3_pyagent_core/system_prompt.md`.
2. The chat UI's `pi_client.PiClient.run_prompt` correctly translates
   user text into a stream of `PiEvent`s.
3. The Phase 5 D-Bus live-sync actually pushes file-mode edits into a
   running Kdenlive.

This design adds a new test module, `phase7_real_session`, that
exercises all three at once by driving a real `pi` session against a
real Kdenlive in a virtual display, with the chat UI as the WebSocket
relay. The test is a **persistent, runnable e2e test** that lives in
the repo, is invoked via `make test-e2e`, and is **skipped** (not
failed) on machines missing the required dependencies.

The test is **not** part of the default `make test` target because it
takes 20-45s, requires a network roundtrip to a model provider, and
needs an X server.

## 2. Goals and non-goals

### Goals

- Drive a real `pi --mode json` subprocess via the chat UI's
  WebSocket.
- Verify the LLM picks `pyagent_add_transition` from the catalog.
- Verify the file-mode edit lands on disk.
- Verify the same edit appears in the **running** Kdenlive via D-Bus.
- Capture the LLM transcript for debugging on failure.
- Skip cleanly on machines without the required deps.

### Non-goals

- A multi-step workflow (import + transition + render + thumbnail). One
  step is enough to prove the path; multi-step would multiply
  flakiness without adding proportional signal.
- A speed test. We assert correctness, not latency.
- Cross-platform support. Linux only (X11 is required for Kdenlive).
- A Web-frontend smoke test. The chat UI is exercised via its
  WebSocket directly; no browser is needed.
- Replacing the existing file-mode e2e test. That test still has
  value (it runs in <15s, no display, no network).

## 3. Test scenario

The user message sent to `pi` is:

> "Add a 1-second dissolve between the two clips in the timeline."

The expected sequence:

1. The chat UI's `PiClient.run_prompt` spawns `pi` with the project
   path in `PYAGENT_PROJECT` and the 19-tool system prompt in
   `--append-system-prompt`.
2. `pi` emits one or more `PiEvent(kind="tool", tool="pyagent_add_transition")`
   with `args = {"clip_a_id": ..., "clip_b_id": ..., "kind": "dissolve", "duration_sec": 1.0}`.
3. The chat UI's `run_op` wrapper calls
   `phase3_pyagent_core.__main__:run_op("add_transition", ...)` which
   returns `(0, {"ok": True, ...})`.
4. The chat UI's notifier (Phase 5) fires a D-Bus live-sync to the
   running Kdenlive.
5. `pi` emits a final `PiEvent(kind="done")` and the LLM produces a
   brief assistant message that mentions "dissolve".

The demo fixture (`phase3_pyagent_core/tests/fixtures/demo.kdenlive`)
already has two clips on track 0, so "the two clips" is unambiguous.

## 4. Assertions

The test runs the following assertions after the prompt completes:

| # | What we check | Pass criterion |
|---|---|---|
| 1 | `pi` called at least one tool | At least one `PiEvent(kind="tool")` was emitted. |
| 2 | `pi` picked the right tool | One tool event has `tool == "pyagent_add_transition"`. |
| 3 | The args were correct (with LLM-drift tolerance) | That event's `args` includes `kind in {"dissolve", "crossfade"}` and `0.5 <= duration_sec <= 1.5`. |
| 4 | The tool succeeded | The tool event's `result["ok"]` is `True`. |
| 5 | The file changed on disk | The tempdir copy of `demo.kdenlive` now contains a `<transition>` element that was not present in the pre-run copy. |
| 6 | The live Kdenlive reflects the change | A D-Bus read of `org.kde.kdenlive`'s project state shows a transition matching (a) the same clip A/B IDs, (b) `kind in {"dissolve", "crossfade"}`. |
| 7 | The LLM described the action | The final assistant text contains "dissolve" (case-insensitive) OR the literal "added a transition". |

Assertion 6 uses the existing `phase5_dbus_sync` D-Bus client. The
exact D-Bus call is the same one Phase 5's `KdenliveDBus` class uses
to read timeline state. If the running Kdenlive does not expose the
new transition, the test fails with a clear diff (expected vs.
actual transition list).

## 5. Module structure

New directory: `pyagent-kdenlive-guide/phase7_real_session/`.

```
phase7_real_session/
├── pyproject.toml                 # test-only deps; no [project.scripts]
├── Makefile                       # `make test-e2e` target
├── README.md                      # one-pager: what, how, deps
├── __init__.py
├── xvfb.py                        # XvfbContext: start/stop virtual display
├── kdenlive.py                    # KdenliveLaunch: launch + wait-for-D-Bus
├── chat_ui.py                     # ChatUIServer: subprocess + healthcheck
├── ws_client.py                   # WebSocket driver: send prompt, collect events
├── dbus_probe.py                  # read the live Kdenlive's project state
├── tests/
│   ├── __init__.py
│   ├── test_e2e_pi_session.py     # the actual test
│   ├── test_skipif.py             # unit tests for the skipif helpers
│   └── _support/
│       ├── __init__.py
│       └── fake_pi.py             # reusable fake pi binary (was in phase4)
└── skipif_helpers.py              # skipif helpers (unittest-style; pytest-free)
```

### Why a new phase module (vs. tests/ at the top level or inside phase4)

- The existing pattern is one phase = one module with `pyproject.toml`
  and `Makefile`. Adding a new phase is the path of least surprise.
- The reusable helpers (`xvfb.py`, `chat_ui.py`, etc.) are valuable
  outside the test (a future `make dev` script that runs the chat UI
  in a virtual display). They are not test-only in spirit.
- The Phase 4 chat UI's existing test is `test_app.py`,
  `test_websocket.py`, etc. — fast unit tests. A 30s e2e test there
  would distort the phase4 test runtime.

### pyproject.toml content

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
    "websockets>=12",   # inherited from phase4
    "dbus-python>=1.3", # inherited from phase5
]

[tool.setuptools.packages.find]
include = ["phase7_real_session*"]
```

## 6. Helpers

### 6.1 `xvfb.py` — XvfbContext

```python
class XvfbContext:
    """Context manager that starts Xvfb on the lowest free :N
    display in [99, 199] and exports DISPLAY=:N. Kills the Xvfb
    process group on exit. No external deps beyond stdlib.
    """
    def __init__(self, min_display: int = 99, max_display: int = 199): ...
    def __enter__(self) -> str: ...  # returns ":<N>"
    def __exit__(self, *exc) -> None: ...
```

Implementation: pick a free display by trying `Xvfb :N -ac -screen 0
1024x768x24` in a loop. `os.setsid` so the process group is killable
in one shot.

### 6.2 `kdenlive.py` — KdenliveLaunch

```python
class KdenliveLaunch:
    """Launch kdenlive in the given DISPLAY, opening `project_path`.
    Blocks until org.kde.kdenlive is on the session D-Bus or
    `timeout` elapses. Captures stderr to a file.
    """
    def __init__(self, project_path: str, xdg_config_home: str,
                 xdg_cache_home: str, display: str,
                 timeout: float = 30.0): ...
    def wait_ready(self) -> None: ...
    def terminate(self) -> None: ...  # SIGTERM, then SIGKILL after 5s
```

`XDG_CONFIG_HOME` and `XDG_CACHE_HOME` are redirected to the test
tempdir so the launched Kdenlive does not pollute the user's real
Kdenlive profile.

### 6.3 `chat_ui.py` — ChatUIServer

```python
class ChatUIServer:
    """Launch `python -m phase4_chat_ui --project <p> --port <free>
    --provider opencode --model minimax-m3` as a subprocess.
    Blocks until GET http://127.0.0.1:<port>/api/project returns
    200 or `timeout` elapses.
    """
    def __init__(self, project_path: str, provider: str, model: str,
                 display: str, timeout: float = 15.0): ...
    @property
    def port(self) -> int: ...
    @property
    def url(self) -> str: ...  # http://127.0.0.1:<port>
    def wait_ready(self) -> None: ...
    def terminate(self) -> None: ...
```

### 6.4 `ws_client.py` — WSClient

```python
class WSClient:
    """Async WebSocket client for /ws. Sends prompts, collects
    PiEvent-style dicts until {"type": "done"} arrives.
    """
    def __init__(self, url: str, timeout: float = 180.0): ...
    async def connect(self) -> None: ...
    async def send_prompt(self, text: str) -> list[dict]: ...
    async def close(self) -> None: ...
```

Synchronous wrapper: `def run_prompt_sync(self, text) -> list[dict]:`
runs the event loop, returns the event list.

### 6.5 `dbus_probe.py`

```python
def read_timeline_state(bus_name: str = "org.kde.kdenlive",
                        object_path: str = "/projects/0/timeline") -> dict:
    """Read the running Kdenlive's timeline state via D-Bus.
    Returns a dict with shape:
      {
        "tracks": [
          {"id": ..., "clips": [{"id": ..., "in": ..., "out": ...}]},
          ...
        ],
        "transitions": [
          {"id": ..., "kind": ..., "from_clip": ..., "to_clip": ...},
          ...
        ]
      }
    """
```

Reuses `phase5_dbus_sync.dbus_client.KdenliveDBus`. The exact method
calls are `getTrackList()` then per-track `getClipList()`, plus a
top-level `getTransitionList()`.

### 6.6 `tests/_support/fake_pi.py`

A copy of the existing `phase4_chat_ui/tests/_support/fake_pi.py` for
local use in this module. The original is re-exported from
`phase7_real_session.tests._support.fake_pi` to avoid a hard
cross-phase import. (Used only in `dbus_probe` and `chat_ui` unit
tests, not in the e2e test itself.)

## 7. Test isolation

- **Project file:** Copied to a `tempfile.mkdtemp(prefix="pyagent_e2e_")`.
  The original `phase3_pyagent_core/tests/fixtures/demo.kdenlive` is
  read but never written.
- **Kdenlive config:** `XDG_CONFIG_HOME=$tmpdir/.config` and
  `XDG_CACHE_HOME=$tmpdir/.cache` so the launched Kdenlive doesn't
  pollute the user's real profile.
- **Kdenlive D-Bus:** Uses the existing session bus. We do not start
  a private D-Bus daemon — the running Kdenlive, the chat UI, and
  the test all share the user's session bus. This is the same setup
  that the existing `phase5_dbus_sync` skipped tests assume.
- **Chat UI port:** Picked via `socket.socket().bind(('',0))` so we
  never collide with another service.
- **Process cleanup:** All subprocesses are started with
  `preexec_fn=os.setsid` so the process group is owned by the test.
  `os.killpg(pgid, SIGTERM)` then SIGKILL after 5s cleans up
  children. Order: Kdenlive → chat UI → Xvfb. If cleanup itself
  fails, we log PIDs to stderr and do not re-raise.
- **Tempdir cleanup:** `tempfile.TemporaryDirectory(ignore_cleanup_errors=True)`.

## 8. Skipif guards

Class-level decorators on `TestE2EPiSession`:

```python
def _has(name): return shutil.which(name) is not None

def _has_opencode_auth() -> bool:
    return bool(os.environ.get("OPENCODE_API_KEY")) or \
           Path.home().joinpath(".pi/agent/auth.json").exists()

def _kdenlive_already_on_bus() -> bool:
    """True if a kdenlive is already registered on the session D-Bus.

    The test must skip in this case because the D-Bus name
    `org.kde.kdenlive` is global — our launched Kdenlive would
    collide with the user's Kdenlive, and the test's D-Bus
    probes would talk to the wrong instance.
    """
    out = subprocess.run(
        ["dbus-send", "--session", "--print-reply",
         "--dest=org.freedesktop.DBus", "/org/freedesktop/DBus",
         "org.freedesktop.DBus.ListNames"],
        capture_output=True, text=True, timeout=5,
    )
    return "kdenlive" in (out.stdout or "").lower()

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
class TestE2EPiSession(unittest.TestCase): ...
```

A machine missing any of these reports `skipped` (not `failed`),
keeping CI honest. The error message names the missing dep so a
developer knows what to install.

## 9. Lifecycle

```
setUp
  1. tempfile.mkdtemp → project_dir
  2. shutil.copy(FIXTURE, project_dir/demo.kdenlive)
  3. with XvfbContext() as display:
       4. KdenliveLaunch(project_dir/demo.kdenlive) → wait for D-Bus
       5. ChatUIServer(project_dir/demo.kdenlive) → wait for HTTP 200
       6. WSClient(chat_ui.url) → connect
       7. ws.send({"type": "prompt", "text": "..."})
       8. collect events until {"type": "done"} (timeout 180s)
       9. assert 7 conditions
      10. close ws
      11. terminate chat_ui, kdenlive
  12. XvfbContext.__exit__ kills Xvfb
tearDown
  13. shutil.rmtree(project_dir)
```

Each step prints `[e2e] step N: <name>` to stderr. The full event
stream is captured to `transcript.json` in the tempdir; on failure,
it is printed to stderr. Kdenlive's stderr is captured to a file
in the tempdir; on failure, the last 50 lines are printed.

## 10. Error handling

| Step | Failure mode | What we do |
|---|---|---|
| 3 (Xvfb) | `:N` in use | We try `N=99..199` in order and use the first free one. |
| 4 (Kdenlive) | D-Bus name never appears (30s) | Kill Kdenlive, fail with stderr tail. |
| 5 (Chat UI) | HTTP 200 never received (15s) | Kill chat UI, fail with stderr tail. |
| 6 (WS) | Connection refused | Kill chat UI, fail. |
| 7 (prompt) | Timeout 180s | Close WS, kill chat UI, fail. |
| 7 (prompt) | pi emits `error` | Fail with the error text. |
| 9 (file parse) | Invalid XML | Fail with parse error. |
| 9 (file parse) | No `<transition>` added | Fail with "tool result said ok=True but file has no transition". |
| 10 (D-Bus probe) | `org.kde.kdenlive` disappears mid-test | Fail with "live Kdenlive died during the test". |
| 11 (assert) | any assertion fails | `assertEqual` shows the diff. |

If the test is interrupted (Ctrl-C, SIGTERM), the `try/finally`
around the Xvfb context manager ensures subprocesses are killed.
Leftover PIDs are logged to stderr but do not re-raise.

## 11. Runtime budget

- Kdenlive boot: 5-10s
- Chat UI boot: 2-3s
- LLM prompt + response: 10-30s
- File parse + D-Bus probe: <1s
- **Total: ~20-45s**

The test sets `unittest.TestCase` timeout to 180s (the LLM roundtrip
is the dominant cost). If a developer sees consistent >60s runtimes,
they should suspect the LLM provider is slow.

## 12. Makefile and CI

```makefile
.PHONY: test test-e2e

test:
	@PYTHONPATH=. python3 -m unittest discover -s phase3_pyagent_core -p "test_*.py"
	@PYTHONPATH=. python3 -m unittest discover -s phase4_chat_ui -p "test_*.py"
	@PYTHONPATH=. python3 -m unittest discover -s phase5_dbus_sync -p "test_*.py"
	@PYTHONPATH=. python3 -m unittest discover -s phase6_render_qc -p "test_*.py"

test-e2e:
	@echo "Running e2e real-pi-session test (needs pi, kdenlive, Xvfb, OPENCODE_API_KEY)..."
	@PYTHONPATH=. python3 -m unittest phase7_real_session.tests.test_e2e_pi_session -v
```

`test-e2e` is **not** part of the default `make test` because (a) it
requires an X server, (b) it makes a real LLM call, (c) it takes
20-45s. CI on a clean machine skips it. Developers with a working
desktop run it manually before pushing.

## 13. Documentation impact

- `pyagent-kdenlive-guide/README.md` gets a new "Real-session e2e
  test" section with: what it does, how to run it, what deps are
  needed, and a one-line install hint for the optional `Xvfb` dep
  (`sudo pacman -S xorg-server-xvfb`).
- `phase7_real_session/README.md` is a one-pager with the same info
  plus the test-skipif matrix.
- `phase7_real_session/skipif_helpers.py` documents the skipif
  rationale inline.

## 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| LLM picks a different tool (e.g., `pyagent_apply_effect` with a "crossfade" effect). | Assertion 3 allows `kind in {"dissolve", "crossfade"}`. Assertion 5 checks the **file** has a `<transition>`, not which tool was called. The test is more lenient than a unit test on purpose. |
| Kdenlive takes longer than 30s to register on D-Bus. | 30s is the current 95th-percentile. If real CI data shows this is too tight, bump to 60s. |
| The user's real Kdenlive is running on the same D-Bus. | We use the test's `XDG_CONFIG_HOME` to scope Kdenlive's profile, but the D-Bus name `org.kde.kdenlive` is global. If the user has Kdenlive open, our test will talk to theirs. Mitigation: `_kdenlive_already_on_bus()` in `skipif_helpers.py` runs `dbus-send ... ListNames` and skips the test if any `kdenlive` is found on the bus. |
| The test's Kdenlive and the user's Kdenlive race for the same D-Bus name. | Same as above: skipped by the `_kdenlive_already_on_bus()` check. |
| The LLM provider is down. | The test fails with a clear error from `pi` (no API key, ECONNREFUSED, etc.). Acceptable. |
| The chat UI's `pi_client.run_prompt` swallows events. | The chat UI is already tested by `phase4_chat_ui/test_pi_client.py`. We are exercising the live integration here. |
| Network jitter. | 180s timeout is generous. The test is allowed to be flaky; the user can re-run. |

## 15. Out of scope (future work)

- A multi-step workflow test (import + transition + render +
  thumbnail).
- A `--model` matrix (running the test against multiple providers).
- A "headless Kdenlive" build (Kdenlive does not currently have one).
- Replacing the file-mode e2e test with this one.

## 16. Open questions for the user

- None. The user approved each design section in chat before this
  spec was written.
