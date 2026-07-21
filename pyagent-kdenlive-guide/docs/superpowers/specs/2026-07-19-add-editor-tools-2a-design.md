# PyAgent for Kdenlive — Sub-project 2a: Core editor tools

**Sub-project 2a of 3.** Sub-project 1 (cleanup) shipped; sub-project
2b (advanced tools: variable-rate speed, undo/redo, keyframes,
compound clips, master effects, color tools) is future; sub-project 3
(end-to-end AI + real-Kdenlive verification) is future.

## Problem

After the cleanup, pyagent exposes 19 editor tools. The user
identified a gap: many common NLE operations have no tool. The
AI cannot slip a clip, ripple-delete a gap, change playback speed,
split a clip, replace its source, group clips together, or remove
an effect/transition it no longer wants. Without these, the AI
falls back to "delete and re-insert" workarounds that lose
in-point/out-point precision, transition timing, and effect stacks.

This sub-project adds 10 new tools that cover the high-frequency
edits. The remaining advanced operations land in sub-project 2b.

## Goals

- 10 new tools that follow the existing per-domain pattern
  (ToolDef in `tools/*.py`, op function in `ops/*.py`,
  OP_TABLE entry, golden-file fixture, behavior test).
- Real-Kdenlive interop for group data: files written by
  pyagent open cleanly in the Kdenlive app, and groups created
  by pyagent survive an "open → re-save" cycle in the app.
- All 10 tools' JSON I/O locked by golden-file tests.
- All 10 tools' behavior verified by per-domain integration tests.
- 4 commits, one per domain, each independently testable.
- No behavior change for the 19 existing tools.

## Non-goals (this sub-project)

- Variable-rate speed (keyframe-based ramps). (Sub-project 2b.)
- Undo / redo tool exposure. (Sub-project 2b.)
- Multi-clip ops (apply effect to all in group, batch operations).
  (Sub-project 2b.)
- Keyframe manipulation tools. (Sub-project 2b.)
- Compound clip creation / nesting. (Sub-project 2b.)
- Color tools / scopes. (Sub-project 2b.)
- Master / track-level effects. (Sub-project 2b.)
- Replace with propagation (replace all clips referencing a
  source). (Sub-project 2b.)
- Transition edit (change duration, kind). (Sub-project 2b.)
- Effect param editing (change effect params after apply).
  (Sub-project 2b.)
- AVSplit group creation or destruction. (Kdenlive manages
  AVSplit groups; pyagent only creates `Normal` groups.)
- Subtitle / composition group targets. (Sub-project 2b if needed.)
- Sub-project 3 entirely.

## The 3-sub-project plan (recap)

| # | Sub-project | Status |
|---|---|---|
| 1 | Cleanup (rewrite for clarity, fix bugs, behavior unchanged) | Done |
| 2a | Core editor tools (this spec) | In design |
| 2b | Advanced tools (variable speed, undo, keyframes, etc.) | Future |
| 3 | End-to-end verification with real Kdenlive + real AI | Future |

---

## Architecture (this sub-project)

The 10 new tools follow the existing per-domain pattern from the
cleanup. No new abstractions, no new modules in the runtime layer.

**File layout** (additions marked `+`):

```
phase2_project_engine/ops/
  bin.py            (unchanged)
  clips.py          (unchanged: 5 placement ops)
+ clips_edit.py     (NEW: slip_clip, ripple_delete_clip,
                       change_clip_speed, split_clip,
                       replace_clip_source)
  effects.py        (extended: +remove_effect)
  transitions.py    (extended: +remove_transition)
  markers.py        (unchanged)
+ groups.py         (NEW: group_clips, ungroup_clips, list_groups)
  __init__.py       (extended: +clips_edit, +groups)

phase3_pyagent_core/tools/
  bin.py            (unchanged)
  catalog.py        (unchanged)
  clips.py          (unchanged: 5 ToolDefs)
+ clips_edit.py     (NEW: 5 ToolDefs)
  effects.py        (extended: +1 ToolDef)
  transitions.py    (extended: +1 ToolDef)
  markers.py        (unchanged)
  project.py        (unchanged)
  render_qc.py      (unchanged)
+ groups.py         (NEW: 3 ToolDefs)
  __init__.py       (extended: +clips_edit, +groups)

phase3_pyagent_core/runtime.py
  OP_TABLE          (extended: +10 entries)
  MUTATING_OPS      (extended: +9 entries; list_groups read-only)

phase3_pyagent_core/tests/
  test_golden_io.py (extended: +10 parametrized cases)
  fixtures/golden_io.json  (extended: +10 entries)

phase2_project_engine/tests/
  test_ops_clips.py       (extended: +5 test functions)
  test_ops_effects.py     (extended: +1 test function)
  test_ops_transitions.py (extended: +1 test function)
+ test_ops_groups.py      (NEW: 3 test functions)

phase7_real_session/tests/
  test_e2e.py             (extended: +1 interop test,
                           skipif_kdenlive_missing)
```

**Per-domain file sizes (post-additions, expected):**

| File | LoC (est) | Under 300? |
|---|---|---|
| `ops/clips.py` | 209 (unchanged) | yes |
| `ops/clips_edit.py` | ~140 | yes |
| `ops/effects.py` | ~95 | yes |
| `ops/transitions.py` | ~115 | yes |
| `ops/groups.py` | ~110 | yes |
| `tools/clips.py` | 78 (unchanged) | yes |
| `tools/clips_edit.py` | ~110 | yes |
| `tools/effects.py` | ~50 | yes |
| `tools/transitions.py` | ~50 | yes |
| `tools/groups.py` | ~75 | yes |
| `test_ops_clips.py` | ~330 (was ~190) | yes |
| `test_ops_effects.py` | ~95 | yes |
| `test_ops_transitions.py` | ~80 | yes |
| `test_ops_groups.py` (NEW) | ~200 | yes |

**Conventions** (inherited from the cleanup):

- Every prod file <300 lines, every test file <400 lines.
- ToolDef = frozen dataclass with name/label/description/op/is_mutating/parameters_schema/required.
- Op function = pure mutation in `phase2_project_engine/ops/<domain>.py`. No I/O.
- Golden-file I/O test locks params + response shape.
- Auto-save after any mutating op (existing `MUTATING_OPS` machinery in `runtime.py`).

**TypeScript exposure**: `extension.ts` calls
`runtime.list_tools()` at load time (extension.ts:62-65) and
iterates the result. New tools are auto-exposed. **No TypeScript
changes required.**

---

## The 10 tool schemas

Standard return envelope: success returns a JSON-serializable
dict; failure raises `ValidationError`/`NotFoundError` (existing
errors module, no new error types). All `is_mutating=True` except
`list_groups`.

---

**Domain: clips-edit** (5 tools, all in `tools/clips_edit.py` / `ops/clips_edit.py`)

### 1. `pyagent_slip_clip` — source shift in fixed timeline window

```yaml
op: slip_clip
params: {clip_id: str, delta_sec: number}
required: (clip_id, delta_sec)
returns: {clip_id, source_id, source_in_sec, source_out_sec,
          track_index, timeline_start_sec, duration_sec}
errors: clip_not_found, source_oob
```

`delta_sec > 0` shifts source media later; `delta_sec < 0` shifts
it earlier. The clip's timeline position and duration stay the
same. Source out-of-bounds raises `source_oob`
(NotFoundError — the entity at the requested position doesn't
exist in the current source media).

### 2. `pyagent_ripple_delete_clip` — delete + close gap on same track

```yaml
op: ripple_delete_clip
params: {clip_id: str}
required: (clip_id,)
returns: {deleted_clip_id, shifted_clip_ids: [str]}
errors: clip_not_found
```

Removed clip is gone; every clip on the same track whose
`timeline_start_sec` was greater than the removed clip's start
has that value reduced by the removed clip's duration. Clips on
other tracks are unaffected.

### 3. `pyagent_change_clip_speed` — constant rate

```yaml
op: change_clip_speed
params: {clip_id: str, rate: number}   # 1.0=normal, 2.0=2x faster
required: (clip_id, rate)
returns: {clip_id, source_id, source_in_sec, source_out_sec,
          rate, old_duration_sec, new_duration_sec}
constraints: 0.1 <= rate <= 10.0
errors: clip_not_found, rate_out_of_range
```

Audio pitch is preserved (handled by the underlying MLT
producer). The LLM can re-apply this tool with `rate=1.0` to
revert.

### 4. `pyagent_split_clip` — single position

```yaml
op: split_clip
params: {clip_id: str, at_sec: number}
required: (clip_id, at_sec)
returns: {left_clip_id, right_clip_id}
constraints: at_sec strictly between clip.timeline_start and
             clip.timeline_end
errors: clip_not_found, split_position_invalid
```

The left half keeps the original `clip_id`; the right half is a
new clip with a fresh runtime id. Both span the original
source range.

### 5. `pyagent_replace_clip_source` — swap media, keep duration

```yaml
op: replace_clip_source
params: {clip_id: str, new_source_id: str}
required: (clip_id, new_source_id)
returns: {clip_id, old_source_id, new_source_id, old_rate,
          new_rate, old_duration_sec, new_duration_sec,
          source_in_sec, source_out_sec}
errors: clip_not_found, source_not_found
behavior: rate is RESET to 1.0 (the new media's natural pace).
          new source_in_sec = 0.
          new source_out_sec = min(old_timeline_duration,
                                   new_source_duration).
          new timeline duration = source_out_sec (since rate=1.0).
```

Rationale: simplest, most predictable. The LLM can re-apply
`change_clip_speed` after replace if a different rate is wanted.
Carrying rate forward would conflate source media identity
with playback rate.

---

**Domain: effects** (1 tool, in `tools/effects.py` / `ops/effects.py`)

### 6. `pyagent_remove_effect` — by index

```yaml
op: remove_effect
params: {clip_id: str, effect_index: int}
required: (clip_id, effect_index)
returns: {clip_id, removed_effect_index, removed_effect_id,
          remaining_effect_count}
errors: clip_not_found, effect_index_out_of_range
```

The LLM must first call `get_timeline_summary()` to see what
effect indices exist on a given clip.

---

**Domain: transitions** (1 tool, in `tools/transitions.py` / `ops/transitions.py`)

### 7. `pyagent_remove_transition` — by id

```yaml
op: remove_transition
params: {transition_id: str}
required: (transition_id,)
returns: {transition_id, affected_clip_ids: [str]}
errors: transition_not_found
```

The transition XML element is removed; the clip entries
bounded by it are not modified.

---

**Domain: groups** (3 tools, all in `tools/groups.py` / `ops/groups.py`)

### 8. `pyagent_group_clips` — create a Normal group

```yaml
op: group_clips
params: {clip_ids: [str], group_name: str}
required: (clip_ids, group_name)
returns: {group_name, clip_ids}
constraints: all clip_ids must exist; group_name non-empty
             and unique across the project
errors: clip_not_found, empty_clip_list, duplicate_group_name
internal:
  1. Resolve each clip_id to (track, pos, sublayer) via ProjectTree.
  2. Load kdenlive:sequenceproperties.groups from tractor
     (or [] if missing/empty).
  3. Append {type: "Normal", pyagent:name: group_name,
             children: [{type: "Leaf", leaf: "clip",
                         data: "<track>:<pos>:-1"}, ...]}.
  4. Save the updated JSON back to the property.
```

### 9. `pyagent_ungroup_clips` — dissolve a group

```yaml
op: ungroup_clips
params: {group_name: str}
required: (group_name,)
returns: {dissolved_group_name, affected_clip_ids: [str]}
errors: group_not_found
```

The group is removed from the JSON tree; the remaining
groups (if any) are untouched.

### 10. `pyagent_list_groups` — read-only query

```yaml
op: list_groups
is_mutating: false
params: {}   # no params
returns: {groups: [{group_name, clip_ids: [str]}]}
internal: load kdenlive:sequenceproperties.groups, walk the
          tree, resolve each Normal group's leaves by
          (track, pos) -> current clip_id via ProjectTree.
          Skip AVSplit groups (Kdenlive manages those).
```

---

## Storage of group data: real Kdenlive format

**Property key:** `kdenlive:sequenceproperties.groups` on the
tractor (verified at `timelineitemmodel.cpp:691` in Kdenlive
master). Kdenlive's `passSequenceProperties` writes the JSON
tree under this exact key.

**Value:** JSON-encoded string containing a JSON array of root
group objects (no envelope object).

**Shape:**

```json
[
  {
    "type": "Normal",
    "pyagent:name": "Intro",
    "children": [
      {"type": "Leaf", "leaf": "clip", "data": "1:120:-1"},
      {"type": "Leaf", "leaf": "clip", "data": "2:240:-1"}
    ]
  }
]
```

**`type` is one of:** `Normal` (user-created), `AVSplit`
(audio-video link, runtime-only), `Leaf` (a member).
Kdenlive's `GroupType` enum maps these to the string forms.
`Selection` is a runtime-only pseudo-group that is filtered
out before write and rejected on read.

**Leaf `data`:** `<track>:<pos>:<sublayer>`. Clip leaves use
the track and position of the clip on the timeline;
subtitles use `-2:<pos>:<sublayer>` (the `-2` track sentinel
identifies a subtitle). Sublayer is `-1` for clips and
compositions, `0+` for subtitles.

**Why position-based, not clip-id-based:** clip ids are
re-assigned on every project load (Kdenlive comment in
`groupsmodel.hpp`: "we cannot expect clipId nor groupId to be
the same on project reopening, thus we cannot rely on them
for saving. To workaround that, we currently identify clips
by their position + track"). Our resolution layer
(`group_clips` / `list_groups`) maps between clip_id (LLM's
handle) and (track, pos) (Kdenlive's persistent reference)
at every call.

**`pyagent:name` side-channel:** each group object carries a
`pyagent:name` field that Kdenlive's `fromJson()` ignores
(unknown fields are dropped). This lets us give groups
user-given names that survive an "open in Kdenlive → re-save
→ reload in pyagent" round trip. The LLM uses `group_name`
as the handle; no runtime UUIDs are minted.

**AVSplit handling:** `group_clips` only creates `Normal`
groups. `list_groups` skips `AVSplit` groups (Kdenlive owns
them). pyagent never creates or destroys AVSplit groups.

**No runtime group_id.** `ungroup_clips` and `list_groups` are
keyed by `group_name` (enforced unique by
`duplicate_group_name`). This avoids the cross-call identity
problem — the same name resolves to the same group on every
read, regardless of how many invocations have happened in
between.

---

## Error model

The 10 new tools use the existing 4-class hierarchy from
`phase2_project_engine/errors.py`. **No new error classes.**

| Error code | Class | When | `fix:` hint |
|---|---|---|---|
| `clip_not_found` | `NotFoundError` | clip_id doesn't resolve in the project | "call get_timeline_summary and re-pick" |
| `source_not_found` | `NotFoundError` | source_id not in the bin | "call list_catalog or import_media first" |
| `transition_not_found` | `NotFoundError` | transition_id not in any tractor | "call get_timeline_summary and re-pick" |
| `effect_index_out_of_range` | `NotFoundError` | effect_index >= effect count on that clip | "call get_timeline_summary to see valid indices" |
| `group_not_found` | `NotFoundError` | group_name not in the groups JSON | "call list_groups to see existing groups" |
| `split_position_invalid` | `NotFoundError` | at_sec outside the clip's timeline range | "use at_sec strictly between clip_start and clip_end" |
| `source_oob` | `NotFoundError` | slip delta would push source_in<0 or source_out>source_duration | "delta must keep source_in >= 0 and source_out <= source duration" |
| `rate_out_of_range` | `ValidationError` | rate outside 0.1..10.0 (policy range) | "use a rate between 0.1 and 10.0" |
| `empty_clip_list` | `ValidationError` | clip_ids is empty | "pass at least one clip_id" |
| `duplicate_group_name` | `ValidationError` | group_name already exists | "use a unique group_name; call list_groups to see existing names" |

**Rule for the boundary:** `NotFoundError` = "the entity at
this position/index/name doesn't exist in the current project
state" (re-list and re-pick). `ValidationError` = "the input
value violates a policy constraint" (change the value). This
rule is why `effect_index_out_of_range`, `source_oob`, and
`split_position_invalid` are all `NotFoundError` (the entity
at the requested position doesn't exist in the current
project state), and why `rate_out_of_range` and
`empty_clip_list` are `ValidationError` (policy constraints
on the input value).

**Response envelope** (unchanged from existing):

- Success: `{"ok": true, "result": {...}}`, exit code 0.
- Validation error: `{"ok": false, "error": "..."}` (with
  `fix:` line), exit code 1.
- Backend error: `{"ok": false, "fatal": true, "error": "..."}`,
  exit code 2.

---

## Testing approach: 3 layers

**Layer 1 — Golden-file I/O tests** (10 new fixtures, in `phase3_pyagent_core/tests/fixtures/golden_io.json`)

- One parametrized case per tool. Captures the response's
  keys, types, and non-timestamp values.
- The fixture grows from 6 entries to 16 (the 6 current
  read-only entries plus 10 new ones — 9 mutating + 1 read-only).
- Read-only (`list_groups`) runs against the demo fixture
  directly.
- Mutating tools copy the demo to tmp first (existing pattern).
- For `split_clip`, the new right_clip_id is replaced with a
  stable placeholder in the golden (UUIDs vary across runs);
  the left_clip_id is stable.
- The `test_golden_io.py` file's `_CASES` list grows from 5
  to 15 entries; the `test_op_output_matches_golden` function
  is parametrized over them, so 10 new collected tests.

**Layer 2 — Per-tool integration tests** (one test file per domain)

The convention is `phase2_project_engine/tests/test_ops_<domain>.py` —
one test file per domain, NOT per source file. The clips-edit
tests live in the same file as the original clips tests.

| Test file | Domain | Tests for | Adds |
|---|---|---|---|
| `test_ops_clips.py` | clips (placement + edit) | `clips.py` + `clips_edit.py` | 5 new test functions |
| `test_ops_effects.py` | effects | `effects.py` | 1 new test function |
| `test_ops_transitions.py` | transitions | `transitions.py` | 1 new test function |
| `test_ops_groups.py` (NEW) | groups | `groups.py` | 3 new test functions |

Each function has multiple assertions for behavior (not just
I/O shape). Examples:

- `test_slip_clip`: timeline position unchanged; source_in/out shift by delta; out-of-bounds delta raises `source_oob` (NotFoundError).
- `test_ripple_delete_clip`: deleted clip gone; following clips on same track have timeline_start_sec reduced by deleted duration; clips on other tracks untouched.
- `test_change_clip_speed`: rate=2.0 halves duration; rate=0.5 doubles it; rate=11.0 raises `rate_out_of_range` (ValidationError).
- `test_split_clip`: returns two clip_ids; left keeps original id; right is new; both span the original range; at_sec=clip_start raises `split_position_invalid`.
- `test_replace_clip_source`: source_id changes; source_in=0; new duration = min(old, new_source_duration); rate resets to 1.0.
- `test_remove_effect`: remaining effect list has the entry at `effect_index` removed; out-of-range index raises `effect_index_out_of_range`.
- `test_remove_transition`: the transition XML element is gone; clip entries that were bounded by it are not modified.
- `test_group_clips`: writes JSON tree to `kdenlive:sequenceproperties.groups`; reads back via `list_groups`; group_name round-trips; leaves resolved by (track, pos) → current clip_id.
- `test_ungroup_clips`: group removed from JSON tree; remaining groups untouched.
- `test_list_groups`: returns [{group_name, clip_ids}] without runtime IDs; AVSplit groups skipped.

**Layer 3 — Real-Kdenlive interop test** (1 new test in `phase7_real_session/tests/test_e2e.py`)

- Loads a pyagent project (with groups written by
  `group_clips`) into a real Kdenlive instance via xvfb;
  asserts no parse errors.
- Triggers a Kdenlive "re-save" pass; reads the resulting
  file and asserts the JSON tree under
  `kdenlive:sequenceproperties.groups` is preserved (type,
  pyagent:name, children, leaf data format).
- Skipped where Kdenlive is not installed (existing
  `skipif_kdenlive_missing` helper). Also skippable with
  `--no-e2e` flag (existing helper).

---

## Test count budget

Each pytest `@pytest.mark.parametrize` case = 1 collected test.
Each test function = 1 collected test. (No separate "+1" for
the existing skip; the current 231 collected tests include
the 1 skipped e2e test.)

| Commit | Layer 1 (golden) | Layer 2 (integration) | Layer 3 (e2e) | Cumulative collected |
|---|---|---|---|---|
| (baseline) | 6 | 32 | 4 | 231 |
| 1. clips-edit | +5 | +5 | 0 | 241 |
| 2. effects | +1 | +1 | 0 | 243 |
| 3. transitions | +1 | +1 | 0 | 245 |
| 4. groups | +3 | +3 | +1 (skipif Kdenlive) | 252 |
| **Post-2a** | 16 | 42 | 5 | **252 collected** |

In CI without Kdenlive, the 1 e2e test in commit 4 is skipped
(so 251 collected, 251 skipped-free pass, 1 skip).

---

## Commit plan

Branch: `add-editor-tools-2a` (off `main`).
4 commits, one per domain, ordered clips-edit → effects →
transitions → groups.

**Commit 1 — `clips-edit` (5 tools)**

Files added:
- `phase2_project_engine/ops/clips_edit.py` (5 functions)
- `phase3_pyagent_core/tools/clips_edit.py` (5 ToolDefs)
- `phase3_pyagent_core/tests/fixtures/golden_io.json` (+5 entries)

Files modified:
- `phase2_project_engine/ops/__init__.py` (+5 exports)
- `phase3_pyagent_core/tools/__init__.py` (+clips_edit module + canonical-order entry)
- `phase3_pyagent_core/runtime.py` (5 OP_TABLE entries, 5 MUTATING_OPS entries)
- `phase2_project_engine/tests/test_ops_clips.py` (5 new test functions)

Cumulative collected tests after commit: 241.

**Commit 2 — `effects` (1 tool)**

Files modified:
- `phase2_project_engine/ops/effects.py` (+`remove_effect`)
- `phase3_pyagent_core/tools/effects.py` (+`REMOVE_EFFECT` ToolDef)
- `phase3_pyagent_core/runtime.py` (+1 OP_TABLE, +1 MUTATING_OPS)
- `phase2_project_engine/tests/test_ops_effects.py` (+1 test function)
- `phase3_pyagent_core/tests/fixtures/golden_io.json` (+1 entry)

Cumulative: 243.

**Commit 3 — `transitions` (1 tool)**

Files modified:
- `phase2_project_engine/ops/transitions.py` (+`remove_transition`)
- `phase3_pyagent_core/tools/transitions.py` (+`REMOVE_TRANSITION` ToolDef)
- `phase3_pyagent_core/runtime.py` (+1 OP_TABLE, +1 MUTATING_OPS)
- `phase2_project_engine/tests/test_ops_transitions.py` (+1 test function)
- `phase3_pyagent_core/tests/fixtures/golden_io.json` (+1 entry)

Cumulative: 245.

**Commit 4 — `groups` (3 tools + real-Kdenlive interop)**

Files added:
- `phase2_project_engine/ops/groups.py` (3 functions)
- `phase3_pyagent_core/tools/groups.py` (3 ToolDefs)
- `phase2_project_engine/tests/test_ops_groups.py` (3 test functions)

Files modified:
- `phase2_project_engine/ops/__init__.py` (+3 exports)
- `phase3_pyagent_core/tools/__init__.py` (+groups module)
- `phase3_pyagent_core/runtime.py` (+3 OP_TABLE, +2 MUTATING_OPS;
  `list_groups` is read-only)
- `phase3_pyagent_core/tests/fixtures/golden_io.json` (+3 entries)
- `phase7_real_session/tests/test_e2e.py` (+1 interop test, gated)

Cumulative: 252 (251 in CI without Kdenlive; 1 skipped).

---

## Migration / rollback

- All 4 commits land on `add-editor-tools-2a` and merge into
  `main`. If a commit introduces a regression, the standard
  revert path applies: `git revert <sha>` per commit. Because
  each commit is independently testable, partial-rollback is
  possible (e.g., ship commits 1-3 and defer 4).
- The 19 existing tools' I/O is unchanged. The agent
  harness does not need to relearn anything.
- The 3 new golden-file fixtures for commits 2-3 do not
  conflict with existing entries; the existing 5 entries
  remain byte-identical.
- If the Kdenlive format diverges from this spec in a future
  Kdenlive version, commit 4 is the only commit that needs
  rework (the interop test will fail and surface the drift).

---

## Definition of done

- [ ] Branch `add-editor-tools-2a` exists with 4 commits.
- [ ] All 10 new tools appear in `runtime.list_tools()` output
      (verifiable: `python3 -c "from phase3_pyagent_core.runtime
      import list_tools; print(len(list_tools()))"` returns 29).
- [ ] `extension.ts` requires no changes (auto-discovery via
      `list_tools()` confirmed at extension.ts:62-65).
- [ ] All 10 new tools have a parametrized golden-file case in
      `phase3_pyagent_core/tests/fixtures/golden_io.json`.
- [ ] All 10 new tools have a behavior test in
      `phase2_project_engine/tests/test_ops_<domain>.py`.
- [ ] Groups tool uses real Kdenlive format: writes
      `kdenlive:sequenceproperties.groups` as a JSON array of
      `{type, pyagent:name, children}` objects, with leaves
      using `data: "<track>:<pos>:<sublayer>"`.
- [ ] All 10 new tools' return shapes match the contracts in
      this spec.
- [ ] All 10 new tools' error codes match the taxonomy in
      this spec.
- [ ] The Layer 3 interop test passes when run with a real
      Kdenlive install.
- [ ] Every new prod file is <300 lines; every new test file
      is <400 lines.
- [ ] No existing tool's JSON I/O has changed (the 19
      existing tools' golden fixtures pass unchanged).
- [ ] `BUGS_FIXED.md` is updated with any bugs found during 2a.
- [ ] The plan doc
      (`docs/superpowers/plans/2026-07-19-add-editor-tools-2a.md`)
      exists.
- [ ] All 252 collected tests pass (251 pass + 1 skip in CI
      without Kdenlive; 252 pass in dev with Kdenlive).

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `kdenlive:sequenceproperties.groups` key or JSON shape differs in the Kdenlive version we test against | Low | High | The Layer 3 interop test exercises real Kdenlive; if the key/shape differs, the test fails with a clear error and the spec is updated before commit 4 lands. Verified the key/shape against Kdenlive master source. |
| `pyagent:name` side-channel field collides with a future Kdenlive namespace | Very low | Low | Kdenlive's `fromJson()` ignores unknown fields, so a future addition of `pyagent:*` by Kdenlive is unlikely. If it happens, we rename to `pyagent_group_name` (1-line change in 3 group ops + 3 golden fixtures). |
| The clips.py + clips_edit.py split makes code harder to find | Low | Low | Naming follows the existing per-domain pattern: per-domain test file, per-domain source file. The 5 new clip-edit ops have a clear home. |
| Auto-save after a group op overwrites changes made by another concurrent process | Low | Medium | Same auto-save pattern as the existing 9 mutating tools; no new concurrency risk. The user is expected to use one process at a time (existing constraint). |
| `split_clip` runtime id for the right half is unstable across calls | Low | Medium | The LLM can re-list to get fresh runtime ids via `get_timeline_summary()`. This is the same pattern as the existing 19 tools' runtime ids. |
| Real Kdenlive test is flaky in CI | Low | Low | The e2e test is gated by `skipif_kdenlive_missing` and can also be skipped with a `--no-e2e` flag (existing helper). |
| `change_clip_speed` with `rate < 0` (reverse playback) | Medium | Medium | Out of scope for 2a. The Kdenlive producer uses `warp_speed` and needs a timewarp filter for reverse. The 0.1..10.0 constraint is documented in the tool description; `ValidationError` if violated. |
| Older Kdenlive versions (< 23.04) use `kdenlive:docproperties.groups` (singular) | Very low | Low | 23.04 is 2.5+ years old at this point (current date 2026-07-19). The user is on a recent Kdenlive. The Layer 3 test will fail if the format doesn't match. |
| Position-based leaf references become stale when clips move | Medium | Medium | This is Kdenlive's own design constraint, not a pyagent one. Kdenlive's `fromJsonWithOffset` re-resolves positions on load. The LLM is expected to re-list groups after moving clips; this is documented in the `group_clips` description. |

---

## Open questions

None. All design decisions captured.
