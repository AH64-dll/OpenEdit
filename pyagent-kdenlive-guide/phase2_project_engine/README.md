# phase2_project_engine

The editor backend library: a 3-layer Python implementation of the
`.kdenlive` file format (XML + MLT tractor playlists) plus a typed,
validating public API that the rest of the pipeline calls. No
`kdenlive-xml.py`, no `editor_backend.py`, no `validation.py` —
those legacy modules were deleted in the 2026-07-19 cleanup.

## What it is

Phase 2 owns the on-disk representation of a `.kdenlive` project. It
exposes a `KdenliveFileBackend` (concrete `EditorBackend` subclass)
with one method per editor op (`insert_clip`, `add_transition`,
`apply_effect`, ...). Each method loads the project tree, mutates it
via a pure-function `op`, validates the result, and writes the tree
back. The file is the source of truth.

## File map

| File | Purpose | Lines |
|---|---|---|
| `types.py` | Frozen dataclasses (`ProjectInfo`, `ClipSummary`, `TimelineSummary`, ...) | 53 |
| `errors.py` | Single source of `BackendError` / `ValidationError` / `NotFoundError` / `CatalogError` | 50 |
| `catalog.py` | `Catalog` dataclass + `from_json` loader | 30 |
| `io.py` | `ProjectTree` + `load_project` / `save_project` / `ensure_docproperties` | 270 |
| `tracks.py` | Pure track navigation: `get_tracks`, `get_video_playlist`, `resolve_producer`, `bump_tractor_duration`, ... | 276 |
| `validators.py` | Pure validation functions (no I/O) | 222 |
| `ops/_helpers.py` | Shared op helpers (`_xml_roundtrip`, `_next_id`, `_format_tc`) | — |
| `ops/bin.py` | Bin ops: `import_media` | — |
| `ops/clips.py` | Clip ops: `insert_clip`, `append_clip`, `move_clip`, `trim_clip`, `delete_clip` | 209 |
| `ops/transitions.py` | Transition ops: `add_transition` (the BUG 10 fix lives here) | — |
| `ops/effects.py` | Effect ops: `apply_effect` (the BUG 9 fix lives here) | — |
| `ops/markers.py` | Marker ops: `add_marker` | — |
| `backend.py` | `EditorBackend` ABC + thin `KdenliveFileBackend` dispatch (one line per op) | 283 |
| `__init__.py` | Re-exports the public surface (preserves pre-cleanup import paths) | — |

All 13 bugs from the initial survey + atomic-swap fallout are fixed;
see `../BUGS_FIXED.md` for the full list.

## Test

```bash
cd pyagent-kdenlive-guide
PYTHONPATH=. python3 -m pytest phase2_project_engine/tests
# 85 passed
```
