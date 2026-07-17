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
