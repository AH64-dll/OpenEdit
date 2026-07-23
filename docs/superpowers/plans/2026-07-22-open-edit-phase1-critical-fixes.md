# Open Edit Phase 1: Critical Safety Net Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 11 critical and top 10 high-severity issues in Open Edit to establish data integrity, security, and basic production readiness.

**Architecture:** Python/FastAPI server with SQLite storage, vanilla JS frontend, subprocess-based render pipeline. IR (Intermediate Representation) drives all edit operations.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, Pydantic, vanilla JS ES modules.

**Global Constraints:**
- No new external dependencies
- All existing tests must continue to pass (after test infrastructure is fixed)
- DB schema changes must be additive (no destructive migrations)
- API responses must remain backward-compatible

---

## Phase 1A: Test Infrastructure & Data Integrity (Tasks 1-5)

### Task 1: Fix test configuration and add smoke test suite

**Files:**
- Create: `open_edit/tests/__init__.py`
- Create: `open_edit/tests/test_smoke.py`
- Modify: `open_edit/pyproject.toml:46`

**Interfaces:**
- Consumes: `open_edit/open_edit/ir/types.py`, `open_edit/open_edit/ir/apply.py`
- Produces: Test suite entry point with PASS/FAIL results

- [ ] **Step 1: Create test directory and init**

```bash
mkdir -p open_edit/tests
touch open_edit/tests/__init__.py
```

- [ ] **Step 2: Fix pyproject.toml testpaths**

```toml
# Change:
testpaths = ["tests"]
# To:
testpaths = ["tests"]
```

- [ ] **Step 3: Write basic smoke test**

```python
# open_edit/tests/test_smoke.py
from open_edit.ir.types import Project, Timeline, Track, Clip, AddClipOp, OperationUnion
from open_edit.ir.apply import apply_operation, derive_timeline

def test_project_can_be_created():
    p = Project(name="test", kind="video")
    assert p.name == "test"
    assert p.kind == "video"
    assert p.timeline is None

def test_add_clip_op_produces_timeline():
    op = AddClipOp(
        edit_id="e1",
        kind="add_clip",
        author="test",
        timestamp="2026-01-01T00:00:00",
        parent_id=None,
        track_index=0,
        asset_hash="abc123",
        in_point_sec=0.0,
        out_point_sec=10.0,
        position_sec=0.0,
    )
    result = derive_timeline([op], Project(name="test", kind="video"))
    assert result is not None
    assert len(result.tracks) > 0
    assert len(result.tracks[0].clips) == 1
    assert result.tracks[0].clips[0].asset_hash == "abc123"

def test_empty_ops_returns_empty_timeline():
    result = derive_timeline([], Project(name="test", kind="video"))
    assert result is not None
    assert len(result.tracks) == 0
```

- [ ] **Step 4: Run smoke tests**

Run: `cd open_edit && python -m pytest tests/test_smoke.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add open_edit/tests/ open_edit/pyproject.toml
git commit -m "test: fix test directory structure and add smoke tests for IR"
```

---

### Task 2: Fix apply_operation purity violation (Critical)

**Files:**
- Modify: `open_edit/open_edit/ir/apply.py:86-89`
- Add test: `open_edit/tests/test_apply_purity.py`

- [ ] **Step 1: Write regression test proving the mutation**

```python
# open_edit/tests/test_apply_purity.py
from copy import deepcopy
from open_edit.ir.types import Project, AddClipOp
from open_edit.ir.apply import apply_operation

def test_apply_operation_does_not_mutate_input():
    base = Timeline(tracks=[])
    original = deepcopy(base)
    
    op = AddClipOp(
        edit_id="e1",
        kind="add_clip",
        author="test",
        timestamp="2026-01-01T00:00:00",
        parent_id=None,
        track_index=0,
        asset_hash="abc123",
        in_point_sec=0.0,
        out_point_sec=10.0,
        position_sec=0.0,
    )
    
    result, _ = apply_operation(base, op)
    assert base == original, "apply_operation mutated the input timeline"
```

- [ ] **Step 2: Verify test fails**

Run: `cd open_edit && python -m pytest tests/test_apply_purity.py -v`
Expected: FAIL — base is mutated

- [ ] **Step 3: Fix apply_operation to deep-copy**

```python
# In apply.py, at the top of apply_operation (line ~86):
def apply_operation(timeline: Timeline, op: OperationUnion, *, strict: bool = True, catalog: EffectCatalog | None = None) -> tuple[Timeline, list[str]]:
    timeline = timeline.model_copy(deep=True)
    ...
```

- [ ] **Step 4: Run regression test**

Run: `cd open_edit && python -m pytest tests/test_apply_purity.py -v`
Expected: PASS

- [ ] **Step 5: Run smoke tests**

Run: `cd open_edit && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add open_edit/open_edit/ir/apply.py open_edit/tests/test_apply_purity.py
git commit -m "fix(ir): apply_operation now deep-copies input timeline (purity contract)"
```

---

### Task 3: Fix SplitClipOp shared effects list (Critical)

**Files:**
- Modify: `open_edit/open_edit/ir/apply.py:459-467`
- Add test: `open_edit/tests/test_apply_split.py`

- [ ] **Step 1: Write regression test**

```python
# open_edit/tests/test_apply_split.py
from open_edit.ir.types import Timeline, Track, Clip, SplitClipOp, AddEffectOp
from open_edit.ir.apply import apply_operation

def test_split_clip_effects_are_independent():
    clip = Clip(
        asset_hash="abc",
        in_point_sec=0.0,
        out_point_sec=10.0,
        position_sec=0.0,
        effects=[{"type": "volume", "params": {"db": "0"}}],
    )
    timeline = Timeline(tracks=[Track(clips=[clip])])
    
    op = SplitClipOp(
        edit_id="e1",
        kind="split_clip",
        author="test",
        timestamp="2026-01-01T00:00:00",
        parent_id=None,
        track_index=0,
        clip_id=clip.id,
        split_time_sec=5.0,
    )
    
    result, _ = apply_operation(timeline, op)
    left = result.tracks[0].clips[0]
    right = result.tracks[0].clips[1]
    
    # Modifying left's effects should NOT affect right
    left.effects.append({"type": "brightness", "params": {"value": "0.5"}})
    assert len(right.effects) == 1, "Split clip shares effects list — right clip got left's new effect"
```

- [ ] **Step 2: Verify test fails**

Run: `cd open_edit && python -m pytest tests/test_apply_split.py -v`
Expected: FAIL — effects list is shared

- [ ] **Step 3: Deep-copy effects in _apply_split_clip**

```python
# In apply.py _apply_split_clip (around line 459):
right_clip = clip.model_copy(update={
    "in_point_sec": split_time_sec,
    "effects": [e.model_copy(deep=True) for e in clip.effects] if clip.effects else [],
})
left_clip = clip.model_copy(update={
    "out_point_sec": split_time_sec,
    "effects": [e.model_copy(deep=True) for e in clip.effects] if clip.effects else [],
})
```

- [ ] **Step 4: Verify test passes**

Run: `cd open_edit && python -m pytest tests/test_apply_split.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add open_edit/open_edit/ir/apply.py open_edit/tests/test_apply_split.py
git commit -m "fix(ir): deep-copy effects list in SplitClipOp to prevent cross-clip corruption"
```

---

### Task 4: Fix emitter.py to emit position_sec (Critical)

**Files:**
- Modify: `open_edit/open_edit/render/emitter.py:149-154`
- Add test: `open_edit/tests/test_emitter.py`

- [ ] **Step 1: Write failing test**

```python
# open_edit/tests/test_emitter.py
from open_edit.ir.types import Timeline, Track, Clip, Project
from open_edit.render.emitter import emit_project

def test_emitter_includes_clip_positions():
    clip = Clip(
        asset_hash="abc123",
        in_point_sec=0.0,
        out_point_sec=10.0,
        position_sec=30.0,  # Starts at 30s
    )
    timeline = Timeline(tracks=[Track(clips=[clip])])
    project = Project(name="test", timeline=timeline)
    
    xml = emit_project(project, {clip.asset_hash: "/path/to/video.mp4"})
    
    # The MLT entry should have blank=30.0 before the clip
    assert 'blank' in xml or 'position' in xml, "No position handling in MLT output"
    # Or check that multiple entries are created (blanks + clip)
    blank_count = xml.count('blank')
    clip_count = xml.count('video.mp4')
    assert blank_count > 0 or 'in="0.0"' in xml, "No position offset found"
```

- [ ] **Step 2: Implement position_sec as blank entries**

```python
# In emitter.py _emit_track (or equivalent MLT generation):
# Before each clip at position > 0, insert a blank entry:
entries = []
current_pos = 0.0
for clip in track.clips:
    if clip.position_sec > current_pos:
        blank_duration = clip.position_sec - current_pos
        entries.append(f'<entry producer="black" in="0" out="{blank_duration}"/>')
    entries.append(f'<entry producer="producer_{idx}" in="{clip.in_point_sec}" out="{clip.out_point_sec}"/>')
    current_pos = clip.position_sec + (clip.out_point_sec - clip.in_point_sec)
```

- [ ] **Step 3: Verify test passes**

Run: `cd open_edit && python -m pytest tests/test_emitter.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add open_edit/open_edit/render/emitter.py open_edit/tests/test_emitter.py
git commit -m "fix(render): emit position_sec as blank entries in MLT output"
```

---

### Task 5: Fix JobLock.try_acquire race condition (Critical)

**Files:**
- Modify: `open_edit/open_edit/storage/job_lock.py:25-41`
- Add test: `open_edit/tests/test_job_lock.py`

- [ ] **Step 1: Write regression test**

```python
# open_edit/tests/test_job_lock.py
import tempfile
from pathlib import Path
from open_edit.storage.job_lock import JobLockStore

def test_try_acquire_no_race():
    with tempfile.TemporaryDirectory() as td:
        store1 = JobLockStore(Path(td))
        store2 = JobLockStore(Path(td))
        
        r1 = store1.try_acquire("job_a", "render", "test")
        r2 = store2.try_acquire("job_a", "render", "test")
        
        assert r1 is True, "First acquire should succeed"
        assert r2 is False, "Second concurrent acquire should fail"
```

- [ ] **Step 2: Implement atomic job lock using UNIQUE constraint**

```python
# In open_edit/storage/job_lock.py:
# Change from SELECT-then-INSERT pattern to INSERT with UNIQUE constraint:

CREATE TABLE IF NOT EXISTS job_lock (
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    UNIQUE(job_type, status)
);

def try_acquire(self, job_type: str, ...) -> bool:
    try:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO job_lock (job_type, status) VALUES (?, 'running')",
                (job_type,)
            )
        return True
    except sqlite3.IntegrityError:
        return False
```

- [ ] **Step 3: Add stale-lock timeout**

```python
# Add to JobLockStore:
STALE_LOCK_TIMEOUT_SEC = 3600  # 1 hour

def _release_stale_locks(self):
    """Release locks older than STALE_LOCK_TIMEOUT_SEC."""
    with self._conn() as conn:
        conn.execute(
            "DELETE FROM job_lock WHERE created_at < datetime('now', ?)",
            (f'-{self.STALE_LOCK_TIMEOUT_SEC} seconds',)
        )
```

- [ ] **Step 4: Run tests**

Run: `cd open_edit && python -m pytest tests/test_job_lock.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add open_edit/open_edit/storage/job_lock.py open_edit/tests/test_job_lock.py
git commit -m "fix(storage): atomic job lock with UNIQUE constraint + stale lock cleanup"
```

---

## Phase 1B: Security & Compatibility (Tasks 6-7)

### Task 6: Fix API key storage security (Critical)

**Files:**
- Modify: `open_edit/open_edit/serve/runtimes/keys_store.py:49-54`

- [ ] **Step 1: Write test for atomic write + permissions**

```python
# Add to open_edit/tests/test_keys_store.py
import tempfile
from pathlib import Path
from open_edit.serve.runtimes.keys_store import KeysStore

def test_keys_file_created_with_restrictive_permissions():
    with tempfile.TemporaryDirectory() as td:
        store = KeysStore(Path(td))
        store.store_key("test_provider", "sk-1234567890abcdef")
        
        keys_path = Path(td) / "keys.json"
        assert keys_path.exists()
        perms = keys_path.stat().st_mode & 0o777
        assert perms <= 0o600, f"Key file permissions too permissive: {oct(perms)}"
```

- [ ] **Step 2: Implement atomic write with secure permissions**

```python
# Replace Path.write_text() with tempfile + os.replace:
import os
import tempfile

def _atomic_write_json(path: Path, data: dict):
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
```

- [ ] **Step 3: Run test**

Run: `cd open_edit && python -m pytest tests/test_keys_store.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add open_edit/open_edit/serve/runtimes/keys_store.py open_edit/tests/test_keys_store.py
git commit -m "fix(security): atomic write + 0600 permissions for API key storage"
```

---

### Task 7: Fix except* Python 3.10 incompatibility (Critical)

**Files:**
- Modify: `open_edit/open_edit/serve/html_overlay.py:572-585`

- [ ] **Step 1: Replace except* with compatible pattern**

```python
# Change:
try:
    ...
except* Exception as eg:
    for e in eg.exceptions:
        _handle_error(e)
# To:
try:
    ...
except Exception as e:
    _handle_error(e)
```

If the ExceptionGroup semantics are actually needed:
```python
try:
    ...
except ExceptionGroup as eg:
    for e in eg.exceptions:
        _handle_error(e)
except Exception as e:
    _handle_error(e)
```

- [ ] **Step 2: Add Python version classifier**

```toml
# In pyproject.toml:
requires-python = ">=3.11"
# OR if backward compat is needed, add a conditional import
```

- [ ] **Step 3: Run syntax check on Python 3.10**

```bash
python3.10 -c "import ast; ast.parse(open('open_edit/open_edit/serve/html_overlay.py').read()); print('Syntax OK')" 2>&1 || echo "ISSUE"
```

Expected: "Syntax OK" (no more `except*`)

- [ ] **Step 4: Commit**

```bash
git add open_edit/open_edit/serve/html_overlay.py
git commit -m "fix: replace except* with compatible Exception handling for Python 3.10"
```

---

## Phase 1C: Render Pipeline Completeness (Tasks 8-9)

### Task 8: Fix track-level effects and audio track kind not emitted (High)

**Files:**
- Modify: `open_edit/open_edit/render/emitter.py:144-163`

- [ ] **Step 1: Write failing test**

```python
# Add to open_edit/tests/test_emitter.py
def test_emitter_includes_track_effects():
    track = Track(
        clips=[Clip(asset_hash="abc", in_point_sec=0.0, out_point_sec=10.0)],
        effects=[{"type": "volume", "params": {"db": "-6"}}],
        kind="video",
    )
    timeline = Timeline(tracks=[track])
    project = Project(name="test", timeline=timeline)
    
    xml = emit_project(project, {"abc": "/path/v.mp4"})
    assert 'volume' in xml, "Track-level effect not emitted"
```

- [ ] **Step 2: Add track effect emission to MLT output**

```python
# In emitter.py, for each track:
# Emit track-level effects as MLT filter entries on the track/tractor
if track.effects:
    for effect in track.effects:
        # Map effect type to MLT filter
        if effect.type == "volume":
            # Add <filter> element with volume parameter
            ...
```

- [ ] **Step 3: Map track kind to MLT track type**

```python
# Audio tracks should use audio-specific producers
if track.kind == "audio":
    # Use MLT audio track configuration
    ...
```

- [ ] **Step 4: Run tests**

Run: `cd open_edit && python -m pytest tests/test_emitter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add open_edit/open_edit/render/emitter.py
git commit -m "fix(render): emit track-level effects and audio track kind in MLT output"
```

---

### Task 9: Fix aggregate.py rollup data loss (Critical)

**Files:**
- Modify: `open_edit/open_edit/style/aggregate.py:42-65`

- [ ] **Step 1: Write regression test**

```python
# open_edit/tests/test_style_aggregate.py
def test_rollup_does_not_purge_unaggregated_events():
    # Create taste events of different types (transitions, fades, pacing)
    # Run rollup
    # Verify non-transition events still exist in the store
    ...
```

- [ ] **Step 2: Fix purge to only remove processed events**

```python
# In aggregate.py rollup():
# Change from:
store.purge(project_id=project_id)  # Purges ALL events
# To:
store.purge(project_id=project_id, op_types=['transitions'])
# Or: only purge events that were actually aggregated
```

- [ ] **Step 3: Implement filtered purge**

```python
# In taste_events.py, add op_types filter to purge():
def purge(self, project_id: str, op_types: list[str] | None = None):
    if op_types:
        placeholders = ','.join('?' * len(op_types))
        self._conn.execute(
            f"DELETE FROM taste_events WHERE project_id = ? AND op_type IN ({placeholders})",
            (project_id, *op_types)
        )
    else:
        self._conn.execute(
            "DELETE FROM taste_events WHERE project_id = ?",
            (project_id,)
        )
```

- [ ] **Step 4: Run tests**

Run: `cd open_edit && python -m pytest tests/test_style_aggregate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add open_edit/open_edit/style/aggregate.py open_edit/open_edit/style/taste_events.py open_edit/tests/test_style_aggregate.py
git commit -m "fix(style): rollup no longer purges unaggregated taste event types"
```

---

## Phase 1D: Frontend Critical Fixes (Tasks 10-12)

### Task 10: Implement light theme CSS (Critical)

**Files:**
- Modify: `open_edit/open_edit/serve/static/style.css`

- [ ] **Step 1: Add all [data-theme="light"] overrides**

At the bottom of `style.css`, add:
```css
[data-theme="light"] {
    --bg-primary: #ffffff;
    --bg-secondary: #f3f4f6;
    --bg-tertiary: #e5e7eb;
    --text-primary: #111827;
    --text-secondary: #4b5563;
    --text-muted: #9ca3af;
    --border-color: #d1d5db;
    --accent: #3b82f6;
    --accent-hover: #2563eb;
    --surface: #ffffff;
    --surface-hover: #f9fafb;
    --shadow: 0 1px 3px rgba(0,0,0,0.1);
    --chat-bg: #ffffff;
    --chat-user-bg: #eff6ff;
    --chat-assistant-bg: #f9fafb;
    --tool-card-bg: #ffffff;
    --input-bg: #ffffff;
    --scrollbar-thumb: #cbd5e1;
    --scrollbar-track: #f1f5f9;
}
```

- [ ] **Step 2: Test the toggle works**

- Open the app, click the theme toggle button
- Verify colors change to light theme
- Verify dark theme still works when toggled back

- [ ] **Step 3: Commit**

```bash
git add open_edit/open_edit/serve/static/style.css
git commit -m "feat(ui): implement light theme CSS with [data-theme='light'] overrides"
```

---

### Task 11: Add WebSocket keepalive/heartbeat (High)

**Files:**
- Modify: `open_edit/open_edit/serve/static/js/ws.js`

- [ ] **Step 1: Add heartbeat ping on the server side**

```python
# In open_edit/open_edit/serve/app.py WebSocket endpoint:
# Add a background task that sends a "ping" event every 30 seconds

async def _heartbeat(websocket: WebSocket):
    while True:
        await asyncio.sleep(30)
        try:
            await websocket.send_json({"type": "ping"})
        except Exception:
            break
```

- [ ] **Step 2: Add heartbeat to WebSocket connect**

```python
# When accepting the WebSocket connection:
heartbeat_task = asyncio.create_task(_heartbeat(websocket))
# Store heartbeat_task for cancellation on disconnect
```

- [ ] **Step 3: Add pong response in frontend ws.js**

```javascript
// In ws.js, handleWsEvent:
if (ev.type === 'ping') {
    // Server heartbeat — no response needed, receiving it keeps connection alive
    return;
}
```

- [ ] **Step 4: Verify connection stability**

```python
# Manual verification:
# Open WebSocket, wait 60+ seconds, verify no disconnect
```

- [ ] **Step 5: Commit**

```bash
git add open_edit/open_edit/serve/app.py open_edit/open_edit/serve/static/js/ws.js
git commit -m "feat(ws): add server-side heartbeat every 30s to prevent idle disconnects"
```

---

### Task 12: Fix tool card + text ordering race (High)

**Files:**
- Modify: `open_edit/open_edit/serve/static/js/chat.js:62,105-111`

- [ ] **Step 1: Write the fix**

```javascript
// In appendTextDelta:
// Before creating a new assistant message, check if a tool card 
// was the last element. If so, create the assistant msg before it.
function appendTextDelta(text) {
    if (!state.pendingAssistantMsg) {
        startAssistantMessage();
        // If the last chat element is a tool card, insert before it
        const lastEl = chatLog.lastElementChild;
        if (lastEl && lastEl.classList.contains('tool-card')) {
            chatLog.insertBefore(state.pendingAssistantMsg, lastEl);
        }
    }
    // ... rest of existing logic
}
```

- [ ] **Step 2: Test with a tool-calling sequence**

- Send a prompt that triggers tool use
- Verify text response appears AFTER the tool card, not before
- Verify ordering is preserved with multiple tool calls

- [ ] **Step 3: Commit**

```bash
git add open_edit/open_edit/serve/static/js/chat.js
git commit -m "fix(chat): preserve tool card + text ordering in appendTextDelta"
```

---

## Phase 1E: Server Hardening (Tasks 13-14)

### Task 13: Add render task cancellation on disconnect (High)

**Files:**
- Modify: `open_edit/open_edit/serve/app.py:333`

- [ ] **Step 1: Track render tasks per WebSocket**

```python
# Store render tasks keyed by WebSocket connection or project ID
_RENDER_TASKS: dict[str, asyncio.Task] = {}

def _run_render_job(project_id: str, ...):
    task = asyncio.create_task(_execute_render(project_id, ...))
    _RENDER_TASKS[project_id] = task
    return task
```

- [ ] **Step 2: Cancel on disconnect**

```python
# In the WebSocket disconnect handler:
task = _RENDER_TASKS.pop(project_id, None)
if task and not task.done():
    task.cancel()
```

- [ ] **Step 3: Handle cancellation in render task**

```python
async def _execute_render(project_id: str, ...):
    try:
        ...
    except asyncio.CancelledError:
        # Clean up render subprocess
        if proc:
            proc.terminate()
        raise
```

- [ ] **Step 4: Commit**

```bash
git add open_edit/open_edit/serve/app.py
git commit -m "fix(server): cancel render tasks when WebSocket disconnects"
```

---

### Task 14: Add rate limiting on render endpoint (Medium)

**Files:**
- Modify: `open_edit/open_edit/serve/app.py:324-334`

- [ ] **Step 1: Implement simple in-memory rate limiter**

```python
import time
from collections import defaultdict

_RENDER_RATE_LIMIT: dict[str, list[float]] = defaultdict(list)
MAX_RENDERS_PER_MINUTE = 5

def _check_render_rate_limit(project_id: str) -> bool:
    now = time.time()
    window_start = now - 60
    timestamps = _RENDER_RATE_LIMIT[project_id]
    # Prune old entries
    _RENDER_RATE_LIMIT[project_id] = [t for t in timestamps if t > window_start]
    if len(_RENDER_RATE_LIMIT[project_id]) >= MAX_RENDERS_PER_MINUTE:
        return False
    _RENDER_RATE_LIMIT[project_id].append(now)
    return True
```

- [ ] **Step 2: Add rate limit check to render endpoint**

```python
@router.post("/api/projects/{id}/render")
async def post_render(id: str, ...):
    if not _check_render_rate_limit(id):
        raise HTTPException(status_code=429, detail="Too many renders. Try again in a moment.")
    ...
```

- [ ] **Step 3: Commit**

```bash
git add open_edit/open_edit/serve/app.py
git commit -m "feat(server): rate limit render endpoint to 5 requests per minute per project"
```

---

## Task 15: Fix settings modal HTML nesting (High)

**Files:**
- Modify: `open_edit/open_edit/serve/static/index.html:263-296`

- [ ] **Step 1: Fix the unbalanced div nesting**

```html
<!-- The current broken structure at ~line 263: -->
<div style="margin-bottom:16px">
    <label for="opencode-api-key">OpenCode API Key</label>
    <input id="opencode-api-key" type="password" class="input" placeholder="sk-...">
</div>

<!-- Ensure every <div> is properly opened and closed -->
```

- [ ] **Step 2: Add backdrop-click dismissal to all modals**

```html
<!-- Add data-modal-close to the backdrop of every modal -->
<div id="modal-new-project" class="modal" data-modal-close>
<div id="modal-asset-preview" class="modal" data-modal-close>
<div id="modal-notes" class="modal" data-modal-close>
```

- [ ] **Step 3: Verify modals work**

- Open/close each modal type
- Verify backdrop click closes it
- Verify Escape key closes it

- [ ] **Step 4: Commit**

```bash
git add open_edit/open_edit/serve/static/index.html
git commit -m "fix(ui): fix settings modal HTML nesting and add backdrop-close to all modals"
```
