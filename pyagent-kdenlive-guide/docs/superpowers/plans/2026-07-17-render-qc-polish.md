# Render/QC Polish Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four post-Phase-6 gaps so the working system is discoverable and the LLM can actually use the 19 wired-up tools.

**Architecture:** Three mechanical edits (system_prompt.md, app.js, new test) plus one new top-level README. No new tools, no new dependencies, no new protocol messages.

**Tech Stack:** Python 3.11+, vanilla JS, FastAPI/WebSocket (existing), `unittest` (existing test framework), `melt` + `ffmpeg` + `ffprobe` (already required for Phase 6 tests).

## Global Constraints

- Godot 4 syntax / GDScript rules do not apply here — this is a Python/TypeScript project.
- All code/comments/docs in English (per project convention).
- No new dependencies; only `lxml` and `jeepney` are already required.
- Filenames: snake_case, no spaces.
- Commit message format: `[polish][<area>] <imperative summary>` — one commit at the end (or two if README is its own).
- Existing tests must still pass: 98 total before this plan, 99 after.
- `phase6_render_qc/test_e2e_pipeline.py` skips on missing melt/ffmpeg/ffprobe/demo fixture (matches existing pattern in `test_render_integration.py`).
- All Phase 6 modules are subpackages under `phase6_render_qc/` (e.g. `phase6_render_qc.render`, not `phase6_render_qc/render.py`).
- The repo already has a `.gitignore` that excludes `__pycache__/` and `*.egg-info/`.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `phase3_pyagent_core/system_prompt.md` | edit | Tell the LLM about Phase 5 live mode + Phase 6 render/QC tools. |
| `phase4_chat_ui/static/app.js` | edit | Add 4 quick-action buttons (Render proxy, Render final, Check QC, Get thumbnail). |
| `phase6_render_qc/test_e2e_pipeline.py` | new | Scripted smoke test exercising Phase 3 → Phase 6 end-to-end (no LLM). |
| `pyagent-kdenlive-guide/README.md` | new | Top-level entry point: summary, architecture, quickstart, tool reference. |

No file is created that doesn't have a single clear responsibility. The `system_prompt.md` edit is 2 paragraphs + 6 tool-list lines, well under the file's existing structure. The `app.js` edit is 6 lines appended to an existing array. The test is a self-contained 90-line file. The README is a single new entry point.

---

## Task 1: Update system_prompt.md

**Files:**
- Modify: `phase3_pyagent_core/system_prompt.md` (insert 1 paragraph after "Hard rules", extend "Available tools" list)

**Interfaces:**
- Consumes: the existing file's structure (the catalog slice `{{CATALOG_SLICE}}` placeholder, the "Hard rules" and "Available tools (summary)" sections)
- Produces: same file, with the LLM now aware of 19 tools and the Phase 5/Phase 6 conventions

- [ ] **Step 1: Read the current system_prompt.md to confirm structure**

The file is at `pyagent-kdenlive-guide/phase3_pyagent_core/system_prompt.md`. Confirm:
- The "Hard rules" section ends with the rule about "3 failed attempts".
- The "Available tools (summary)" section ends with `pyagent_save_project — write the .kdenlive file to disk. Use this when you are done editing.`
- The "Catalog slice" section follows immediately.

If any of these are missing or have changed, re-read the file before continuing.

- [ ] **Step 2: Insert the Phase 5/6 paragraph after the "Hard rules" list**

Find the line that ends the "Hard rules" section (the rule about "After 3 failed attempts on the same operation, stop and tell the user."). Insert these two paragraphs immediately after it, before the blank line that precedes `## Available tools (summary)`:

```markdown
- **Phase 5 live mode** — when `PYAGENT_LIVE=1` is set, three tools
  (`pyagent_import_media`, `pyagent_append_clip`,
  `pyagent_apply_effect`) apply via Kdenlive's D-Bus instead of the
  file backend, so the user sees the change without a reload. In a long
  session, prefer them. If a live call fails (Kdenlive not running,
  D-Bus unavailable), the extension falls back to file mode
  automatically — do not preemptively avoid them.
- **Phase 6 render + QC** — after any non-trivial edit, verify it.
  The cheap flow is:
  1. `pyagent_render(mode="proxy", in_sec=X, out_sec=Y)` — render a
     small range around the change. 640x360, sub-2s for a 4s clip.
  2. `pyagent_list_black_frames(video)` and
     `pyagent_list_silence(video)` — deterministic, runs on the
     rendered video, returns spans.
  3. `pyagent_get_audio_levels(video)` — numeric RMS + peak dB.
  4. If anything is flagged, `pyagent_get_thumbnail(video,
     timestamp_sec)` for a visual check. Output is capped at ≤480px
     long-edge JPEG, q70, <250KB.

  Do not skip step 1 — a QC pass on the source clips tells you nothing
  about your edit; you have to render the *timeline* to see what your
  edit actually produces.
```

- [ ] **Step 3: Extend the "Available tools (summary)" list**

Find the line `pyagent_save_project — write the .kdenlive file to disk. Use this when you are done editing.` Insert these 6 lines immediately after it, before the blank line that precedes `## Catalog slice`:

```markdown
- `pyagent_render` — render the project (or a range) to MP4.
  `mode="proxy"` (default) is fast; `mode="final"` uses the project
  profile and is slow.
- `pyagent_get_thumbnail` — extract a single capped JPEG frame.
- `pyagent_get_qc_crop` — extract a cropped frame for legibility
  checks.
- `pyagent_list_black_frames` — deterministic black-frame check.
- `pyagent_list_silence` — deterministic silence check.
- `pyagent_get_audio_levels` — numeric RMS + peak dB.
```

- [ ] **Step 4: Sanity check the file**

Run: `wc -l pyagent-kdenlive-guide/phase3_pyagent_core/system_prompt.md`
Expected: ~85 lines (was ~67 before; +20 lines for the new content; ±2 acceptable).

Run: `grep -c "pyagent_" pyagent-kdenlive-guide/phase3_pyagent_core/system_prompt.md`
Expected: ≥ 19 (count of tool mentions in the lists and rules).

- [ ] **Step 5: Confirm Phase 3 tests still pass**

Run:
```bash
cd pyagent-kdenlive-guide
PYTHONPATH=. python3 -m unittest discover -s phase3_pyagent_core -p "test_*.py" 2>&1 | tail -3
```
Expected: 29 tests, OK (1 skipped). The system_prompt change is documentation only, so this is a safety net.

---

## Task 2: Add 4 quick-action buttons to the chat UI

**Files:**
- Modify: `phase4_chat_ui/static/app.js` (extend the `QUICK_ACTIONS` array at lines 199–204)

**Interfaces:**
- Consumes: the existing `QUICK_ACTIONS` array (4 entries, 4 lines of `{label, prompt}` objects)
- Produces: same array, now 8 entries. The 4 new entries follow the same `{label, prompt}` shape; the existing 4 stay unchanged. No new code, no new events.

- [ ] **Step 1: Read the current QUICK_ACTIONS block**

Open `pyagent-kdenlive-guide/phase4_chat_ui/static/app.js` and confirm lines 199–204 contain:

```javascript
const QUICK_ACTIONS = [
  { label: "Add crossfade between clips", prompt: "Add a crossfade transition between the last two clips on the timeline." },
  { label: "Append test clip", prompt: "Import the test clip and append it to the end of the first track." },
  { label: "List effects", prompt: "List the available video effects from the catalog." },
  { label: "Show timeline", prompt: "Show me the current timeline summary." },
];
```

- [ ] **Step 2: Append 4 new entries**

Change the closing `];` so the array becomes:

```javascript
const QUICK_ACTIONS = [
  { label: "Add crossfade between clips", prompt: "Add a crossfade transition between the last two clips on the timeline." },
  { label: "Append test clip", prompt: "Import the test clip and append it to the end of the first track." },
  { label: "List effects", prompt: "List the available video effects from the catalog." },
  { label: "Show timeline", prompt: "Show me the current timeline summary." },
  { label: "Render proxy", prompt: "Render a 640x360 proxy of the current project to /tmp/pyagent_proxy.mp4 and report the file size, duration, and elapsed render time." },
  { label: "Render final", prompt: "Render the project at full quality to /tmp/pyagent_final.mp4 using the project's own profile. This is slow — confirm the user is okay with it before proceeding." },
  { label: "Check QC", prompt: "Run the cheap deterministic QC checks (black frames, silence, audio levels) on /tmp/pyagent_proxy.mp4 over the full timeline and report any flags. If anything is flagged, pull a thumbnail for the affected timestamp and include it in the report." },
  { label: "Get thumbnail", prompt: "Pick a representative timestamp around the middle of the timeline and extract a thumbnail to /tmp/pyagent_thumb.jpg so the user can see what the project looks like right now." },
];
```

- [ ] **Step 3: Sanity check the file**

Run: `node --check pyagent-kdenlive-guide/phase4_chat_ui/static/app.js`
Expected: silent exit (no syntax errors). If `node` is not on PATH, skip this step and rely on the Phase 4 WebSocket test in Step 4.

- [ ] **Step 4: Confirm Phase 4 tests still pass**

Run:
```bash
cd pyagent-kdenlive-guide
PYTHONPATH=. python3 -m unittest discover -s phase4_chat_ui -p "test_*.py" 2>&1 | tail -3
```
Expected: 22 tests, OK. The chat UI JS isn't loaded by the Python tests, so this confirms the server side wasn't broken.

---

## Task 3: Add the e2e pipeline smoke test

**Files:**
- Create: `pyagent-kdenlive-guide/phase6_render_qc/test_e2e_pipeline.py`
- Test: `pyagent-kdenlive-guide/phase6_render_qc/test_e2e_pipeline.py` (self-contained; no separate fixtures file)

**Interfaces:**
- Consumes:
  - `phase3_pyagent_core.__main__:run_op(op: str, args: dict, project: str, catalog: str) -> (int, dict)` — already exists; returns `(code, response_dict)`. The `response_dict` has the shape `{"ok": bool, "result": ..., "fatal": bool, "error": str|None}`. On success, `response_dict["result"]` is a dataclass; the relevant fields vary per op.
  - `phase6_render_qc.render.render(project, output, mode, in_sec=None, out_sec=None) -> RenderResult` — already exists.
  - `phase6_render_qc.thumbnails.get_thumbnail(video, timestamp_sec, output) -> ThumbnailResult` — already exists.
  - `phase6_render_qc.black_frames.list_black_frames(video) -> BlackFramesResult` — already exists.
  - `phase6_render_qc.audio.list_silence(video) -> SilenceResult` — already exists.
  - `phase6_render_qc.audio.get_audio_levels(video) -> AudioLevels` — already exists.
- Produces: 1 new test class (`TestE2EPipeline`) that runs in <15s and asserts real artifacts (file existence, MP4 dimensions, JPEG magic bytes, file-size cap).

- [ ] **Step 1: Verify the existing run_op signature and demo fixture**

Run:
```bash
cd pyagent-kdenlive-guide
PYTHONPATH=. python3 -c "
from phase3_pyagent_core.__main__ import run_op
print('run_op ok')
import os
demo = 'phase3_pyagent_core/tests/fixtures/demo.kdenlive'
print('demo exists:', os.path.isfile(demo))
"
```
Expected: prints `run_op ok` and `demo exists: True`.

If the demo fixture is missing, this test will skip (see Step 2). If `run_op` signature has changed, re-read `phase3_pyagent_core/__main__.py` to confirm the `(op, args, project, catalog) -> (int, dict)` shape.

- [ ] **Step 2: Create the new test file**

Create `pyagent-kdenlive-guide/phase6_render_qc/test_e2e_pipeline.py` with this exact content:

```python
"""End-to-end pipeline smoke test: Phase 3 edit -> Phase 6 render/QC.

No LLM. Uses the demo fixture to apply a known sequence of edits via
phase3_pyagent_core.run_op, then renders and inspects the result with
every Phase 6 tool. Asserts real artifacts (file size, MP4 dimensions,
JPEG magic, file-size caps). Runs in <15s on a developer machine.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "phase3_pyagent_core" / "tests" / "fixtures" / "demo.kdenlive"
CATALOG = REPO / "phase1_knowledge_base" / "catalog.json"


def _run(op: str, args: dict, project: str, catalog: str) -> tuple[int, dict]:
    """Helper: call phase3_pyagent_core.run_op and return (code, resp)."""
    from phase3_pyagent_core.__main__ import run_op
    return run_op(op, args, project, catalog)


def _video_info(path: str) -> dict:
    """Tiny ffprobe wrapper — just width/height/duration of video stream."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,duration",
         "-of", "default=noprint_wrappers=1:nokey=0", path],
        capture_output=True, text=True, timeout=30,
    )
    info: dict = {}
    for line in (out.stdout or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip()
    return info


@unittest.skipIf(shutil.which("melt") is None, "melt not on PATH")
@unittest.skipIf(shutil.which("ffmpeg") is None, "ffmpeg not on PATH")
@unittest.skipIf(not FIXTURE.is_file(), "demo.kdenlive fixture missing")
@unittest.skipIf(not CATALOG.is_file(), "catalog.json missing")
class TestE2EPipeline(unittest.TestCase):
    """Edit a copy of the demo fixture, render a proxy, run all QC tools."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="pyagent_e2e_")
        self.project = os.path.join(self.tmp, "work.kdenlive")
        with open(FIXTURE, "rb") as src, open(self.project, "wb") as dst:
            dst.write(src.read())
        self.proxy = os.path.join(self.tmp, "proxy.mp4")
        self.thumb = os.path.join(self.tmp, "thumb.jpg")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_edit_render_qc_roundtrip(self) -> None:
        # ---- Phase 3: apply a known edit sequence ----
        # Append a second instance of the source clip onto track 0, then
        # add a 1s crossfade between the existing and the new clip.
        # The demo already has a 4s clip at out=4.0, so the appended one
        # is the same producer re-instanced. add_transition uses
        # clip_a_id=existing, clip_b_id=new.
        code, resp = _run("get_timeline_summary", {}, self.project, str(CATALOG))
        self.assertEqual(code, 0, f"get_timeline_summary failed: {resp}")
        self.assertTrue(resp.get("ok"), resp)
        summary = resp["result"]
        # demo fixture has one clip on track 0; capture its id.
        existing_clips = summary.get("tracks", [{}])[0].get("clips", [])
        self.assertGreaterEqual(len(existing_clips), 1, summary)
        existing_id = existing_clips[0]["id"]

        # Read project_info to get the source id of the existing clip.
        code, resp = _run("get_project_info", {}, self.project, str(CATALOG))
        self.assertEqual(code, 0, resp)
        sources = resp["result"].get("sources", [])
        self.assertGreaterEqual(len(sources), 1, resp)
        source_id = sources[0]["id"]

        # Append a second clip of the same source.
        code, resp = _run("append_clip", {
            "track_index": 0, "source_id": source_id,
            "source_in_sec": 0, "source_out_sec": 2.0,
        }, self.project, str(CATALOG))
        self.assertEqual(code, 0, f"append_clip failed: {resp}")
        self.assertTrue(resp.get("ok"), resp)
        new_id = resp["result"]["clip_id"] if isinstance(resp["result"], dict) else None
        self.assertIsNotNone(new_id, f"no clip_id in result: {resp}")

        # Add a crossfade between the existing clip and the new one.
        code, resp = _run("add_transition", {
            "clip_a_id": existing_id, "clip_b_id": new_id, "kind": "crossfade",
            "duration_sec": 1.0,
        }, self.project, str(CATALOG))
        self.assertEqual(code, 0, f"add_transition failed: {resp}")

        # Save.
        code, resp = _run("save", {}, self.project, str(CATALOG))
        self.assertEqual(code, 0, f"save failed: {resp}")

        # ---- Phase 6: render + QC ----
        from phase6_render_qc.render import render
        rr = render(self.project, self.proxy, mode="proxy")
        self.assertTrue(rr.ok, f"render failed: {rr.error}")
        self.assertTrue(os.path.isfile(self.proxy), "proxy not written")
        self.assertGreater(os.path.getsize(self.proxy), 5_000, "proxy too small")

        info = _video_info(self.proxy)
        self.assertEqual(info.get("width"), "640", info)
        self.assertEqual(info.get("height"), "360", info)
        # 4s original + 2s appended - 1s overlap from crossfade = ~5-6s.
        # We accept anything in [4.5, 7.0] to be tolerant of test drift.
        dur = float(info.get("duration", 0))
        self.assertGreater(dur, 4.5, f"proxy too short: {dur}s")
        self.assertLess(dur, 7.0, f"proxy too long: {dur}s")

        from phase6_render_qc.black_frames import list_black_frames
        bf = list_black_frames(self.proxy)
        self.assertTrue(bf.ok, f"blackdetect failed: {bf.error}")
        self.assertIsInstance(bf.spans, list)

        from phase6_render_qc.audio import list_silence, get_audio_levels
        sil = list_silence(self.proxy)
        self.assertTrue(sil.ok, f"silencedetect failed: {sil.error}")
        self.assertIsInstance(sil.spans, list)
        self.assertEqual(sil.threshold_db, -35.0)
        self.assertEqual(sil.min_sec, 1.0)

        al = get_audio_levels(self.proxy)
        self.assertTrue(al.ok, f"audio levels failed: {al.error}")
        self.assertLess(al.peak_db, 10.0)
        self.assertGreater(al.peak_db, -200.0)

        from phase6_render_qc.thumbnails import get_thumbnail
        # Thumbnail at the crossfade midpoint.
        th = get_thumbnail(self.proxy, 4.0, self.thumb)
        self.assertTrue(th.ok, f"thumbnail failed: {th.error}")
        self.assertLessEqual(max(th.width, th.height), 480)
        self.assertLess(th.file_bytes, 250_000)
        with open(self.thumb, "rb") as f:
            self.assertEqual(f.read(3), b"\xff\xd8\xff", "not a JPEG")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the new test alone**

Run:
```bash
cd pyagent-kdenlive-guide
PYTHONPATH=. python3 -m unittest phase6_render_qc.test_e2e_pipeline -v 2>&1 | tail -8
```
Expected: `Ran 1 test in <15s` and `OK`.

If it fails, the most common causes are:
1. `run_op` returning a different shape than expected — print `resp` and compare to the dataclass fields in `phase3_pyagent_core/__init__.py` and `KdenliveFileBackend` (e.g. `append_clip` may return a string id, not a dict).
2. The demo fixture's track 0 clip has a different id format — adjust `existing_clips[0]["id"]` accordingly.
3. The proxy is the wrong duration — relax the bounds or print `info`.

Fix the test inline (do not change the production code; the test is the contract).

- [ ] **Step 4: Run all Phase 6 tests together**

Run:
```bash
cd pyagent-kdenlive-guide
PYTHONPATH=. python3 -m unittest discover -s phase6_render_qc -p "test_*.py" 2>&1 | tail -5
```
Expected: 24 tests, OK (23 existing + 1 new). Total runtime <25s.

---

## Task 4: Write the top-level README

**Files:**
- Create: `pyagent-kdenlive-guide/README.md`

**Interfaces:**
- Consumes: nothing (new file)
- Produces: a single new entry point at the project root. The file references but does not duplicate per-phase READMEs.

- [ ] **Step 1: Verify there is no existing top-level README**

Run:
```bash
ls pyagent-kdenlive-guide/README.md 2>&1
```
Expected: `No such file or directory` (so we are creating, not overwriting). If the file already exists, read it first and decide whether to replace or augment.

- [ ] **Step 2: Create the README**

Create `pyagent-kdenlive-guide/README.md` with this content:

````markdown
# PyAgent for Kdenlive

A `.kdenlive`-editing AI assistant. Talk to it, it edits your timeline.

Four working phases; two stretch (deferred).

## What it is

PyAgent is a `pi` agent extension (`phase3_pyagent_core/extension.ts`) that
exposes 19 tools to an LLM: 13 file-mode edit tools, 3 live-mode D-Bus
edit tools, and 6 render / QC tools. A vanilla FastAPI + WebSocket chat
UI (`phase4_chat_ui/`) wraps the same extension as a web app. Phase 5
plugs into Kdenlive's built-in D-Bus so edits show up live when
`PYAGENT_LIVE=1`. Phase 6 renders the result and runs cheap
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

```bash
# 1. Install all five working packages in editable mode.
cd pyagent-kdenlive-guide
pip install -e phase1_knowledge_base \
            -e phase2_project_engine \
            -e phase3_pyagent_core \
            -e phase4_chat_ui \
            -e phase5_dbus_sync \
            -e phase6_render_qc

# 2. Point PyAgent at a .kdenlive file.
export PYAGENT_PROJECT=/path/to/your/project.kdenlive
# Optional: live mode (requires Kdenlive running with D-Bus enabled).
export PYAGENT_LIVE=1

# 3. Run the chat UI.
PYTHONPATH=. python3 -m phase4_chat_ui
# Open http://localhost:8000
```

The chat UI takes a `--project` flag too:

```bash
python3 -m phase4_chat_ui --project /path/to/project.kdenlive --port 8000
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
```

99 tests total. Some Phase 5 and Phase 6 tests skip if `dbus-send`,
`melt`, `ffmpeg`, or the demo fixture are unavailable.

## Limitations

- **File mode requires a manual reload** unless `PYAGENT_LIVE=1` and
  Kdenlive is running. Live mode covers 3 high-frequency tools only.
- **QC is sanity-check only** — it catches black frames, silence,
  and produces capped JPEGs. It is not broadcast-grade QC.
- **No native dock** (Phase 8) — the chat UI is a separate web app.
- **No D-Bus fork** (Phase 7) — Phase 5 uses upstream Kdenlive's
  built-in D-Bus. The fork was deferred because upstream already has
  the methods we need.

## Stretch (deferred)

- **Phase 7 (D-Bus fork track)** — deferred. Phase 0's spike confirmed
  upstream Kdenlive already exposes the methods Phase 5 uses, so
  maintaining a fork would add complexity for no gain.
- **Phase 8 (native dock)** — deferred. The architecture decision
  was to earn a real Kdenlive-side dock by using Phases 0–6 in
  production first. The chat UI is designed to be embeddable later
  via a `QWebEngineView` in a KDDockWidgets panel.
````

- [ ] **Step 3: Sanity check the README**

Run:
```bash
wc -l pyagent-kdenlive-guide/README.md
grep -c "^| \`pyagent_" pyagent-kdenlive-guide/README.md
```
Expected: ~150 lines, and `grep` count of 19 (one row per tool in the table).

- [ ] **Step 4: Cross-check every quickstart command**

Run each command from the Quickstart section's Phase 6 CLI examples
against the actual binaries:

```bash
cd pyagent-kdenlive-guide
PYTHONPATH=. python3 -m phase6_render_qc.render --help
PYTHONPATH=. python3 -m phase6_render_qc.thumbnails --help
PYTHONPATH=. python3 -m phase6_render_qc.black_frames --help
PYTHONPATH=. python3 -m phase6_render_qc.audio --help
```
Expected: each prints a help message (the `--help` flag is parsed
correctly). If any of them error, fix the README's command.

- [ ] **Step 5: Confirm Phase 4 chat UI entry point is correct**

Run:
```bash
PYTHONPATH=. python3 -m phase4_chat_ui --help 2>&1 | head -20
```
Expected: help output with the `--project` and `--port` flags documented
in the README. If the entry point doesn't accept these flags, fix the
README.

---

## Task 5: Final verification and commit

**Files:** none new; just verify all tests pass and commit.

- [ ] **Step 1: Run all four test suites**

Run:
```bash
cd pyagent-kdenlive-guide
PYTHONPATH=. python3 -m unittest discover -s phase3_pyagent_core -p "test_*.py" 2>&1 | tail -3
PYTHONPATH=. python3 -m unittest discover -s phase4_chat_ui -p "test_*.py"       2>&1 | tail -3
PYTHONPATH=. python3 -m unittest discover -s phase5_dbus_sync -p "test_*.py"     2>&1 | tail -3
PYTHONPATH=. python3 -m unittest discover -s phase6_render_qc -p "test_*.py"     2>&1 | tail -3
```
Expected: 29, 22, 24, 24 — all OK.

- [ ] **Step 2: Commit**

```bash
cd pyagent-kdenlive-guide
git add phase3_pyagent_core/system_prompt.md \
        phase4_chat_ui/static/app.js \
        phase6_render_qc/test_e2e_pipeline.py \
        README.md \
        docs/superpowers/specs/2026-07-17-render-qc-polish-design.md
git -c user.email=ah64@local -c user.name=ah64 commit -m "[polish][docs+ui] wire render/QC into LLM prompt, add 4 quick actions, e2e test, top-level README

- system_prompt.md: Phase 5 live mode paragraph + Phase 6 render/QC
  paragraph + 6 new tool entries. LLM now knows about all 19 tools.
- app.js: 4 new quick-action buttons (Render proxy, Render final,
  Check QC, Get thumbnail). No new protocol.
- test_e2e_pipeline.py: scripted smoke that runs Phase 3 edit ops
  (append + crossfade) on the demo fixture, then Phase 6 render +
  every QC tool, asserting real artifacts (file size, MP4 dimensions,
  JPEG magic, file-size cap).
- README.md: top-level entry point with summary, architecture diagram,
  quickstart, full tool table, testing section, limitations, stretch
  notes.
- 99 tests pass (was 98; new e2e)."
```

- [ ] **Step 3: Verify the commit landed**

Run:
```bash
git log --oneline -3
```
Expected: top commit is the polish commit; the one before is Phase 6 (`0354f2a`).
