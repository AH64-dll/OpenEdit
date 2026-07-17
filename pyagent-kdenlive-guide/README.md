# PyAgent for Kdenlive

A `.kdenlive`-editing AI assistant. Talk to it, it edits your timeline.

Four working phases; two stretch (deferred).

## What it is

PyAgent is a `pi` agent extension (`phase3_pyagent_core/extension.ts`) that
exposes 19 tools to an LLM: 13 file-mode edit tools (3 of which also
support live-mode D-Bus), and 6 render / QC tools. A vanilla FastAPI +
WebSocket chat UI (`phase4_chat_ui/`) wraps the same extension as a web
app. Phase 5 plugs into Kdenlive's built-in D-Bus so edits show up live
when `PYAGENT_LIVE=1`. Phase 6 renders the result and runs cheap
deterministic QC.

## Architecture

```
              ┌──────────────┐
   user ───▶  │ Phase 4 chat │
              │  UI (web)    │
              └──────┬───────┘
                     │ WebSocket
                     ▼
              ┌──────────────┐         ┌────────────┐
   LLM ───▶  │ pi extension │ ──────▶ │ Phase 3    │ ──▶ .kdenlive
              │ (Phase 3)    │         │ backend    │     (file mode)
              └──────┬───────┘         └────────────┘
                     │
            ┌────────┴────────┐
            ▼                 ▼
       ┌─────────┐       ┌─────────┐
       │ Phase 5 │       │ Phase 6 │
       │ D-Bus   │       │ render+ │
       │ bridge  │       │ QC      │
       └────┬────┘       └────┬────┘
            ▼                 ▼
       live Kdenlive      MP4 + thumbs
                            + QC reports
```

- **File mode (default)**: edits land in the `.kdenlive` file; user
  reloads the project to see them.
- **Live mode (`PYAGENT_LIVE=1`)**: 3 tools (`import_media`,
  `append_clip`, `apply_effect`) go through Kdenlive's D-Bus instead.
  User sees the change immediately.
- **Render + QC (Phase 6)**: always file-based. Reads the `.kdenlive`
  file, runs melt/ffmpeg, returns artifacts.

## Quickstart

The phases are siblings, not pip-installable packages — run with
`PYTHONPATH=.` from this directory. Only the four phases that ship a
`pyproject.toml` (3, 4, 5, 6) need to be importable; phase 1 (catalog
data) and phase 2 (editor backend library) are consumed via
`PYTHONPATH` as well.

```bash
cd pyagent-kdenlive-guide
pip install -e phase3_pyagent_core \
            -e phase4_chat_ui \
            -e phase5_dbus_sync \
            -e phase6_render_qc
# (system deps: melt, ffmpeg, ffprobe, jeepney, lxml)

# Point PyAgent at a .kdenlive file.
export PYAGENT_PROJECT=/path/to/your/project.kdenlive
# Optional: live mode (requires Kdenlive running with D-Bus enabled).
export PYAGENT_LIVE=1

# Run the chat UI.
PYTHONPATH=. python3 -m phase4_chat_ui --project "$PYAGENT_PROJECT" --port 8000
# Open http://localhost:8000
```

The chat UI takes a `--project` flag (required) plus `--host`,
`--port`, `--provider`, `--model`, `--pi-binary`:

```bash
PYTHONPATH=. python3 -m phase4_chat_ui --project /path/to/project.kdenlive --port 8000
```

The Phase 6 CLI tools are also available standalone:

```bash
python3 -m phase6_render_qc.render --project x.kdenlive --output out.mp4
python3 -m phase6_render_qc.thumbnails --video out.mp4 --timestamp-sec 1.0 --output t.jpg
python3 -m phase6_render_qc.black_frames --video out.mp4
python3 -m phase6_render_qc.audio silence --video out.mp4
python3 -m phase6_render_qc.audio levels --video out.mp4
```

## Tools (19 total)

| Tool | Phase | What it does | Live-mode eligible |
|---|---|---|---|
| `pyagent_get_project_info` | 3 | read project metadata | — |
| `pyagent_get_timeline_summary` | 3 | read tracks/clips/transitions | — |
| `pyagent_list_catalog` | 3 | look up effect/transition details | — |
| `pyagent_import_media` | 3 | add media to the bin | **yes** |
| `pyagent_insert_clip` | 3 | insert a clip at a position | — |
| `pyagent_append_clip` | 3 | append a clip to a track end | **yes** |
| `pyagent_move_clip` | 3 | move a clip | — |
| `pyagent_trim_clip` | 3 | trim a clip's in/out | — |
| `pyagent_delete_clip` | 3 | remove a clip | — |
| `pyagent_add_transition` | 3 | crossfade between two clips | — |
| `pyagent_apply_effect` | 3 | apply an effect to a clip | **yes** |
| `pyagent_add_marker` | 3 | add a marker/guide | — |
| `pyagent_save_project` | 3 | write the .kdenlive file to disk | — |
| `pyagent_render` | 6 | render to MP4 (proxy or final) | — |
| `pyagent_get_thumbnail` | 6 | extract a single JPEG frame | — |
| `pyagent_get_qc_crop` | 6 | extract a cropped JPEG frame | — |
| `pyagent_list_black_frames` | 6 | deterministic black-frame check | — |
| `pyagent_list_silence` | 6 | deterministic silence check | — |
| `pyagent_get_audio_levels` | 6 | numeric RMS + peak dB | — |

## Testing

```bash
cd pyagent-kdenlive-guide
PYTHONPATH=. python3 -m unittest discover -s phase3_pyagent_core -p "test_*.py"  # 29
PYTHONPATH=. python3 -m unittest discover -s phase4_chat_ui -p "test_*.py"       # 22
PYTHONPATH=. python3 -m unittest discover -s phase5_dbus_sync -p "test_*.py"     # 24
PYTHONPATH=. python3 -m unittest discover -s phase6_render_qc -p "test_*.py"     # 24
PYTHONPATH=. python3 -m unittest discover -s phase7_real_session/tests -p "test_*.py"  # 28
```

127 tests total. Some Phase 5 and Phase 6 tests skip if `dbus-send`,
`melt`, `ffmpeg`, or the demo fixture are unavailable. The single
Phase 7 skip is the real-session e2e test (see next section).

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

## Limitations

- **File mode requires a manual reload** unless `PYAGENT_LIVE=1` and
  Kdenlive is running. Live mode covers 3 high-frequency tools only.
- **QC is sanity-check only** — it catches black frames, silence,
  and produces capped JPEGs. It is not broadcast-grade QC.
- **No native dock** (Phase 8) — the chat UI is a separate web app.

## Stretch (deferred)

- **Phase 7 (D-Bus fork track)** — deferred. Phase 0's spike confirmed
  upstream Kdenlive already exposes the methods Phase 5 uses, so
  maintaining a fork would add complexity for no gain.
- **Phase 8 (native dock)** — deferred. The architecture decision
  was to earn a real Kdenlive-side dock by using Phases 0–6 in
  production first. The chat UI is designed to be embeddable later
  via a `QWebEngineView` in a KDDockWidgets panel.
