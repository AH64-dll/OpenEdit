# PyAgent for Kdenlive — Whole-pipeline cleanup

**Sub-project 1 of 3.** Future sub-projects: (2) add 15+ missing editor
tools, (3) end-to-end verification with real Kdenlive + real AI.

## Problem

The pyagent-kdenlive-guide codebase is ~10,700 lines of Python + 616
lines of TypeScript across 7 phases. After ~3 weeks of feature work
without cleanup, it has accumulated:

- **Dead code** (unused classes, modules, adapters that always return
  False for `available()`).
- **Duplication** (3 different `_resolve_*` helpers for finding a
  producer; `_sec_to_tc`/`_tc_to_sec` defined in two modules;
  `ValidationError` defined in two modules; 3 overlapping track-query
  functions).
- **Bugs** in the file backend that cause AI edits to misroute or fail
  (audio fallback to `playlists[0]`; transition timing only uses
  `a.out`; tractor duration ignores `blank` children; effect
  param defaults ignored).
- **One file is 942 lines** (`kdenlive_file_backend.py`); another is
  716 lines (`app.py`); the extension.ts is 616 lines with 19 tool
  schemas hand-rolled.

The user reports: AI gets stuck, transitions don't work, the AI can't
reach all the editor tools, the backend has many bugs. Adding new
tools on this foundation would propagate the bugs.

## Goals (this sub-project)

- Rewrite the codebase for clarity, with no behavior change for the
  19 existing tools.
- Fix the documented backend bugs.
- Establish a 3-layer Phase 2 structure (types / IO / ops) so
  sub-project 2 (new tools) can land on solid ground.
- Keep all 7 phases; clean each.
- All 180+ existing tests rewritten for the new structure and
  passing.

## Non-goals (this sub-project)

- No new editor tools. (Sub-project 2.)
- No behavior change for the 19 existing tools' JSON I/O. The agent
  harness should not need to relearn anything.
- No new dependencies.
- No migration of the chat UI's HTML/JS/CSS beyond what is forced by
  Python-side signature changes (there are none planned).

## The 3-sub-project plan

| # | Sub-project | Scope | Effort |
|---|---|---|---|
| 1 | **Cleanup (this spec)** | Rewrite all 7 phases for clarity; fix documented bugs; tests pass; behavior unchanged | 3 weeks |
| 2 | New editor tools | Add 15+ missing ops (slip, ripple, speed, undo, grouping, replace, etc.) — also expand effect/transition coverage | 4 weeks |
| 3 | Wire + test | End-to-end verification with real Kdenlive + real AI; performance + UX polish | 2 weeks |

Sub-project 2 will land on the clean foundation this spec produces.

## Architecture (post-cleanup)

```
pyagent-kdenlive-guide/
  phase1_knowledge_base/
    types.py            # CatalogEntry, Parameter dataclasses
    catalog.py          # Catalog (load/save/filter from JSON)
    cookbook.py         # recipe corpus
    build_catalog.py    # rebuild catalog from /usr/share/kdenlive/effects/
    build_cookbook.py   # rebuild cookbook from catalog
    README.md

  phase2_project_engine/       <-- THE CLEANUP'S CENTERPIECE
    types.py            # ProjectInfo, ClipSummary, TrackSummary,
                        #   TransitionSummary, MarkerSummary, EffectSummary
    errors.py           # BackendError, ValidationError, NotFoundError,
                        #   CatalogError, validation_error()
    validators.py       # PURE validation functions, no I/O
    catalog.py          # Catalog dataclass + by_id index
    io.py               # ProjectTree + load_project() + save_project()
                        #   (load, save, docproperties, kdenlive:props)
    tracks.py           # track/clip navigation (get_tracks,
                        #   get_video_playlist, is_audio_track, find_*,
                        #   resolve_producer, _insert_entry_at_position, ...)
    ops/
      __init__.py       # re-exports
      bin.py            # import_media
      clips.py          # insert/append/move/trim/delete
      transitions.py    # add_transition
      effects.py        # apply_effect
      markers.py        # add_marker
      _helpers.py       # shared low-level helpers (timecode, etc)
    backend.py          # EditorBackend (ABC) + KdenliveFileBackend (concrete)
                        #   THIN dispatch only, ~200 lines

  phase3_pyagent_core/
    types.py            # re-export phase2.types
    runtime.py          # run_op() — load backend, dispatch, save, handle errors
    tools/              # per-domain tool registration
      __init__.py
      bin.py            # import_media tool
      clips.py          # insert/append/move/trim/delete tools
      transitions.py
      effects.py
      markers.py
      project.py        # get_project_info, get_timeline_summary
      catalog.py        # list_catalog
      render_qc.py      # the 6 phase6 tools (just parameter schemas)
    extension.ts        # ONE FILE: imports tools/*, registers 19 tool defs.
                        #   Thin: only names + parameter schemas. ~300 lines.
    __main__.py         # CLI: python3 -m phase3_pyagent_core <op> --args-json ...
    system_prompt.md    # unchanged

  phase4_chat_ui/
    types.py            # ChatMessage, PiEvent, Session, PlanCard
    app.py              # FastAPI app, ~300 lines
    session.py          # Session lifecycle + persistence
    adapters/
      __init__.py       # AgentAdapter protocol, build_adapter()
      piagent.py        # PiAgentAdapter
      opencode.py       # OpenCodeAdapter
      _registry.py      # _APP_REGISTRY dict
    pi_client.py        # subprocess runner, JSON event parser
    state.py            # project state snapshot (read-only)
    watcher.py          # file watcher
    static/             # HTML/JS/CSS
    tests/

  phase5_dbus_sync/
    types.py            # LiveResult dataclass
    live_sync.py        # apply(tool, args, project) — D-Bus first, file fallback
                        #   + triggers cleanRestart on running kdenlive
    dbus_client.py      # low-level D-Bus calls
    notifier.py         # (may merge into live_sync.py if it shrinks)
    __main__.py         # CLI

  phase6_render_qc/
    render.py           # melt-based render
    thumbnails.py       # ffmpeg-based thumbnails
    black_frames.py
    audio.py            # silence + levels
    parsers.py          # shared parsing
    qc_loop.py          # high-level driver; may shrink or merge

  phase7_real_session/
    e2e.py              # ONE file: drives real pi + real kdenlive in xvfb
    xvfb.py             # xvfb helper
    skipif.py           # skipif_helpers
    ws_client.py        # websocket client
    tests/
      test_e2e.py       # ONE persistent e2e test
```

### Module-size budget

- Every production file: <300 lines.
- Every test file: <400 lines.
- If a file needs to grow, split it first.

## Phase 2 — the 3-layer structure (foundation)

### Layer 1: types (frozen dataclasses)

```python
# phase2_project_engine/types.py
@dataclass(frozen=True)
class ProjectInfo:
    name: str
    fps: float
    width: int
    height: int
    colorspace: str
    track_count: int
    duration_sec: float
    path: str | None

@dataclass(frozen=True)
class ClipSummary:
    clip_id: str
    track_index: int
    start_sec: float
    end_sec: float
    source_id: str        # bin producer's kdenlive:id
    source_path: str
    source_name: str
    source_in_sec: float
    source_out_sec: float
    effects: tuple[str, ...]

@dataclass(frozen=True)
class TrackSummary:
    index: int
    kind: str             # "video" | "audio"
    name: str
    clip_count: int

@dataclass(frozen=True)
class TransitionSummary:
    transition_id: str
    track_index: int
    start_sec: float
    end_sec: float
    kind: str

@dataclass(frozen=True)
class MarkerSummary:
    position_sec: float
    label: str
    kind: str             # "marker" | "guide" | "chapter"

# Defined now (used in sub-project 2):
@dataclass(frozen=True)
class EffectSummary:
    effect_id: str
    clip_id: str
    params: dict[str, str]
```

### Layer 2: IO (load/save + ProjectTree wrapper)

```python
# phase2_project_engine/io.py
@dataclass
class ProjectTree:
    root: etree._Element
    path: Path | None
    
    # I/O functions
def load_project(path: str | Path) -> ProjectTree: ...
def save_project(tree: ProjectTree, path: str | Path | None = None) -> None: ...

# ProjectTree methods (structural only — no track logic here):
class ProjectTree:
    def get_profile(self) -> dict: ...
    def get_main_bin(self) -> etree._Element | None: ...
    def get_docproperties(self) -> dict[str, str]: ...
    def ensure_docproperties(self) -> None: ...
    def ensure_root_attrs(self) -> None: ...
    def ensure_kdenlive_properties_on_producer(self, producer, path) -> None: ...
    def get_tractor(self) -> etree._Element | None: ...
```

### Layer 3: ops (per-domain, one file each)

Each op file exports a small set of functions that take a `ProjectTree`
plus their kwargs and return the new state. **No class wrappers** in
the op files; the backend class in `backend.py` dispatches to them.

```python
# phase2_project_engine/ops/clips.py
def insert_clip(tree, *, track_index, position_sec, source_id,
                source_in_sec=0.0, source_out_sec=None,
                video_only=False, audio_only=False) -> str: ...
def append_clip(tree, *, track_index, source_id, ...) -> str: ...
def move_clip(tree, *, clip_id, new_track, new_position_sec) -> None: ...
def trim_clip(tree, *, clip_id, new_in_sec, new_out_sec) -> None: ...
def delete_clip(tree, *, clip_id) -> None: ...
```

(Similar shape for `bin.py`, `transitions.py`, `effects.py`, `markers.py`.)

### Tracks & helpers (between layers 2 and 3)

```python
# phase2_project_engine/tracks.py
def get_tracks(tree) -> list[etree._Element]: ...
def get_track_playlists(tree, tractor) -> list[etree._Element]: ...
def get_video_playlist(tree, tractor) -> etree._Element | None: ...
def is_audio_track(tree, tractor) -> bool: ...
def find_clip_entry(tree, clip_id) -> tuple[etree._Element, int]: ...
def find_all_entries(tree, clip_id) -> list[tuple[etree._Element, int]]: ...
def resolve_producer(tree, source_id) -> etree._Element: ...
def resolve_source_duration(tree, source_id) -> float: ...
def next_kdenlive_id(tree) -> str: ...
def bump_tractor_duration(tree) -> None: ...

# phase2_project_engine/ops/_helpers.py
def playlist_duration(pl) -> float: ...
def entry_start_sec(pl, entry) -> float: ...
def shift_entry_on_timeline(pl, entry, shift) -> None: ...
def insert_entry_at_position(pl, entry, position_sec) -> None: ...
def sec_to_tc(sec) -> str: ...
def tc_to_sec(s) -> float: ...
def probe_duration_sec(path) -> float: ...
```

### Backend class (thin dispatch)

```python
# phase2_project_engine/backend.py
class EditorBackend(ABC):
    @abstractmethod
    def get_project_info(self) -> ProjectInfo: ...
    # ... (all 19 abstract methods, unchanged signatures)

class KdenliveFileBackend(EditorBackend):
    def __init__(self, project_path, catalog):
        self.tree = load_project(project_path or None)
        self.tree.ensure_docproperties()
        self.catalog = catalog
    
    def import_media(self, paths): 
        return ops_bin.import_media(self.tree, paths)
    
    def insert_clip(self, **kwargs): 
        return ops_clips.insert_clip(self.tree, **kwargs)
    # ...
```

## Backend bug fixes (no behavior change for tool I/O, just correctness)

These are correctness fixes — the 19 tools' JSON I/O stays identical
(so the LLM doesn't need to relearn anything), but the underlying
implementation is now correct.

| # | Bug | Fix |
|---|---|---|
| 1 | `insert_clip` audio fallback used `playlists[0]` — would silently misroute audio into a video playlist | Use `tracks.get_video_playlist` which detects audio-tractor-with-video-content |
| 2 | `add_transition` timing only used `a.out` — could clip the B side | Compute from both entries' `in`/`out`; raise a clear error if not adjacent |
| 3 | `add_transition` cross-track restriction is a TODO comment, not enforced | Already raises `ValidationError`; make the message clearer |
| 4 | `_bump_tractor_duration` ignores `blank` children | Sum both `entry` and `blank` durations |
| 5 | `apply_effect` ignores catalog defaults when `params` is empty | Read defaults from the catalog entry and apply them |
| 6 | Three different `_resolve_*` helpers for finding a producer | Consolidate to one `resolve_producer(tree, source_id)` |
| 7 | `get_video_tracks` (heuristic) conflicts with `get_tracks` (structural) | Delete `get_video_tracks`; structural only |
| 8 | `ValidationError` defined in both `editor_backend.py` and `validation.py` | Single source in `errors.py`; re-export from `editor_backend.py` for backward compat (one release) |
| 9 | `apply_effect` writes `kdenlive_id` (snake) instead of `kdenlive:id` (colon) | Use the canonical form |
| 10 | `add_transition` writes transition to `get_tractor()` (the main one) — but the project may have multiple tractors | Insert the transition into the tractor that owns the playlist where the two clips live |

## Error handling

Three error classes, all inheriting `BackendError`. Every error message
carries a `fix:` line for the LLM.

- `ValidationError(BackendError)` — bad input (out of range, wrong
  type, clip not found). LLM self-corrects.
- `NotFoundError(BackendError)` — referenced clip/track/effect not in
  the project. LLM retries with corrected ids.
- `CatalogError(BackendError)` — effect/transition not in the catalog.
  LLM calls `list_catalog` to look up the right id.

Internal exceptions (`KeyError`, `etree.XMLSyntaxError`, etc.) are
caught at the `runtime.py` boundary in phase 3 and turned into a
`fatal: True` response — they never reach the LLM as a stack trace.

## Testing strategy

### Per-module tests

One test file per production module. The shared fixture is a fresh
empty `ProjectTree` per test (`tests/conftest.py`).

```
phase2_project_engine/tests/
  conftest.py            # fresh empty tree + sample clip fixtures
  test_types.py
  test_errors.py
  test_validators.py
  test_catalog.py
  test_io.py
  test_tracks.py
  test_ops_bin.py
  test_ops_clips.py
  test_ops_transitions.py
  test_ops_effects.py
  test_ops_markers.py
  test_backend.py        # thin dispatch tests
  test_roundtrip.py      # load -> save -> load equivalence on real kdenlive files
```

Coverage target: ≥90% on phase2.

### Golden-file tests

The 19 tools' JSON I/O is locked down by golden-file tests in
`phase3_pyagent_core/tests/test_golden_io.py`:
- For each tool, call it with a known input and assert the JSON output
  byte-for-byte matches a checked-in fixture.
- If a tool's I/O is intentionally changing, the test fails loudly and
  the fixture must be updated as part of the change.

### Phase 7 e2e test

One persistent test (`phase7_real_session/tests/test_e2e.py`) that
drives a real `pi` against a real Kdenlive in xvfb. Asserts:
1. AI picks `pyagent_add_transition` from the 19-tool catalog with
   valid kind + duration.
2. File-mode edit lands on disk.
3. The same edit is visible in the running Kdenlive after a clean
   restart.

The test is unchanged in intent, only the file layout is reduced.

### Test count budget

| Phase | Current | Post-cleanup | Reason |
|---|---|---|---|
| 1 | 0 (data only) | 0 | unchanged |
| 2 | ~50 (test_phase2.py) | ~80 | per-module + roundtrip |
| 3 | ~30 | ~30 | golden + integration |
| 4 | ~22 | ~22 | unchanged in count |
| 5 | ~24 | ~24 | unchanged in count |
| 6 | ~24 | ~24 | unchanged in count |
| 7 | 1 | 1 | unchanged |
| **Total** | **~150** | **~180+** | all pass |

## Migration plan

Atomic swaps, one phase per commit, no half-states:

1. **Build new phase2 in a subdirectory** (`phase2_project_engine/_v2/`)
   without touching existing files.
2. Write tests for the new code; verify all pass.
3. **Atomic swap**: rename `_v2/*` to `phase2_project_engine/*` (one
   git commit). Update `phase2_project_engine/__init__.py` to re-export
   the same public names (so phase3/extension.ts doesn't need to
   change).
4. Update `phase3_pyagent_core/runtime.py` and `__main__.py` to use
   the new `ops/*` layout (one commit).
5. Update `phase3_pyagent_core/extension.ts` to import tool defs from
   the new `tools/*` layout (one commit).
6. Update `phase4_chat_ui` to use the new types (one commit).
7. Update `phase5_dbus_sync` to use the new types (one commit).
8. Update `phase6_render_qc` to use the new types (one commit).
9. Update `phase7_real_session` to use the new types (one commit).
10. Drop the old `phase7_real_session/dbus_probe.py`,
    `phase7_real_session/chat_ui.py`, `phase7_real_session/kdenlive.py`
    (their functionality moves to phase4 / phase5).

After each commit: run the relevant test suite. If anything breaks,
fix forward — never revert.

## Definition of done

- [ ] Every production file <300 lines; every test file <400 lines.
- [ ] No duplicate code between modules (verified: `grep -r '_sec_to_tc\|ValidationError\|_resolve_producer'` shows one definition each).
- [ ] No unused classes / adapters / modules (verified: `grep -r 'available.*False'` shows no production usage).
- [ ] All 180+ tests pass.
- [ ] All 19 tools have the same JSON I/O as before (verified by
      golden-file tests).
- [ ] Phase 7 e2e test still passes against real Kdenlive.
- [ ] One single commit per phase (10 total).
- [ ] `docs/superpowers/specs/2026-07-19-cleanup-design.md` (this file)
      + `docs/superpowers/plans/2026-07-19-cleanup.md` exist.
- [ ] All 10 documented backend bugs are fixed and have a regression
      test.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Behavior drift in one of the 19 tools breaks the chat UI | Medium | High | Golden-file tests; per-commit verification |
| Kdenlive opens but shows "Unreferenced" producers after the rewrite | Low | Medium | Preserve the `kdenlive:clip_type` and `kdenlive:duration` property order; roundtrip test on `manual_baseline.kdenlive` |
| LLM re-learns tool schemas because parameter shapes changed | Low | High | Lock with golden-file tests; freeze op names |
| Phase 7 e2e test becomes flaky in CI | Low | Low | Keep the skipif_helpers; add a `--no-e2e` flag |
| Migration commits can't be reverted cleanly | Low | Medium | Atomic commits, each one green; tag after each phase |

## Out of scope

- New editor tools (sub-project 2).
- Performance optimization beyond correctness.
- New chat UI features (multi-session, image uploads, etc.).
- Documentation beyond the spec + plan + updated READMEs.
- A graphical desktop integration (KDDockWidgets panel).
- Sync with Kdenlive via D-Bus fork (still using upstream).

## Open questions

None at this time. All major design decisions captured above.
