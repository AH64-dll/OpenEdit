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
| `e2e.py` | The ONE entry point: skipif helpers + `XvfbContext` + `KdenliveLaunch` + `ChatUIServer` + `read_timeline_state` + re-exported `WSClient`. |
| `skipif.py` | Thin re-export shim — `from phase7_real_session.skipif import _has`. |
| `xvfb.py` | (legacy module; logic now lives in `e2e.py`). |
| `ws_client.py` | `WSClient` — drive the WebSocket, collect events. |
| `tests/test_e2e.py` | The ONE persistent test: 1 unit test class for the XML parser + 1 e2e class that drives a real pi + real Kdenlive. |
