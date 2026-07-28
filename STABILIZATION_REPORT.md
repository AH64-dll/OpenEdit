# Stabilization Report — 2026-07-24

## 1. Architecture Chosen

- **Product surface:** Python FastAPI server/UI (`open_edit/`)
- **Legacy path:** Go/MLT pipeline (`cmd/`, `internal/`, `run.sh`, `edit.sh`) — retained for compilation/rendering through deliberate adapter
- **Deprecated:** Maintaining two independent workflows. New development targets the Python path.

## 2. Fixed Issues

### OE-P0-001 — Provider Registry Drift (partial fix)
- Replaced boolean `owns_agent_loop` with `agent_mode` enum in `providers.py`
- Values: `openedit_loop` (Anthropic/OpenAI), `external_loop` (Pi), `chat_only` (OpenCode, Antigravity, JCode)
- Updated `agent.py` routing to use `agent_mode` instead of `owns_agent_loop`
- Files: `open_edit/open_edit/serve/providers.py`, `open_edit/open_edit/serve/agent.py`

### OE-P0-002 — CLI Agent Ownership (fixed)
- OpenCode, Antigravity, JCode now marked `chat_only` — they cannot mutate the project
- `external_loop` providers (Pi) correctly route to `_run_cli_owned_turn`
- `chat_only` providers fall through to the internal loop (text-only, no tools)
- Files: `open_edit/open_edit/serve/providers.py`, `open_edit/open_edit/serve/agent.py`

### Run-Script Read-Only Block (fixed)
- `sandbox_bridge.py` lines 480-483 and 568-571: changed `ops_missing` error to `FreeFormResult.ok(ops=[], duration_s=0.0)` when 0 ops are produced after a clean run
- This unblocks the agent's read-only introspection scripts (asset inventory, project state)
- Without this fix, any read-only `run_script` call returned `ops_missing`, forcing the agent to abandon the sandbox IR pipeline
- Files: `open_edit/open_edit/agent/sandbox_bridge.py`
- Test: `test_run_python_read_only_succeeds_with_zero_ops` updated (was `test_run_python_missing_project_id`)

### Get-Transcript-Packed Silent Empty (fixed)
- Added `retry: True` flag when alignment is missing (transcription still in progress)
- Previously returned empty string silently — agent couldn't distinguish "no data" from "still processing"
- File: `open_edit/open_edit/agent/tools/pyagent_get_transcript_packed.py`

### Get-Style-Profile Raw KeyError (fixed)
- Added explicit `args.get("op_type")` guard with clear "op_type is required" error
- Previously raised raw `KeyError: 'op_type'` when called without the parameter
- File: `open_edit/open_edit/agent/tools/pyagent_get_style_profile.py`

### Propose-Silence-Cuts Fragile Param (fixed)
- Changed `args["asset_hash"]` to `args.get("asset_hash")` with explicit safety check
- Added `retry: True` flag when alignment is missing (instead of silent error)
- File: `open_edit/open_edit/agent/tools/pyagent_propose_silence_cuts.py`

### Analyze-Narrative Missing Retry (fixed)
- Added `retry: True` flag when alignment is missing (matching the reviewed skills/ version)
- File: `open_edit/open_edit/agent/tools/pyagent_analyze_narrative.py`

## 3. Files and Schemas Changed

| File | Change | API Break? |
|------|--------|-----------|
| `open_edit/open_edit/serve/providers.py` | Added `agent_mode` field; removed `owns_agent_loop` | Yes — `owns_agent_loop` attribute removed |
| `open_edit/open_edit/serve/agent.py` | `provider_spec.owns_agent_loop` → `provider_spec.agent_mode == "external_loop"` | No |
| `open_edit/open_edit/agent/sandbox_bridge.py` | `ops_missing` → `ok(ops=[])` for 0-op scripts | Yes — 0-op scripts now succeed instead of failing |
| `open_edit/open_edit/agent/tools/pyagent_get_style_profile.py` | Added `op_type` guard | No (was KeyError before) |
| `open_edit/open_edit/agent/tools/pyagent_get_transcript_packed.py` | Added `retry: True` on missing alignment | No (returns error dict instead of empty `""`) |
| `open_edit/open_edit/agent/tools/pyagent_propose_silence_cuts.py` | Safe `args.get()`, `retry: True` | No (was KeyError or silent error before) |
| `open_edit/open_edit/agent/tools/pyagent_analyze_narrative.py` | Added `retry: True` on missing alignment | No |

## 4. Provider Capability Matrix

| Capability | Anthropic | OpenAI | Pi | OpenCode | Antigravity | JCode |
|---|---:|---:|---:|---:|---:|---:|
| Listed consistently | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (chat_only) |
| agent_mode | openedit_loop | openedit_loop | external_loop | chat_only | chat_only | chat_only |
| supports_tools | via schema | via schema | TS bridge | None | None | None |
| supports_images | SDK | SDK | Yes | No | No | No |
| Editing capability | Full | Full | Full | Chat only | Chat only | Chat only (hidden) |

## 5. Test Results

- **Python (non-sandbox):** 100% pass (exact count: all non-sandbox tests green)
- **Python (sandbox):** 9 pre-existing failures (sandbox binary not available in dev environment)
- **Go tests:** 3/3 passing (cached)
- **Ruff:** 233 errors in `open_edit/` (all pre-existing, 159 auto-fixable)

## 6. Golden Workflow Status

**Not yet implemented.** The golden workflow requires:
- Phase 3: WebSocket security
- Phase 4: Transactional project creation + multi-file upload
- Phase 5: Edit graph correctness
- Phase 6: Durable render service
- Phase 7: Frontend state sync
- Phase 8: Go/Python integration

These phases remain for future work.

## 7. Remaining Known Limitations

1. **`silence_cutter.py`** — The `skills/` directory has a more sophisticated version (breath-keep, boundary protection) but it has a different API from the installed version. Deploying it requires updating `find_silence_gaps` signature and tests. 
2. **JCode** — Half-registered; present in `providers.py` (chat_only) but missing from `cli_adapter.py`. `get_adapter("jcode")` raises `KeyError`.
3. **Config TOML preservation** — `save_llm_config()` still warns it may drop non-`[llm]` sections (OE-P1-005).
4. **WebSocket auth** — Not implemented (OE-P0-004).
5. **Project creation** — Subprocess-based, may return unusable projects (OE-P1-011).
6. **Render jobs** — In-memory only, lost on restart (OE-P1-009).

## 8. Security Assumptions

- **Local development only.** WebSocket authentication is not implemented.
- Token-based HTTP auth via `BaseHTTPMiddleware` — does not protect WebSocket route.
- Sandbox runs without bwrap/seccomp in dev mode (`OPEN_EDIT_SANDBOX_BACKEND=dev`).
- Provider API keys are read from environment variables or project config — never exposed in responses.

## 9. Upgrade and Rollback

**No migrations changed.** The edit graph schema and project format are unchanged. To roll back any file, `git checkout <file>` reverts to the commit version.

## 10. Root Cause Resolution

The core insight from the investigation: the agent failed in every run because **the LLM tool surface was designed for humans, not LLMs.** Tools raised raw KeyErrors, returned ambiguous empty results, and never signaled whether a failure was temporary (retry) or permanent (wrong params). The `run_script` bug (`ops_missing` on read-only scripts) was the final trap door that pushed the agent out of the IR sandbox and into bash — but even before that, earlier tool failures had already eroded trust in the tool system.

The fixes in this report address every failure mode identified in the `goo` trace:
1. `ops_missing` → 0 ops = success (the sandbox door is now open)
2. `get_style_profile` KeyError → clean "op_type is required" (no crash)
3. `get_transcript_packed` silent empty → `retry: True` (agent knows to wait)
4. `propose_silence_cuts` missing alignment → `retry: True` (agent knows to wait)
5. `analyze_narrative` missing alignment → `retry: True` (agent knows to wait)
6. `chat_only` providers marked accurately → agent system hides tools (no misleading tool calls)

These six changes are individually small but collectively remove every escape hatch that forced the agent to abandon the IR sandbox and fall back to bash.

---

## 11. Repair Batch Update — 2026-07-25

This update implements and tests the next dependency-ordered portions of
Phases 1 and 4. It does **not** mark the wider stabilization plan complete.

### Fixed in this batch

- **OE-P0-003 / OE-P1-010:** `POST /api/projects/{project_id}/ingest` now
  accepts a repeated `files` multipart field and returns `{project_id,
  accepted, rejected}`. Each upload uses a unique `.open_edit/inbox/` path,
  is size-limited by `OPEN_EDIT_MAX_UPLOAD_BYTES`, is processed off the event
  loop, and is removed after CAS ingest. Invalid files reject individually
  without rolling back valid files from the same batch.
- **OE-P1-011:** project creation initializes the canonical directory and
  SQLite schema through Python storage APIs in a temporary sibling directory.
  It validates the DB before atomic publication and removes the temporary
  directory on failure. Failed HTTP creation returns
  `project_initialization_failed`.
- **OE-P1-012:** project summaries now derive duration, clips, and tracks from
  the canonical applied timeline, not from every ingested asset. A derivation
  failure is visible as `timeline_status: "invalid"` with
  `timeline_error_code: "timeline_derivation_failed"`.
- **OE-P1-005:** LLM config writes now fsync their temp file, refuse to
  overwrite malformed TOML, and preserve unrelated tables including tables
  named similarly to `llm`.
- **OE-P1-006 / OE-P1-008:** the generic LLM key override is scoped to the
  selected provider, and Pi cost parsing starts from the existing session
  file size so a second turn does not recount earlier turns.
- **OE-P0-004:** the chat WebSocket now independently authenticates remote
  upgrades before `accept()`. Remote access requires `OPEN_EDIT_TOKEN`, a
  matching token, and an explicit `OPEN_EDIT_ALLOWED_ORIGINS` entry. Localhost
  keeps its documented bypass. Chat messages have configurable byte and
  per-client/project rate limits. The browser only adds its configured token
  to a WSS URL, never `ws://`.
- **OE-P0-002:** provider configuration responses now expose registry-derived
  labels, agent modes, and tool/session capability metadata. The selector
  labels each visible provider as a full editing agent or chat only. Chat-only
  providers receive no tool schemas, and a malformed tool event is rejected
  before it can execute a mutation.
- **OE-P1-013 (partial):** whole-graph reorder now validates a complete,
  duplicate-free permutation and performs the sequence replacement in one
  SQLite transaction. Invalid reorder requests do not leave partial ordering
  state.
- **OE-P1-013 (partial):** the public delete endpoint now records a reversible
  `reverted` status transition rather than hard-deleting durable history, and
  rejects reversion where later operations still reference the target.

### Evidence

```bash
cd open_edit
python -m pytest \
  tests/test_llm_config.py tests/test_serve_cost.py \
  tests/test_serve_llm_usage.py tests/test_stream_chat_pi_refactor.py \
  tests/test_providers.py tests/test_serve_asset_stream.py \
  tests/test_serve_projects.py tests/test_errors.py -q
```

Result: **92 passed** (one third-party FastAPI/httpx deprecation warning).

WebSocket regression evidence:

```bash
cd open_edit
python -m pytest tests/test_serve_ws.py tests/test_serve_errors.py \
  tests/test_serve_send_reconnect.py -q
```

Result: **25 passed** (one third-party FastAPI/httpx deprecation warning).

Combined repair-batch regression command, covering provider configuration,
credentials/cost accounting, project lifecycle and ingest, WebSocket policy,
agent behavior, and edit-graph storage:

```bash
cd open_edit
python -m pytest \
  tests/test_llm_config.py tests/test_serve_cost.py \
  tests/test_serve_llm_usage.py tests/test_stream_chat_pi_refactor.py \
  tests/test_providers.py tests/test_serve_llm_config_api.py \
  tests/test_serve_asset_stream.py tests/test_serve_projects.py \
  tests/test_serve_ws.py tests/test_serve_errors.py \
  tests/test_serve_send_reconnect.py tests/test_serve_agent.py \
  tests/test_agent_loop_stability.py tests/test_serve_edit_graph_api.py \
  tests/test_storage/test_edit_graph.py tests/test_storage/test_phase1_integrity.py -q
```

Result: **passed** (one third-party FastAPI/httpx deprecation warning).

### OE-P1-009 — Durable render service (implemented core)

- Added `serve/render_service.py` as the shared REST and agent render path.
  It persists per-project SQLite jobs and uses the states `queued`, `running`,
  `cancelling`, `cancelled`, `succeeded`, `failed`, and `orphaned`.
- Added per-project serialization, process-wide configurable concurrency
  (`OPEN_EDIT_RENDER_CONCURRENCY`), restart recovery that marks unfinished
  jobs orphaned, and POSIX process-group TERM/KILL cleanup with a bounded
  grace period.
- The launcher now invokes `sys.executable -m open_edit.cli`, not a bare
  `open_edit` binary, and consumes explicit `render --json` output rather
  than inferring paths from arbitrary stdout.
- REST polling, cancellation, agent-triggered proxy/final renders, and the
  browser poller now use the durable state model. Overlay rendering remains a
  separate legacy path and must be folded into this service before this issue
  is fully accepted.

Focused validation:

```bash
cd open_edit
python -m compileall -q open_edit/serve/render_service.py \
  open_edit/serve/app.py open_edit/serve/tool_executor.py open_edit/cli.py
python -m pytest tests/test_render_service.py tests/test_serve_render_jobs.py \
  tests/test_storage/test_render_snapshots.py tests/test_serve_agent.py -q
```

Result: **passed**. The new tests cover durable retrieval after constructing a
new service, startup orphan recovery, and same-project serialization.

### OE-P1-013 — Optimistic graph revisions (implemented core)

- `EditGraphStore` now keeps a monotonic `graph_revision` in `project_meta`.
  Append, status changes, hard delete, move, and both reorder paths advance it
  within the same SQLite transaction as the mutation.
- Storage accepts an optional `expected_revision` and raises an explicit
  `GraphRevisionConflict` before changing a stale graph.
- The status, reversible-delete, and whole-reorder APIs accept
  `expected_revision`, return `graph_revision`, and translate stale writes to
  HTTP 409.

Focused validation:

```bash
cd open_edit
python -m pytest tests/test_storage/test_edit_graph.py \
  tests/test_storage/test_phase1_integrity.py \
  tests/test_serve_edit_graph_api.py -q
```

Result: **passed** (third-party FastAPI/httpx deprecation warning). The new
storage regression proves a stale reorder preserves both the newer order and
the newer revision.

### Remaining blocking phases

Complete browser E2E coverage and Go/Python render integration remain
required before the plan's definition of done can be claimed. Hard
melt/ffmpeg child-process cleanup under real renderers is still an
acceptance gap for OE-P1-009.

## 13. Repair Batch Update — 2026-07-25 (Phases 5/6/7)

### Fixed in this batch

**Phase 5**
- Added `serve/edit_graph_service.py` as the shared mutation path for
  manual UI and future AI callers (`add_clip`, `move_clip`, `trim_clip`,
  `split_clip`, `remove_clip`, `change_track`).
- `POST /api/projects/{id}/ops` appends validated ops with
  `expected_revision` and `author=user`.
- `GET /api/projects/{id}` now returns `graph_revision`,
  `timeline_status`, and `timeline_error_code`.
- Edit Graph Undo/Revert send `expected_revision`.
- Asset cards expose **Add** → `add_clip` on track V1.
- Polling refreshes only when `graph_revision` changes.

**Phase 6**
- Render jobs persist `graph_revision` + `edit_graph_hash`.
- Enqueue refuses invalid timelines and stale `expected_revision`.
- Overlay mode is folded into `RenderService` (same durable job /
  cancel / orphan policy as proxy/final).
- Agent `trigger_render` overlay path uses the durable service.

**Phase 7**
- Upload UI shows per-file accepted/rejected results.
- `listRenders` no longer swallows errors; UI shows a degraded-state
  warning instead of an empty list.
- Send button gates on project + provider + model, with a precise
  `title` reason.

### Evidence

```bash
cd open_edit
python -m pytest tests/test_phase567_edit_render.py tests/test_render_service.py \
  tests/test_serve_edit_graph_api.py tests/test_serve_projects.py -q
```

Result: **passed**.

Expanded repair regression (providers, WS, agent, ingest, Phase 5/6/7):
**passed**.

### Still open

- Full drag/trim/split timeline interaction in the canvas
- Playwright golden E2E
- Real melt/ffmpeg process-tree cancel integration tests
- Go/Python contract parity (Phase 8)

## 12. Repair Batch Update — 2026-07-25 (OE-P1-007)

### Plan assessment

`OpenEdit_Repair_Plan.md` is sound: dependency-ordered phases, explicit
acceptance criteria, and a correct product boundary (Python UI/server as
surface, Go/MLT as render adapter). One documentation mistake was fixed:
`docs/architecture/CURRENT_SYSTEM.md` still claimed the Go pipeline was
the supported product path; that contradicted Phase 0 / TARGET and the
code users actually run.

### Fixed in this batch

- **OE-P1-007:** every provider now declares `context_strategy`
  (`native_session` | `full_history` | `stateless`).
  - Pi: `native_session` (last user turn + session id).
  - Anthropic / OpenAI / OpenCode / Antigravity: `full_history`.
  - JCode (hidden): `stateless`.
- `_stream_cli` serializes role-separated conversation text for
  `full_history` adapters instead of discarding all but the latest user
  message. Transcripts are truncated from the oldest turn under a
  32 KB budget.
- OpenCode / Antigravity command builders no longer double-wrap an
  already role-tagged transcript in a second `[user]` envelope.
- Config API capability payloads expose `context_strategy`.

### Evidence

```bash
cd open_edit
python -m pytest tests/test_stream_chat_opencode.py tests/test_providers.py \
  tests/test_cli_adapter.py tests/test_serve_llm_config_api.py -q
```

Result: **passed**.

The new OpenCode regression proves a second-turn prompt contains the
first-turn user fact (`nebula-42`) plus prior assistant text.
