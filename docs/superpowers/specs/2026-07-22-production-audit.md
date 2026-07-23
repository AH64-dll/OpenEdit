# Production Readiness Audit — mlt-pipeline / Open Edit

**Date**: 2026-07-22
**Scope**: Go Pipeline (deterministic video pipeline) + Open Edit (AI-native video editor)
**Excluded**: PyAgent (Kdenlive editor prototype — outside scope)
**Method**: 5 independent deep-dive audits (server layer, IR/storage/render/QC, Go pipeline, frontend, agent tools/tests)

---

## Executive Summary

This codebase contains two distinct subsystems at very different maturity levels.

**Go Pipeline** (`cmd/`, `internal/`) is production-grade: 1.5K LOC, zero external dependencies, deterministic, well-tested. Two critical bugs (orphaned subprocesses, XML injection) need fixing before it's safe in unattended CI.

**Open Edit** (`open_edit/`) is an experimental prototype with strong engineering in places (sandbox bridge, search_assets tool, WebSocket reconnection) but fundamental gaps in testing, data integrity, and production hardening. Key findings:

| Category | Critical | High | Medium/Low |
|----------|----------|------|------------|
| **Server Layer** | 2 | 6 | 12+ |
| **IR/Storage/Render/QC** | 5 | 7 | 15+ |
| **Go Pipeline** | 2 | 2 | 6+ |
| **Frontend** | 1 | 6 | 10+ |
| **Agent Tools & Tests** | 1 | 1 | 8+ |

**Total: 11 critical, 22 high, 51+ medium/low issues identified.**

---

## Top 15 Issues (Ranked by Severity + Impact)

| Rank | Issue | Subsystem | Severity | Summary |
|------|-------|-----------|----------|---------|
| 1 | **Zero Python test coverage** | Open Edit (all) | **Critical** | `pyproject.toml:testpaths = ["tests"]` — directory doesn't exist. Entire agent tools, skills, sandbox bridge, agent loop have no tests. |
| 2 | **API keys stored in plaintext** | Server | **Critical** | `keys_store.py` writes to `~/.open_edit/keys.json` with no encryption. Any filesystem-level access leaks all provider API keys. |
| 3 | **`except*` syntax requires Python 3.11** | Server | **Critical** | `html_overlay.py:572` uses PEP 654 `except*`. Crashes with `SyntaxError` on Python 3.10 (Ubuntu 22.04 LTS). |
| 4 | **`apply_operation` mutates input Timeline in-place** | IR | **Critical** | Docstring promises pure function but every `_apply_*` mutates the input. Direct callers get silent data corruption. |
| 5 | **`SplitClipOp` shares effects list** | IR | **Critical** | Both child clips reference the same list object. Modifying one clip's effects corrupts the other. |
| 6 | **MLT emitter ignores `position_sec`** | Render | **Critical** | All clips placed sequentially in MLT, ignoring timeline positions. Renders will not match the edit graph. |
| 7 | **`JobLock.try_acquire` TOCTOU race** | Storage | **Critical** | SELECT then INSERT without atomicity allows concurrent jobs. |
| 8 | **`rollup` purges ALL taste events but only aggregates transitions** | Style | **Critical** | Non-transition taste events (fades, pacing, audio, color) are permanently deleted on every rollup. |
| 9 | **Orphaned melt subprocesses** | Go Pipeline | **Critical** | `cmd/render/main.go` has no `Setpgid` or signal handler. SIGINT/SIGTERM leaves `melt` running. |
| 10 | **XML injection in MLT generation** | Go Pipeline | **Critical** | File paths with `&`, `<`, `>`, `"` produce malformed XML. `mlt/generate.go:82`. |
| 11 | **Light theme CSS entirely missing** | Frontend | **Critical** | Theme toggle sets `data-theme="light"` but zero CSS rules match it. The toggle is a no-op. |
| 12 | **No WebSocket keepalive/heartbeat** | Frontend | **High** | Idle connections die silently. Laptop sleep / proxy timeout disconnects with no detection until next send. |
| 13 | **Fire-and-forget render tasks** | Server | **High** | `app.py:333` creates detached `asyncio.create_task` with no cancellation propagation. User disconnect doesn't stop rendering. |
| 14 | **Sync subprocess blocks event loop during project creation** | Server | **High** | `projects.py:560` uses `subprocess.run` (sync) inside async lock. `open_edit init` can block all API requests for up to 300s. |
| 15 | **Non-atomic write + TOCTOU race on API key file** | Server | **High** | `Path.write_text()` then `os.chmod` — crash mid-write corrupts keys.json; race window exposes keys with default permissions. |

---

## 1. Architecture Review

### Strengths
- **Clean separation of deterministic and non-deterministic work**: Go pipeline is all deterministic; the AI's only job is writing `edl.json`. This is the right architectural split.
- **IR/Storage/Serve/Render separation** in Open Edit follows a reasonable layered architecture.
- **WebSocket event protocol** is well-defined with typed events and a state-machine widget pattern on the frontend.
- **Sandbox bridge** is thoroughly engineered with resource limits, PATH allow-listing, and referential integrity validation.
- **Zero external Go dependencies** — exemplary supply-chain hygiene.

### Weaknesses
- **`app.js` (1,325 lines) is a god module** — combines bootstrap, timeline, edit graph, LLM config, settings, command palette, and zoom controls. Needs decomposition into `timeline.js`, `edit-graph.js`, `settings.js`, `commands.js`.
- **`agent.py` (1,342 lines) does too much** — system prompt building, tool execution, cost tracking, visual verification, CLI-owned turns, circuit breaker, conversation persistence. At minimum, cost tracking should be extracted.
- **`emitter.py` has silent omissions** — `position_sec`, track-level effects, HTML overlays, and audio track kind mapping are all missing. The emitter doesn't accurately reflect the IR state.
- **No migration strategy for SQLite schemas** — `CREATE TABLE IF NOT EXISTS` with comments saying "additive-only". Schema changes require manual migration.

---

## 2. Code Quality Review

### Positive Patterns
- All 13 agent tools have consistent `(args, project_path) -> dict` signatures
- Pydantic discriminated union for IR operations is well-implemented
- Frontend uses ES modules, centralized API client, and state normalizers
- Cost sidecar persistence is documented as "lazy" with appropriate caveats
- `go.mod` with zero requires — commendable

### Problematic Patterns
- **Duplicate cost persistence** — identical ~15-line blocks at 3 locations in `agent.py`
- **Sync I/O in async context** — spans 6+ files (projects.py, pi_bridge.py, llm.py, cli_adapter.py)
- **Bare `except Exception`** — spans 6+ files with silent failure swallowing
- **Module-level mutable state** — `_RENDER_JOBS`, `_OPENCODE_CACHE`, conversations dict all grow without bound
- **Fragile string matching** for error classification (llm.py:288-304, agent.py:330-342)
- **Redundant ffprobe subprocess** in Go analyzer (detectScenes re-probes for duration already known)

### Dead / Unused Code
- `_apply_free_form_code` in `apply.py:721-745` — function exists but `FreeFormCodeOp` handler just returns `timeline` unchanged
- `_origLoadProjectState` reference at `app.js:1317` — remnant of timeline patch approach
- Several documentation files referenced in root directory listing do not exist on disk (`CHANGELOG.md`, `PROJECT_EXPLAINED.md`, `ORIGINAL_REQUEST.md`, `openedit.md`)

---

## 3. Performance Review

### Bottlenecks
| Issue | Location | Impact |
|-------|----------|--------|
| Deep copy of conversation history every agent iteration | `agent.py:597-607` | O(n^2) over long conversations with image data |
| No connection pooling for SQLite | `edit_graph.py:31-43` | Fresh connection per `with _conn():` block |
| `latest_for_project` loads ALL snapshots | `render_snapshots.py:104-105` | Should use `SELECT ... ORDER BY DESC LIMIT 1` |
| `_known_clip_ids` O(n^2) per validation | `validate.py:41-48` | Scans all ops multiple times per validate call |
| `_has_audio_stream` runs subprocess every call | `silence.py:118-130` | No caching — same video probed dozens of times |
| WhisperModel loaded per transcription call | `transcription.py:35` | Model loading takes seconds, done per-file |
| Style profile read from disk every agent turn | `retrieve.py:33` | No in-memory cache |
| Redundant ffprobe in scene detection | Go `analyzer.go:146-171` | Re-probes duration already obtained |

### Recommendations
- Implement LRU cache for conversation history truncation (keep last N turns)
- Add SQLite connection pooling or reuse connections per project
- Cache `_has_audio_stream` results per asset hash with TTL
- Cache WhisperModel at module level
- Fix `latest_for_project` query to use `LIMIT 1`

---

## 4. Security Review

### Critical
| Issue | Location | Details |
|-------|----------|---------|
| **API keys in plaintext JSON** | `keys_store.py:15,49-50` | No encryption. Write with tempfile+os.replace + chmod 600. |
| **Non-atomic key file write** | `keys_store.py:50` | `Path.write_text()` can leave partial file on crash. |
| **TOCTOU on key file permissions** | `keys_store.py:53-54` | Race window between write and chmod exposes keys. |

### High
| Issue | Location | Details |
|-------|----------|---------|
| **XML injection in MLT generation** | Go `mlt/generate.go:82` | File paths with `&<>"` produce malformed XML. |
| **Command injection risk in ffprobe calls** | Multiple files | File paths are passed to subprocess. Currently safe because paths come from validated sources, but no sanitization layer. |
| **`FreeFormCodeOp` executes arbitrary Python** | `ir/types.py:276-282` | Sandboxed via Rust binary but no timeout/mem guard in the operation model itself. |

### Medium
| Issue | Location | Details |
|-------|----------|---------|
| **No Content-Type validation on file upload** | `app.py:257-321` | Any file accepted before ffprobe rejects it. |
| **Path traversal in CLI `_find_existing_project`** | `cli.py` | Walks up directory tree — could escape project root. |
| **`_validate_workdir` not called in all paths** | `sandbox_bridge.py` | Security validation exists but may be bypassed in some code paths. |

---

## 5. Data Integrity Review

### Critical
| Issue | Location | Details |
|-------|----------|---------|
| `apply_operation` mutates input Timeline | `apply.py:86-89` | Pure function contract violation |
| SplitClipOp shares effects between clips | `apply.py:459-467` | Effect mutation on one clip corrupts the other |
| `rollup` purges non-transition taste events | `aggregate.py:64` | All fades/pacing/audio/color events permanently lost |
| Duplicate effect appending (audio gain, normalize) | `apply.py:534-541,712-716` | Multiple calls create redundant effects |

### High
| Issue | Location | Details |
|-------|----------|---------|
| `move_arbitrary` can create duplicate sequence_nums | `edit_graph.py:173-206` | Non-atomic update |
| `append` can race on sequence_num | `edit_graph.py:113-116` | `MAX` query is not locked |
| `mark_processed` stores only one op_id per note | `notes.py:207-214` | Column is JSON array but only one op_id stored |
| `evict_oldest_ready` doesn't delete rendered MP4s | `render_snapshots.py:114-124` | DB rows deleted but disk space never reclaimed |
| No WAL mode in notes.py and render_snapshots.py | `notes.py:117`, `render_snapshots.py:55` | Readers block writers |
| Stale locks never released | `job_lock.py:43-51` | Crash leaves lock held forever |
| Ripple delete uses asset duration not timeline duration | `apply.py:398-408` | Wrong shift amount for speed-changed clips |

---

## 6. UI/UX Review

### Critical
| Issue | Location | Details |
|-------|----------|---------|
| **Light theme broken** | `style.css` | Toggle sets `data-theme="light"` but zero CSS rules match |

### High
| Issue | Location | Details |
|-------|----------|---------|
| **No WebSocket keepalive** | `ws.js` | Idle connections undetected until send fails |
| **Tool card + text ordering race** | `chat.js:62,105-111` | Text after tool cards creates out-of-order bubbles |
| **No `<main>` landmark** | `index.html:110` | Left/right panels are `<aside>` with no `<main>` |
| **Settings modal broken `<div>` nesting** | `index.html:289-296` | Malformed DOM from extra `</div>` |
| **Spurious "connection dropped" toast on provider change** | `app.js:1068` | `_intentionalClose` not set before `connectWS` |

### Medium
| Issue | Location | Details |
|-------|----------|---------|
| Backdrop click only closes command palette | `index.html:225,237,248` | Other modals miss `data-modal-close` |
| No loading state for timeline on project switch | `app.js` | Shows old tracks until new data arrives |
| Timeline clips show only 8 hash characters | `app.js:1270` | Should show source filename or clip index |
| Edit graph truncated at 50 with no "show more" | `app.js:207` | Pagination missing |
| Emoji icons in UI (cross-platform rendering issues) | Multiple | `🌙☀️✂️🏷️🔊🎬` may render as boxes on Linux |
| No `prefers-reduced-motion` media query | `style.css` | Animations can trigger vestibular disorders |

---

## 7. Testing Review

### Go Tests — Acceptable
| File | Lines | Grade | Notes |
|------|-------|-------|-------|
| `test/e2e_test.go` | 168 | A | Full pipeline E2E with proper cleanup, Setpgid, duration assertion |
| `test/bridge_open_edit_test.go` | 103 | A | Bridge contract test |
| `internal/edl/validate_test.go` | 119 | A- | 10+ cases, good coverage |
| `internal/mlt/generate_test.go` | 143 | A- | Golden byte-match test |
| `test/agent_test.go` | 90 | B+ | Build-tagged canary test, runs real opencode |

### Python Tests — CRITICAL FAILURE
| Area | Status | Details |
|------|--------|---------|
| `open_edit/tests/` | **Non-existent** | `pyproject.toml` says `testpaths = ["tests"]` but no `tests/` dir exists |
| `open_edit/test/` | **Data only** | Contains `test/.open_edit/` test data, no test code |
| Agent tools (13) | **Untested** | Zero test coverage |
| Agent skills (5) | **Untested** | Zero test coverage |
| Sandbox bridge (858 lines) | **Untested** | Requires Rust binary |
| Agent loop (1,342 lines) | **Untested** | Zero test coverage |
| IR apply.py (800 lines) | **Untested** | Zero test coverage |
| Server routes | **Untested** | Zero test coverage |
| Frontend | **Untested** | Zero test coverage |

**The entire `open_edit` Python package has zero test coverage.** This is the single biggest risk in the codebase.

---

## 8. Error Handling Review

### Problematic Patterns
| Pattern | Locations | Risk |
|---------|-----------|------|
| `except Exception: pass` | `projects.py:512-513`, `transcription.py:48-50`, `keys_store.py:33-34` | Silent failures, hard-to-debug production issues |
| Catch-all retry with string matching | `llm.py:288-304` | Refactored SDK exceptions silently skip retries |
| `except (asyncio.CancelledError, Exception)` | `agent.py:696` | Overly broad cancellation handling |
| Sync subprocess errors not propagated | `projects.py:560-579` | 300s timeout causes confusing failures |
| KeyError instead of validation error | All 13 agent tools | Malformed LLM tool calls produce unhelpful crashes |

### What's Done Well
- Render orchestration has clear timeout handling
- Sandbox bridge has comprehensive error wrapping with `_SandboxError`
- Visual verification returns clear pass/fail with frame evidence
- Go pipeline has consistent `fmt.Errorf` with context
- WebSocket reconnection has exponential backoff and max retries

---

## 9. Refactoring Opportunities

| Opportunity | Effort | Impact | Priority |
|-------------|--------|--------|----------|
| Split `app.js` into timeline, edit-graph, settings, commands modules | 2-3h | High maintainability | High |
| Extract cost persistence from `agent.py` into shared helper | 1h | Eliminates 3x duplicated code | Medium |
| Add generic `_emit` method to IR API to eliminate 370 lines of boilerplate | 1h | Cuts `api.py` by 90% | Low |
| Share `_resolve_sandbox_bin` between free-form and render paths | 30min | Eliminates duplicate logic | Low |
| Add shared arg validation decorator for agent tools | 2h | Consistent error messages for 13 tools | Medium |
| Extract duplicate render output path resolution | 30min | 3 locations unified | Low |
| Add connection reuse/sharing for SQLite stores | 2h | Reduced connection overhead | Medium |
| Replace string-based timestamps with `datetime` objects | 4h | Correctness, especially in comparisons | Low |

---

## 10. Production Readiness Checklist

### Must-Fix Before Production
- [ ] Add Python test suite (at minimum: smoke tests for agent loop, IR apply, tool execution)
- [ ] Fix `pyproject.toml` testpaths configuration
- [ ] Encrypt API keys at rest (or at minimum: atomic write + restrictive permissions)
- [ ] Add Python 3.10 compatibility or pin Python 3.11+ in packaging
- [ ] Fix `apply_operation` to not mutate input (deep-copy or pure function)
- [ ] Fix `SplitClipOp` to deep-copy effects list
- [ ] Fix `emitter.py` to emit `position_sec`, track-level effects, audio track kind, and HTML overlays
- [ ] Fix `JobLock.try_acquire` race condition (use INSERT with UNIQUE constraint on status)
- [ ] Fix `aggregate.py:rollup` to not purge unaggregated taste events
- [ ] Add signal handler + `Setpgid` to Go render binary
- [ ] Add XML escaping to `mlt/generate.go`
- [ ] Implement light theme CSS
- [ ] Add WebSocket keepalive/heartbeat
- [ ] Add render task cancellation on WebSocket disconnect
- [ ] Fix `agent.py` cost persistence duplication
- [ ] Fix settings modal HTML nesting
- [ ] Add loading state for timeline panel
- [ ] Fix tool card + text ordering in chat
- [ ] Add `_intentionalClose` guard to `saveLLMConfig` callback

### Strongly Recommended
- [ ] Add WAL mode to `notes.py` and `render_snapshots.py`
- [ ] Add stale-lock cleanup in `job_lock.py`
- [ ] Add pagination to edit graph (remove 50-item cap)
- [ ] Add `no-reduced-motion` media query
- [ ] Fix ripple delete speed-change duration calculation
- [ ] Fix duplicate effect appending (audio gain, normalize, add_effect)
- [ ] Add `Content-Type` validation on file uploads
- [ ] Add CI job for Go tests
- [ ] Add rate limiting on render endpoint
- [ ] Replace emoji with SVG icons in UI
- [ ] Implement LLM narrative analyzer (remove stub)
- [ ] Cache WhisperModel at module level
- [ ] Fix `latest_for_project` query

### Nice-to-Have
- [ ] Decompose `app.js` into separate modules
- [ ] Extract cost persistence helper from `agent.py`
- [ ] Add connection pooling for SQLite
- [ ] Add structured logging framework
- [ ] Replace string timestamps with `datetime`
- [ ] Migrate to TypeScript or add JSDoc type annotations
- [ ] Add golden-file tests for MLT emitter output
- [ ] Add developer onboarding docs for Open Edit

---

## 11. Long-Term Improvement Roadmap

### Phase 1: Safety Net (1-2 weeks)
1. Fix `pyproject.toml` testpaths, add smoke test suite (critical path tests)
2. Fix critical data integrity bugs (apply.py mutation, SplitClipOp, JobLock, aggregate.py rollup)
3. Fix critical security issues (API key storage, XML injection)
4. Fix critical UI bug (light theme CSS)
5. Fix Python 3.10 compatibility or pin version

### Phase 2: Production Hardening (2-3 weeks)
1. Add WebSocket keepalive, render cancellation, connection lifecycle
2. Add orphaned process protection (Go render signal handler)
3. Implement emitter completeness (position_sec, track effects, overlays, audio tracks)
4. Add WAL mode to all SQLite stores
5. Add stale-lock cleanup and job timeout enforcement
6. Add rate limiting and input validation on API endpoints
7. Fix all high-severity issues from the audit

### Phase 3: Quality Infrastructure (3-4 weeks)
1. Comprehensive Python test suite (unit + integration)
2. CI job for Go tests
3. Add TypeScript or strict JSDoc to frontend
4. Structured logging framework
5. SQLite migration strategy
6. Performance optimization (caching, query optimization, connection pooling)

### Phase 4: Architectural Evolution (1-2 months)
1. Decompose `app.js` and `agent.py` into focused modules
2. Implement full LLM narrative analyzer
3. Add pagination, loading states, and accessibility to UI
4. Add template system for render profiles
5. Replace emoji with SVG icon system
6. Add developer documentation and onboarding guide

### Phase 5: Future Innovation
1. Multi-project concurrent editing support
2. Collaborative editing (shared IR ops via WebSocket)
3. Render farm / distributed rendering
4. Plugin system for agent tools and render effects
5. Mobile-responsive UI

---

## Appendix: Issue Count by Severity

| Subsystem | Critical | High | Medium | Low/Info |
|-----------|----------|------|--------|----------|
| Server Layer | 2 | 6 | 8 | 12+ |
| IR/Storage/Render/QC | 5 | 7 | 15+ | 6+ |
| Go Pipeline | 2 | 2 | 6+ | 6+ |
| Frontend | 1 | 6 | 10+ | 8+ |
| Agent Tools & Tests | 1 | 1 | 4+ | 6+ |
| **Total** | **11** | **22** | **43+** | **38+** |

**Grand Total: 11 Critical, 22 High, 43+ Medium, 38+ Low** — Approximately 114+ distinct issues across the two subsystems audited.
