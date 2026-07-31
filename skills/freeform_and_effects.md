# Free-form ops & effect catalog — reference

This is the agent-facing reference for what the structured effect
catalog CAN express, what it CANNOT, and how to escape to free-form
ops when the catalog is not enough. It is a reference doc, not a
skill — there is no separate "free-form skill" tool to call.

## Structured effect catalog

Path: `open_edit/ir/catalog/effects/`

Available catalog effects:

- **Visual:** `brightness`, `contrast`, `saturation`, `luma`
- **Audio:** `eq`, `gain`, `volume`, `panner`, `delay`
- **Transitions:** `dissolve`
- **Enrichment:** `music_bed`, `sfx`

Plus the first-class op `normalize_audio` (in `open_edit/ir/api.py`).

There is **no** `denoise`, **no** `compressor`, **no** `fade` in the
catalog. To use `afftdn` / `acompressor` / `afade`, escape to
free-form.

## Free-form ops (escape hatch)

When the catalog cannot express what the brief asks for, use one of:

- **`RawMltXmlOp`** — embeds raw MLT XML. Use this for an `affine`
  filter (zoom / camera move), or for `afftdn` / `acompressor` /
  `afade` audio filters.
- **`FreeFormCodeOp`** — arbitrary Python that emits IR ops at apply
  time. Use this when the op list itself has to be generated
  dynamically (e.g., one effect per clip in a list).

Both are committed via `edit_project apply_generated_ops` (preferred)
or `run_script` (when you need Python to build the op list).

## When to escape to free-form

| Brief goal | Required op | Notes |
|---|---|---|
| Dynamic zoom / camera move | `RawMltXmlOp` with MLT `affine` filter, keyframed `cx` / `cy` / `scale` | Catalog cannot express zoom. |
| Audio denoise | `RawMltXmlOp` with `afftdn` filter | Catalog has no denoise. |
| Audio compression | `RawMltXmlOp` with `acompressor` filter | Catalog has no compressor. |
| Audio fade in/out | `RawMltXmlOp` with `afade` filter | Catalog has no fade. Use for smooth section transitions. |
| Dynamic per-clip op generation | `FreeFormCodeOp` | When the op list has to be computed from runtime state. |

For everything else (brightness, contrast, eq, gain, volume, music
bed, sfx, dissolve, normalize), prefer the structured catalog — it
gives you validation and undo for free.

## What you CANNOT do

- **Cursor-following zoom.** The `Asset` model has no pointer-track
  or mouse-movement telemetry. Any "follow the cursor" promise is
  fiction. Offer the user a keyframed camera move on a fixed
  trajectory instead — that is expressible as a `RawMltXmlOp`
  `affine` filter with keyframed `cx` / `cy` / `scale`.

## Validation gap — read this before using free-form

`RawMltXmlOp` and `FreeFormCodeOp` skip the reference check that
structured ops go through (see `open_edit/ir/validate.py:452` — the
"no reference check (free-form)" branch). Consequences:

- A malformed MLT filter only fails at **render** time, far from the
  edit loop.
- A `FreeFormCodeOp` Python error only surfaces at apply time, not at
  `apply_generated_ops` time.

Recommended workflow for any free-form op:

1. Build the op via `edit_project apply_generated_ops` (or
   `run_script` for the Python form).
2. Before committing to a real project, run `trigger_render --mode
   proxy` to surface MLT errors early.
3. Only treat the op as committed once the proxy render succeeds.

## Relevant source (read these in the real codebase)

- `open_edit/ir/types.py:287` — `class RawMltXmlOp`
- `open_edit/ir/types.py:293` — `class FreeFormCodeOp`
- `open_edit/agent/sandbox/bridge.py` — `run_free_form` (free-form
  execution facade; backends live in `open_edit/agent/sandbox/backends.py`)
- `open_edit/ir/validate.py:452` — `RawMltXmlOp` / `FreeFormCodeOp`
  bypass the reference check
- `open_edit/ir/catalog/effects/` — the structured effect catalog
- `open_edit/ir/api.py:348` — `normalize_audio` (first-class op)
- `open_edit/ir/api.py:56/121/165/216` — `add_clip` /
  `add_transition` / `add_effect` / `set_keyframe`
