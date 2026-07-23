# Whisper Install + Ordered Silence-Trimmed Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (A) Install `faster-whisper` and re-transcribe the 3 project assets so they carry word-level alignment; (B) Take over from the stalled agent and build an ordered, silence-trimmed timeline via the proper IR API (no direct DB writes), placing the 3 videos in order 1→2→3 with silence/fumble gaps removed and cut points flagged as review markers.

**Architecture:** Whisper transcription is optional in `storage/transcription.py` (returns `[]` when `faster-whisper` is absent). Re-transcription writes alignment back into each asset's sidecar JSON. The timeline is built by appending `AddClipOp` operations to the project's `EditGraphStore` (in `edit_graph.db`), letting `derive_or_load_timeline` replay them through the real apply pipeline — exactly what a tool call would do, but without the sandbox. Review markers are `NotesStore` review notes (`source=agent`), not IR ops.

**Tech Stack:** Python 3.13 venv at `/home/ah64/apps/mlt-pipeline/open_edit/.venv` (the `PINNED_PYTHON_BIN`); `faster-whisper` (CPU, int8); `ffmpeg`/`ffprobe`; Open Edit `open_edit.*` modules.

## Global Constraints
- Install ONLY into the project venv: `/home/ah64/apps/mlt-pipeline/open_edit/.venv/bin/pip` (the server and agents use `PINNED_PYTHON_BIN = sys.executable` → that venv). Do NOT use system pip.
- Never write ops directly to `edit_graph.db`; always go through `EditGraphStore.append(op)` so status events + sequence numbering are correct (Phase 1 integrity).
- Markers are notes via `add_marker(...)`, NOT IR ops.
- Project root: `/home/ah64/OpenEditProjects/ll`. Assets: `f6f74b…` (1.mp4, 1039.8s), `81b720…` (2.mp4, 315.0s), `6cc047…` (3.mp4, 578.8s). Timeline order MUST be 1→2→3.
- After any code change, restart the live server (currently PID 263222) — but note we are editing the PROJECT DB directly via the storage layer, not the server, so no restart needed for the build; restart only if we change server code (we do not here).

---

### Task 1: Install faster-whisper into the project venv

**Files:**
- Env: `/home/ah64/apps/mlt-pipeline/open_edit/.venv`

**Interfaces:**
- Consumes: nothing
- Produces: importable `faster_whisper.WhisperModel` inside the venv

- [ ] **Step 1: Install into the venv (allow time — pulls torch/onnxruntime)**

Run:
```bash
/home/ah64/apps/mlt-pipeline/open_edit/.venv/bin/pip install faster-whisper
```
Expected: exit 0, "Successfully installed faster-whisper-…".

- [ ] **Step 2: Verify import resolves in the venv**

Run:
```bash
/home/ah64/apps/mlt-pipeline/open_edit/.venv/bin/python -c "from faster_whisper import WhisperModel; print('whisper ok')"
```
Expected: prints `whisper ok`.

---

### Task 2: Re-transcribe the 3 assets and persist alignment

**Files:**
- Script (new, throwaway): `/home/ah64/apps/mlt-pipeline/open_edit/scripts/retx_assets.py`
- Data: `/home/ah64/OpenEditProjects/ll/.open_edit/assets/<hh>/<hash>.meta.json` (sidecars rewritten)

**Interfaces:**
- Consumes: `open_edit.storage.transcription.transcribe`, `open_edit.storage.assets.AssetStore`, `Asset.model_dump_json`
- Produces: sidecars with non-empty `alignment`

- [ ] **Step 1: Write the re-transcription script**

```python
import sys
from pathlib import Path
from open_edit.storage.assets import AssetStore
from open_edit.storage.transcription import transcribe

ROOT = Path("/home/ah64/OpenEditProjects/ll")
ASSETS_DIR = ROOT / ".open_edit" / "assets"
PROJECT_ID = ROOT.name
HASHES = ["f6f74b…", "81b720…", "6cc047…"]  # fill exact 64-hex below

store = AssetStore(ASSETS_DIR)
for h in HASHES:
    asset = store.get(h)
    if asset is None:
        print("MISSING", h); continue
    alignment = transcribe(Path(asset.stored_path))
    print(h, "words:", len(alignment))
    asset = asset.model_copy(update={"alignment": alignment})
    sidecar = ASSETS_DIR / h[:2] / f"{h}.meta.json"
    sidecar.write_text(asset.model_dump_json(indent=2))
```
(Replace `HASHES` with the exact 64-char asset hashes from `list_assets`.)

- [ ] **Step 2: Run it and confirm non-empty alignment**

Run:
```bash
/home/ah64/apps/mlt-pipeline/open_edit/.venv/bin/python scripts/retx_assets.py
```
Expected: three lines, each `… words: <N>` with N > 0 (base model on ~10–17 min audio, N in the thousands).

- [ ] **Step 3: Sanity-check sidecars contain alignment**

Run:
```bash
grep -c '"word"' /home/ah64/OpenEditProjects/ll/.open_edit/assets/*/*.meta.json
```
Expected: each sidecar shows a count > 0.

---

### Task 3: Compute silence + fumble keep-segments per asset

**Files:**
- Script (new): `/home/ah64/apps/mlt-pipeline/open_edit/scripts/build_timeline.py` (grows across Tasks 3–5)

**Interfaces:**
- Consumes: `ffmpeg silencedetect`, `asset.alignment`
- Produces: `keep_segments: dict[hash, list[tuple[float,float]]]`

- [ ] **Step 1: Add silence detection (ffmpeg) helper**

```python
import subprocess, re, json

def silence_intervals(path: str, noise_db="-30dB", d=0.3):
    out = subprocess.run(
        ["ffmpeg", "-i", path, "-af", f"silencedetect=noise={noise_db}:d={d}",
         "-f", "null", "-"], capture_output=True, text=True
    ).stderr
    starts = [float(x) for x in re.findall(r"silence_start:\s*([\d.]+)", out)]
    ends   = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", out)]
    ivs = []
    for s, e in zip(starts, ends):
        ivs.append((s, e))
    return ivs

def keep_from_silence(path, duration, noise_db="-30dB", d=0.3, pad=0.05):
    ivs = sorted(silence_intervals(path, noise_db, d))
    segs, cur = [], 0.0
    for s, e in ivs:
        s = max(0.0, s - pad); e = min(duration, e + pad)
        if s > cur:
            segs.append((cur, s))
        cur = max(cur, e)
    if cur < duration:
        segs.append((cur, duration))
    return segs
```

- [ ] **Step 2: Add fumble (whisper long-pause) flagging + optional cut**

```python
FUMBLE_CUT_SEC = 4.0      # silent/wordless gap longer than this -> cut
FUMBLE_FLAG_SEC = 1.5     # gap longer than this -> review marker (no cut)

def fumble_gaps(alignment, duration):
    gaps = []
    if not alignment:
        return gaps
    words = sorted(alignment, key=lambda w: w.t_start)
    prev_end = 0.0
    for w in words:
        gap = w.t_start - prev_end
        if gap >= FUMBLE_FLAG_SEC:
            gaps.append((prev_end, w.t_start, gap))
        prev_end = w.t_end
    gaps.append((prev_end, duration, duration - prev_end))
    return gaps
```
Plan: remove intervals where a fumble gap ≥ `FUMBLE_CUT_SEC` AND ffmpeg also flagged silence there (intersection) — i.e. genuinely empty. Flag 1.5–4.0s gaps as review markers only (never delete spoken content).

- [ ] **Step 3: Smoke-test segment counts**

Print keep-segments per asset. Expected: each asset yields multiple segments separated by silence; total trimmed duration < raw duration.

---

### Task 4: Build the ordered timeline via IR ops

**Files:**
- Modify: `/home/ah64/apps/mlt-pipeline/open_edit/scripts/build_timeline.py`

**Interfaces:**
- Consumes: `keep_segments`, `open_edit.ir.types.AddClipOp`, `open_edit.storage.edit_graph.EditGraphStore.append`, `open_edit.agent.tools.add_marker`
- Produces: appended `add_clip` ops for all 3 assets in order; `add_marker` notes at each cut

- [ ] **Step 1: Append AddClipOp per keep-segment, in order 1→2→3**

```python
from open_edit.ir.types import AddClipOp
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.agent.tools import add_marker

ORDER = ["f6f74b…", "81b720…", "6cc047…"]  # exact hashes, 1.mp4 -> 2.mp4 -> 3.mp4
DB = "/home/ah64/OpenEditProjects/ll/.open_edit/edit_graph.db"
PROJECT_ID = "ll"
store = EditGraphStore(DB)
TRACK = "v1"
pos = 0.0
for h in ORDER:
    for (a, b) in keep_segments[h]:
        dur = b - a
        if dur < 0.1:
            continue
        op = AddClipOp(
            asset_hash=h, track_id=TRACK, track_kind="video",
            position_sec=round(pos, 3), in_point_sec=round(a, 3),
            out_point_sec=round(b, 3), author="ai",
        )
        store.append(op)
        add_marker({"project_id": PROJECT_ID, "t_start": pos,
                    "t_end": pos + dur,
                    "text": f"clip {h[:8]} keep [{a:.2f}-{b:.2f}]"},
                   "/home/ah64/OpenEditProjects/ll")
        pos += dur
print("timeline end:", pos)
```
Note: `AddClipOp` auto-creates track `v1` via `_get_or_create_track`. `position_sec` is cumulative timeline position (kept segments concatenated). `out_point_sec` is asset-local; `b` already is asset-local (segments computed from asset timeline), so this is correct.

- [ ] **Step 2: Run the builder**

Run:
```bash
/home/ah64/apps/mlt-pipeline/open_edit/.venv/bin/python scripts/build_timeline.py
```
Expected: prints `timeline end: <N>` where N ≈ sum of all kept durations (well under 1933s raw total).

---

### Task 5: Verify the derived timeline

**Files:**
- Script: reuse `scripts/build_timeline.py` (add a verify block) or a one-off

**Interfaces:**
- Consumes: `open_edit.ir.apply.derive_or_load_timeline`, `EditGraphStore.load_all`
- Produces: human-readable verification

- [ ] **Step 1: Derive + assert ordering and durations**

```python
from open_edit.ir.apply import derive_or_load_timeline
ops = store.load_all()
tl = derive_or_load_timeline(ops, project_id=PROJECT_ID)
clips = [c for c in tl.clips if c.track_id == "v1"]
print("clip count:", len(clips))
for c in sorted(clips, key=lambda c: c.position_sec):
    print(f"  pos={c.position_sec:8.2f} src={c.asset_hash[:8]} "
          f"in={c.in_point_sec:8.2f} out={c.out_point_sec:8.2f}")
print("first asset:", clips[0].asset_hash[:8], "== 1.mp4 hash f6…")
print("last  asset:", clips[-1].asset_hash[:8], "== 3.mp4 hash 6c…")
```
Expected: clips sorted by position show asset hashes in order f6… → 81… → 6c…; no two consecutive clips from the same asset overlap (silence removed).

- [ ] **Step 2: Commit the work scripts + note local-only**

```bash
git add scripts/retx_assets.py scripts/build_timeline.py
git commit -m "tooling: whisper re-transcribe + ordered silence-trimmed timeline build"
```
Note: this commits only the scripts, NOT the project DB. The edit graph lives in `/home/ah64/OpenEditProjects/ll` (outside the repo).

---

## Self-Review
- Spec coverage: Whisper install (Task 1–2), fumble/silence detection (Task 3), ordered trimmed timeline via IR (Task 4), verification (Task 5). Covered.
- Placeholders: none — exact paths, hashes placeholders marked to fill with the real 64-hex from `list_assets`, exact function calls shown.
- Type consistency: `AddClipOp` fields match `ir/types.py:118` (`asset_hash, track_id, track_kind, position_sec, in_point_sec, out_point_sec, clip_id, author, kind`). `add_marker(args, project_path)` matches `pyagent_add_marker.py:16`. `EditGraphStore.append(op)` matches `edit_graph.py:114`. `derive_or_load_timeline(ops, project_id=...)` matches `ir/apply.py`.
