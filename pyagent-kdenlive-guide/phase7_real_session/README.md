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
make test        # unit tests for the helpers (fast, no display needed) — 3 tests
make test-e2e    # the e2e test (20-45s, needs display + network) — 1 test
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

## File map (post-2026-07-19 cleanup)

| File | Purpose | Lines |
|---|---|---|
| `e2e.py` | The ONE entry point: skipif helpers + `XvfbContext` + `KdenliveLaunch` + `ChatUIServer` + `read_timeline_state` + re-exported `WSClient` | 299 |
| `skipif.py` | Thin re-export shim — `from phase7_real_session.skipif import _has` | — |
| `ws_client.py` | `WSClient` — drive the WebSocket, collect events | — |
| `tests/test_e2e.py` | The ONE persistent test: 1 unit test class for the XML parser (3 cases) + 1 e2e class that drives a real pi + real Kdenlive (1 case) | 319 |

The 2026-07-19 cleanup collapsed 4 entry-point modules that all
duplicated the skipif + XvfbContext + KdenliveLaunch + ChatUIServer
boilerplate. `xvfb.py` and `run_e2e.py` (now deleted) lived alongside
`e2e.py` and `tests/test_e2e.py`; the helpers are now named classes
inside `e2e.py` and `xvfb.py` is a thin re-export shim for the small
amount of legacy test code that still imports from it. Net: ~290 LOC
deleted and the only persistent e2e test is
`tests/test_e2e.py::TestE2EPiSession::test_edit_render_qc_roundtrip`.
