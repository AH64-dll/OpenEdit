# Design: Op Validation at the Vault Door

**Date:** 2026-07-23
**Status:** Approved (design), pending implementation plan
**Goal:** Make broken edits impossible to persist, regardless of how they are produced, while maximizing agent freedom.

## Background & Motivation

Today the only op-validation lives inside `run_free_form` (`agent/sandbox_bridge.py:_validate_ops_incrementally`, line 644). It is bypassed whenever ops are written through any other path — the unsandboxed `bash` tool, raw SQL, or the `DevBackend`. The 366-overlapping-clip corruption in project `o-2` happened *because* of that bypass.

Verification during design surfaced a second gap: the current validation checks **op shape** (parse against `OperationUnion`) and **reference integrity** (does `clip_id`/`asset_hash` exist), but it does **not** detect **overlapping clips**. `apply_operation` (`ir/apply.py:91`) has no overlap handling, so overlapping timelines are silently accepted. Fixing this is the core of "make the validation work right."

User decisions (2026-07-23):
- **Keep** op validation at the vault door and make it actually catch overlaps.
- **Loosen** the fs allow-list: drop the "must be under `OPEN_EDIT_PROJECTS_ROOT`" restriction; the agent may read/write anywhere.
- **Drop** audit-stamping enrichment (no new provenance fields).
- **Keep a minimal, non-blocking append lock** (decision by implementer) to protect op ordering.
- **No** internet blocking, **no** CPU/memory limits — freedom over safety hardening.

## Architecture

The single chokepoint for every persisted op is `EditGraphStore.append()` (`storage/edit_graph.py:114`). We move validation there so it is backend-agnostic.

```
producer (sandbox / dev / bash / SQL / UI)
        |
        v
EditGraphStore.append(op)
        |-- shape validation      (TypeAdapter(OperationUnion))   -- reject malformed
        |-- reference validation  (clip_id / asset / transition)  -- reject dangling
        |-- minimal lock (short)  -- protect sequence_num order
        v
   INSERT into edits / edit_status_events
```

A second, read-side check (`validate_timeline`) runs when the timeline is *derived*, so any pre-existing corruption in an already-stored DB is detected where it matters (render, and an explicit validation command) without breaking loading of legacy projects.

## Components

### 1. New module: `open_edit/ir/validation.py`
Extract and formalize the existing checks:
- `validate_op_shape(raw) -> OperationUnion` — parse/validate one op dict against `OperationUnion` (moved from the inline `TypeAdapter(...).validate_python` in `_validate_ops_incrementally`).
- `validate_op_references(op, state) -> None` — moved/cleaned from `_validate_references` (`sandbox_bridge.py:707`). `state` is the set of currently-known `clip_id`s, `asset_hash`es, `effect_id`s, `edit_id`s, `group_label`s, plus `track_ids`. Raises `ReferenceError` on a missing target. (RawMltXmlOp / FreeFormCodeOp are exempt.)
- `validate_timeline(timeline) -> None` — **new**. Raises on:
  - overlapping clips on the same track,
  - orphaned transitions (`AddTransitionOp` whose `clip_a_id`/`clip_b_id` is not present in the final timeline),
  - negative or zero-duration clips/effects,
  - any op that `apply_operation` would reject.

`validate_timeline` reuses the same reference logic against the *derived* timeline so both write- and read-side checks stay consistent.

### 2. `EditGraphStore.append()` (`storage/edit_graph.py:114`)
- Before insert: call `validate_op_shape` then `validate_op_references(op, current_state)`.
- `current_state` is derived from the ops already in the DB (`load_all()` → id sets). Order-dependent, matching current behavior (an op must reference ids created by earlier ops). For project sizes in use (hundreds of ops) this is acceptable; a future optimization can cache id sets.
- On failure raise `OpValidationError` (new exception in `ir/validation.py`, subclass of `ValueError`). Callers already catch `ValueError` (`run_free_form` returns `invalid_argument`); the `bash`/SQL path simply fails to persist — which is the desired rejection.
- Wrap the two `INSERT`s in a short-lived `threading.Lock` (process-local) so concurrent callers cannot interleave `sequence_num` assignment. Lock is released immediately after the transaction; it never blocks the agent for longer than one insert.

### 3. `derive_timeline` (`ir/apply.py:91`)
- After building the `Timeline`, call `validate_timeline(timeline)` **only when `strict=True`** (new keyword, default `False`). This keeps existing/legacy projects (which may already contain overlaps, e.g. `o-2`) loadable, while the render path and the new validation command opt into strict checking.

### 4. Fs allow-list loosening (`agent/sandbox_bridge.py:_validate_workdir`, line 196)
- Remove the "resolved path must be under an allowed root" check (lines 210–216).
- Keep: must be an existing directory **and** contain `edit_graph.db` (functional — the code cannot operate without the DB). This is not a freedom restriction; it is "point me at a project."
- `_get_allowed_roots` (line 174) is left intact but no longer gates anything; `OPEN_EDIT_PROJECTS_ROOT` remains usable as a hint, never required.

### 5. Audit stamping — no change
Existing `originating_note_id` field stays as-is (zero cost, already present). No new fields, no enrichment.

### 6. Explicitly NOT done
- No network denylist, no rlimits, no CPU/mem caps (freedom).
- `bwrap`/Rust sandbox code is left in place (unused when `OPEN_EDIT_SANDBOX_BACKEND=dev`); not deleted.

## Data Flow

1. Agent/script produces an op and calls `store.append(op)`.
2. `append` validates shape + references against current DB state; if invalid → raises, op is **not** written.
3. Valid op is inserted with a guaranteed `sequence_num` under the minimal lock.
4. When the timeline is derived for render/UI, `derive_timeline(strict=True)` runs `validate_timeline` and raises on overlaps/orphans — catching any corruption that predates this change.

## Error Handling

- `OpValidationError` (subclass of `ValueError`): raised by `append` on shape/reference failure. `run_free_form` already maps `ValueError` → `FreeFormResult.fail("invalid_argument", ...)`. The agent `edit_project` / `bash` paths surface a clear message instead of persisting corruption.
- `TimelineValidationError` (subclass of `ValueError`): raised by `validate_timeline` under `strict=True`. Render path reports it as a failed render with the specific reason (e.g. "overlap on track V1 at 12.3s"). Non-strict loads never raise.
- Sanitized error strings only (existing `_sanitize_for_detail` behavior preserved) — no path/token leakage to the LLM.

## Testing (TDD)

Unit (`tests/test_ir_validation.py`):
- `validate_op_shape`: malformed dict / unknown op kind → raises.
- `validate_op_references`: op referencing a non-existent `clip_id` / `asset_hash` / transition target → raises; valid op → passes.
- `validate_timeline`: two overlapping clips on same track → raises; orphan `AddTransitionOp` → raises; negative duration → raises; clean timeline → passes.

Integration (`tests/test_edit_graph_append_validation.py`):
- Appending a dangling-reference op via `EditGraphStore.append` raises `OpValidationError` and writes nothing.
- Building a timeline with an overlap and calling `derive_timeline(strict=True)` raises `TimelineValidationError`; `strict=False` (default) still loads.
- Regression: a 366-style overlap scenario is now detected (proves the original gap is closed).

Existing suite (`test_sandbox_bridge.py`, `test_free_form_e2e.py`, `test_sandbox_backends.py`) must stay green.

## Scope Boundaries (YAGNI)

Out of scope: new effect types, raw MLT escape hatches, network/resource hardening, audit UI, write-ahead op journal. This change only relocates and strengthens validation and loosens the workdir restriction.
