# OpenEdit Stabilization and Repair Execution Plan

**Repository:** `AH64-dll/OpenEdit`  
**Branch reviewed:** `main`  
**Audit date:** 2026-07-24  
**Primary objective:** Turn the current repository into a reliable editor where users can create a project, ingest media, edit manually or through an AI agent, inspect/revise the edit graph, render, cancel work safely, and reopen the project without losing state.

---

## Instructions to the Coding Agent

Act as the lead engineer responsible for stabilizing this project. Execute this plan in order. Do not begin with cosmetic UI work, broad refactoring, or new features. First restore a coherent product architecture and prove the essential workflows with automated tests.

For every issue:

1. Add a failing regression test that demonstrates the defect.
2. Implement the smallest coherent fix.
3. Run the relevant unit, integration, browser, Go, and Python tests.
4. Record any changed API or storage contract.
5. Do not hide failures with `except Exception: pass`, fallback-to-empty behavior, or fake success responses.
6. Do not mark a phase complete until its acceptance criteria pass.

Use one focused pull request or commit series per phase. Avoid a full rewrite unless a phase explicitly requires replacing a broken subsystem.

---

# 1. Executive Diagnosis

The repository currently contains two different product paths:

- A root Go/MLT pipeline under `cmd/`, `internal/`, `run.sh`, and `edit.sh`.
- A much larger experimental Python application under `open_edit/`, including the FastAPI server, browser UI, AI agent, edit graph, assets, rendering, review, sandbox, and provider integrations.

This split is the first architectural problem. A bug can be fixed in one path while the user is actually running the other. The Python product also has several duplicated registries and duplicated execution paths that have already drifted apart.

The most important failures found in the static audit are:

1. **Provider definitions disagree across the project.** `jcode` is registered in one place but rejected or absent elsewhere; Anthropic and OpenAI exist in the provider layer but are excluded from the UI configuration endpoint.
2. **Some CLI providers are treated as complete editing agents while they do not support OpenEdit tools.** OpenCode and Antigravity are currently chat-only in their adapters, yet the agent dispatcher classifies them as owning a complete agent loop.
3. **The frontend and backend disagree on file ingestion.** The browser submits every selected file under two field names, while the backend accepts one `file` only.
4. **Provider configuration can destroy unrelated TOML settings.** Saving `[llm]` rewrites the file and intentionally drops other sections.
5. **API-key resolution can select a key belonging to the wrong provider.** This produces confusing authentication failures and risks sending the wrong credential to a provider SDK.
6. **Render jobs and rate limits live only in process memory.** Restarting the server loses job state; concurrent renders and cancellation are not robust.
7. **The WebSocket chat route needs an explicit authentication and abuse-control audit.** HTTP token middleware does not automatically prove that the WebSocket route is protected.
8. **The CLI stream path loses conversation context for adapters that do not implement sessions.** It extracts only the last user message.
9. **Cost accounting for Pi appears to read from byte offset zero every turn.** This can repeatedly count the entire session instead of the current turn delta.
10. **Project creation may return success after initialization failed, leaving a folder that is not recognized as a project.**
11. **The project timeline summary is partly derived from raw asset duration rather than the applied edit timeline.**
12. **Many broad exception handlers convert corruption or integration failures into empty state.** This makes the UI look blank instead of explaining what failed.

The repair strategy below addresses these in dependency order.

---

# 2. Severity Model

- **P0 — Blocking:** The main workflow cannot work correctly, data/security is at risk, or the UI promises functionality the backend cannot perform.
- **P1 — Major:** The workflow works only under narrow conditions, loses state, misreports success, or fails unpredictably.
- **P2 — Reliability:** Error handling, performance, testing, observability, and maintainability problems likely to create future defects.
- **P3 — Polish:** UI clarity and developer-experience improvements that do not block correctness.

---

# 3. Confirmed and High-Risk Findings

## OE-P0-001 — Provider Registry Drift

**Affected files**

- `open_edit/open_edit/serve/providers.py`
- `open_edit/open_edit/serve/llm_config.py`
- `open_edit/open_edit/serve/cli_adapter.py`
- `open_edit/open_edit/serve/runtimes/registry.py`
- `open_edit/open_edit/serve/app.py`
- Provider/model controls in `open_edit/open_edit/serve/static/`

**Observed conflict**

- `providers.py` registers six providers, including `jcode`.
- `llm_config.py` validates only five and excludes `jcode`.
- `cli_adapter.py` registers only `pi`, `opencode`, and `antigravity`.
- `runtimes/registry.py` advertises six providers.
- `GET/PUT /api/projects/{id}/llm-config` uses only `cli_adapter.list_adapters()`, so Anthropic and OpenAI are omitted even though SDK implementations exist.
- `llm.py` contains a `jcode` output branch, but no JCode adapter can be returned by `get_adapter("jcode")`.

**Impact**

Provider selection can be missing, rejected, saved but unusable, or fail at runtime with a `KeyError`. The UI, configuration file, runtime discovery, and dispatcher do not describe the same system.

**Required fix**

Create one canonical provider registry. Each entry must include:

```text
id
label
transport: sdk | cli
agent_mode: openedit_loop | external_loop | chat_only
installed/discovery strategy
default model
model discovery function
auth strategy
supports_tools
supports_images
supports_sessions
adapter/stream factory
```

All API validation, model lists, UI options, runtime discovery, and dispatcher behavior must derive from this registry. Remove provider-name literals and parallel hardcoded lists wherever practical.

For JCode, choose exactly one outcome:

- Implement and test a real adapter, or
- Remove/hide it from every public registry until it is supported.

Do not leave a half-registered provider.

**Regression tests**

- A registry-consistency test that asserts every public provider can be loaded, validated, listed, configured, and dispatched.
- Parameterized tests for every provider ID.
- API test proving Anthropic and OpenAI appear when supported.
- API test proving an unsupported provider cannot appear in the UI.

---

## OE-P0-002 — CLI Agent Ownership Does Not Match Tool Capability

**Affected files**

- `open_edit/open_edit/serve/providers.py`
- `open_edit/open_edit/serve/agent.py`
- `open_edit/open_edit/serve/cli_adapter.py`
- `open_edit/open_edit/serve/opencode_adapter.py`
- `open_edit/open_edit/serve/pi_bridge.py`

**Observed conflict**

OpenCode and Antigravity adapters return `supports_tools() == False`, and OpenCode deliberately ignores `toolCall` events. However, all CLI providers are marked `owns_agent_loop=True`, which means `agent.py` assumes the external CLI can run the complete edit/tool loop.

The current system prompt hides tools for adapters that report no tool support, so these providers can converse but cannot actually edit the project. This contradicts the product expectation that selecting an AI provider gives it access to assets, timeline operations, and rendering tools.

**Required fix**

Replace the boolean `owns_agent_loop` with a clear execution mode:

- `openedit_loop`: OpenEdit calls the model and executes normalized tool calls locally.
- `external_loop`: The provider executes tools through a verified bridge and returns tool-use and tool-result events.
- `chat_only`: The provider cannot mutate the project.

Recommended provider behavior:

- Anthropic/OpenAI: `openedit_loop`.
- Pi: `external_loop` only after bridge contract tests pass.
- OpenCode: either implement an OpenEdit tool bridge and mark `external_loop`, or mark `chat_only` and make that limitation explicit in the UI.
- Antigravity: same rule as OpenCode.
- JCode: do not expose until its mode is implemented and tested.

The UI must show capability labels such as **Full editing agent**, **Chat only**, or **Unavailable**. A chat-only provider must not be presented as capable of applying edits.

**Regression tests**

- Selecting a full editing provider and requesting “add clip X to track 1” produces exactly one mutation.
- No external-loop tool is executed twice.
- Chat-only providers never claim an edit succeeded.
- Tool calls and results remain paired after switching providers mid-conversation.

---

## OE-P0-003 — Upload Contract Is Broken for Multiple Files

**Affected files**

- `open_edit/open_edit/serve/static/js/api.js`
- `open_edit/open_edit/serve/app.py`

**Observed conflict**

The browser appends each selected file under both `files` and `file`. The FastAPI endpoint accepts one `file: UploadFile`. Selecting multiple files therefore sends duplicate multipart parts without a matching server contract.

**Required fix**

Choose one documented contract. Recommended:

```python
files: list[UploadFile] = File(...)
```

Return a batch result:

```json
{
  "project_id": "...",
  "accepted": [...],
  "rejected": [
    {"filename": "...", "error": "..."}
  ]
}
```

The frontend must append each file exactly once under `files`. It should display progress per file and preserve successful ingests even if another file fails.

For atomic all-or-nothing behavior, state that explicitly and clean up every partial CAS write. Partial-success behavior is preferable for a media importer.

**Regression tests**

- One file.
- Multiple files.
- Duplicate filenames.
- One valid and one invalid file.
- Zero-byte file.
- Interrupted upload.
- File exceeding configured size limit.

---

## OE-P0-004 — WebSocket Authentication and Origin Protection Must Be Explicit

**Affected files**

- `open_edit/open_edit/serve/app.py`
- `open_edit/open_edit/serve/static/js/ws.js`

**Risk**

The token check is implemented through `BaseHTTPMiddleware`, while chat is a WebSocket route. The WebSocket client also creates a URL without a token. Do not assume the HTTP middleware protects the WebSocket handshake.

**Required fix**

Add a WebSocket-specific authentication function before `accept()`:

- Localhost may retain the documented local bypass.
- Remote connections must validate `OPEN_EDIT_TOKEN` through a secure, documented mechanism.
- Validate the `Origin` header against allowed origins for remote use.
- Reject unauthorized clients with an appropriate close code.
- Never print the token in logs.
- Add message-size limits and per-client/per-project rate limits.

Because browsers cannot attach arbitrary Authorization headers to `new WebSocket()`, use one of these approaches:

1. Same-origin secure cookie created through an authenticated HTTP endpoint, or
2. A short-lived WebSocket ticket, or
3. A query token only when HTTPS/WSS is mandatory and logs are guaranteed to redact it.

The short-lived ticket approach is preferred for remote access.

**Regression tests**

- Localhost behavior with no token.
- Remote connection with token disabled.
- Remote connection with token enabled and missing/invalid token.
- Valid remote connection.
- Disallowed Origin.
- Oversized message.
- Rate-limit exhaustion.

---

## OE-P1-005 — Saving LLM Configuration Deletes Other TOML Sections

**Affected file**

- `open_edit/open_edit/serve/llm_config.py`

**Observed behavior**

`save_llm_config()` warns that it rewrites the file and drops unrelated content. This becomes data loss as soon as `.open_edit/config.toml` contains any other project settings.

**Required fix**

Use a TOML library that preserves or safely merges tables. At minimum:

1. Parse the existing file.
2. Replace only the `llm` table.
3. Preserve all unrelated tables and keys.
4. Write to a temporary file.
5. `fsync` the file when durability matters.
6. Atomically replace the original.
7. Keep a backup if parsing fails; never overwrite malformed configuration.

**Regression tests**

- Save into an empty file.
- Update an existing `[llm]` table.
- Preserve `[render]`, `[ui]`, and unknown custom tables.
- Preserve UTF-8 values.
- Malformed TOML does not get overwritten.
- Simulated write interruption leaves the original readable.

---

## OE-P1-006 — Provider API-Key Selection Can Use the Wrong Credential

**Affected file**

- `open_edit/open_edit/serve/llm.py`

**Observed behavior**

`_api_key(provider)` checks generic and unrelated provider environment variables before provider-specific stored keys. For example, an OpenAI key may be returned while Anthropic is selected.

**Required fix**

Use a provider-specific mapping:

```text
anthropic -> ANTHROPIC_API_KEY -> stored anthropic key
openai    -> OPENAI_API_KEY    -> stored openai key
...
```

Treat `OPEN_EDIT_LLM_API_KEY` as an explicit override only when the project/provider configuration says it applies to the currently selected provider. Never fall through to an arbitrary stored key from another provider.

Return a precise error such as:

```text
Anthropic is selected, but no Anthropic key is configured.
```

Do not expose key values in diagnostics, responses, or exceptions.

**Regression tests**

- Both provider keys are configured; each SDK receives only its own.
- Only the wrong provider key exists; the selected provider fails clearly.
- Stored-key precedence is deterministic.
- Generic override behavior is documented and tested.

---

## OE-P1-007 — CLI Conversation Context Is Lost

**Affected files**

- `open_edit/open_edit/serve/llm.py`
- `open_edit/open_edit/serve/cli_adapter.py`

**Observed behavior**

`_stream_cli()` scans the message list and extracts only the latest user text. Pi may retain state through its session ID, but OpenCode and Antigravity command builders ignore `session_id`, and the prior conversation is not serialized into the request.

**Required fix**

Every adapter must explicitly declare one context strategy:

- Native persistent session.
- Full normalized conversation passed each turn.
- Stateless chat, visibly labeled and not used as an editing agent.

For full-history mode, serialize role-separated messages with a token budget and summary policy. Do not silently discard earlier user instructions, tool results, or project decisions.

**Regression tests**

A two-turn test must prove that the second answer can use a fact supplied only in the first turn for every provider advertised as conversational.

---

## OE-P1-008 — Pi Cost Delta Starts at Byte Zero

**Affected file**

- `open_edit/open_edit/serve/llm.py`

**Observed behavior**

`baseline_size` is initialized to zero before the Pi call and is not set to the current session file size. Parsing from zero can count previous session events again.

**Required fix**

Before invoking Pi:

1. Resolve the existing session file, if any.
2. Record its byte size.
3. After the call, parse only bytes after that offset.
4. Handle log rotation or file replacement.
5. Keep session cumulative cost separate from turn cost.

Prefer provider-reported request IDs and usage values when available.

**Regression tests**

- First turn cost.
- Second turn in same session reports only second-turn delta.
- Session cumulative equals turn 1 + turn 2, not turn 1 + full log.
- Rotated/truncated session file.

---

## OE-P1-009 — Render Jobs Are Ephemeral and Process Handling Is Fragile

**Affected files**

- `open_edit/open_edit/serve/app.py`
- `open_edit/open_edit/serve/tool_executor.py`
- Other render/orchestrator modules under `open_edit/open_edit/render/`

**Observed behavior**

- REST render jobs are stored in `_RENDER_JOBS` and `_RENDER_TASKS` dictionaries.
- A server restart loses job status.
- REST and agent tools contain separate render-launch logic.
- Output is inferred from the last stdout line or newest MP4.
- Cancellation sends terminate/kill but does not consistently use a process group, grace timeout, and forced cleanup.
- There is no clear global or per-project concurrency policy.

**Required fix**

Create one `RenderService` used by REST, agent tools, and verification. It must provide:

- Durable SQLite job records.
- States: `queued`, `running`, `cancelling`, `cancelled`, `succeeded`, `failed`, `orphaned`.
- Per-project lock and configurable global concurrency limit.
- Structured render result written as JSON, not parsed from arbitrary stdout.
- Process-group creation so child `ffmpeg`/`melt` processes are cancelled too.
- Graceful terminate, bounded wait, then forced kill.
- Temporary output followed by atomic rename on success.
- Recovery on server startup: running jobs become `orphaned` or are safely resumed.
- Progress events where the renderer can provide them.
- A single timeout policy.

Use one centralized CLI launcher. Do not require a bare `open_edit` executable to be present on `PATH` when the package is running from source; support `sys.executable -m open_edit.cli` or call the Python service directly.

**Regression tests**

- Successful proxy and final render.
- Renderer nonzero exit.
- Timeout.
- User cancellation.
- Child process cleanup.
- Two renders for the same project.
- Renders for different projects under the global limit.
- Server restart while a job is running.
- Output paths containing spaces.
- Renderer logging extra stdout lines.

---

## OE-P1-010 — Upload Processing Can Block and Collide

**Affected file**

- `open_edit/open_edit/serve/app.py`

**Observed behavior**

The uploaded stream is copied synchronously inside an async route to `project_path / safe_name`. Two concurrent uploads with the same filename can share the same temporary path. Large copies can block the event loop.

**Required fix**

- Stream to a unique temporary path under `.open_edit/inbox/` or the OS temp directory.
- Enforce a configurable maximum upload size while streaming.
- Use async file I/O or `asyncio.to_thread` for blocking copies.
- Do not trust extension alone; probe content.
- Use a per-upload ID.
- Clean up temp files in all error/cancellation paths.
- Deduplicate by content hash after ingest.
- Never overwrite a user file in the project root.

---

## OE-P1-011 — Project Creation Can Return an Unusable Project

**Affected file**

- `open_edit/open_edit/serve/projects.py`

**Observed behavior**

If `open_edit init` fails, the function logs a warning and still returns a project object, but project discovery requires `.open_edit/edit_graph.db`. The newly returned project can disappear from the next project list.

**Required fix**

Make creation transactional:

1. Create in a temporary directory.
2. Initialize schema and stores through Python APIs, not a subprocess where possible.
3. Validate required files and schema version.
4. Rename into the final project directory only after success.
5. On failure, remove the temporary directory or mark it as a recoverable failed project.
6. Return a non-2xx error with a stable error code.

**Regression tests**

- Successful creation appears immediately and after restart.
- Initialization failure does not return 201.
- Duplicate project name.
- Invalid name.
- Permission denied.
- Interrupted creation.

---

## OE-P1-012 — Timeline Summary Does Not Represent the Edited Timeline

**Affected file**

- `open_edit/open_edit/serve/projects.py`

**Observed behavior**

`total_duration_s` is computed by summing the durations of all ingested assets. That is not the duration of the current edited timeline: unused assets, trims, overlaps, speed changes, gaps, and multiple tracks make it incorrect.

**Required fix**

Derive all timeline summary fields from the canonical applied timeline produced by `ir.apply.derive_timeline()`. Use raw assets only as inputs, never as a substitute for the applied timeline.

If timeline derivation fails, return a visible degraded-state object:

```json
{
  "timeline_status": "invalid",
  "timeline_error_code": "..."
}
```

Do not silently return a plausible but wrong number.

---

## OE-P1-013 — Hard Delete and Reorder Need Transactional Semantics

**Affected files**

- `open_edit/open_edit/serve/app.py`
- `open_edit/open_edit/storage/edit_graph.py`
- `open_edit/open_edit/ir/validate.py`

**Risk**

The storage layer describes the graph as a durable history that includes reverted and superseded operations, while the REST API exposes hard deletion. Reorder performs repeated moves rather than one validated atomic operation.

**Required fix**

- Define whether edit history is append-only or mutable.
- Prefer revert/tombstone for committed operations.
- Reserve hard deletion for uncommitted drafts or explicit destructive maintenance.
- Validate references before status changes/deletion.
- Reorder the entire requested set in one database transaction.
- Reject missing IDs, duplicates, incomplete permutations where a full ordering is required, and dependency-invalid orders.
- Increment a graph revision/hash after every successful mutation.
- Support optimistic concurrency with `expected_revision` to prevent stale UI writes.

**Regression tests**

- Reorder success and rollback on failure.
- Duplicate IDs.
- Concurrent reorder requests.
- Delete/revert an operation referenced by later operations.
- Stale revision conflict.
- Derived timeline remains valid after every accepted mutation.

---

## OE-P2-014 — Subprocess Streaming Can Deadlock or Run Indefinitely

**Affected file**

- `open_edit/open_edit/serve/llm.py`

**Risks**

- Timeout is applied to individual stdout reads, not necessarily total process lifetime.
- `stderr` is not continuously drained while stdout is streamed.
- A verbose child process can fill the stderr pipe and block.
- Unknown JSON events are often silently discarded.

**Required fix**

Implement a shared async process supervisor:

- Total wall-clock timeout plus optional inactivity timeout.
- Concurrent stdout and stderr drain tasks.
- Bounded buffers and truncation markers.
- Process-group cancellation.
- Exit-code handling independent of whether text was already emitted.
- Structured diagnostics with provider, command basename, duration, exit code, and redacted stderr.
- Contract tests using fake child processes.

---

## OE-P2-015 — Broad Exception Handling Hides Corruption

**Affected areas**

- `serve/agent.py`
- `serve/app.py`
- `serve/projects.py`
- `serve/tool_executor.py`
- storage and render fallbacks

**Required fix**

Classify failures:

- User input error → 4xx / tool error.
- Missing dependency/runtime → actionable configuration error.
- Corrupt project state → project health error; do not return empty state as if valid.
- Transient provider/network failure → retry only before any streamed output, with bounded attempts.
- Internal invariant violation → log stack trace with correlation ID and return stable error code.

Every broad exception must either:

1. Be narrowed to expected exception classes, or
2. Log context and return an explicit degraded/error state.

No silent `pass` in a data, provider, render, authentication, or persistence path.

---

# 4. Target Architecture

Adopt the following product boundary unless repository owners explicitly choose another:

```text
Browser UI
   |
FastAPI application / WebSocket gateway
   |
Application services
   |-- ProjectService
   |-- AssetService
   |-- EditGraphService
   |-- AgentService
   |-- RenderService
   |-- ReviewService
   |
Canonical IR + SQLite stores
   |
Compiler/render backend
   |-- Go/MLT adapter where it is the stable implementation
   |-- Python render components only where they add required functionality
```

Recommended decision: make the Python server/UI the product surface and use the stable Go/MLT code through a deliberate adapter for compilation/rendering. Do not maintain two unrelated project formats and two independent render orchestration systems.

The canonical project must have:

```text
project/
  .open_edit/
    project.db or clearly versioned DB files
    config.toml
    assets/
    renders/
    conversations/
    logs/
    temp/
```

All schema changes require versioned migrations and rollback/backup behavior.

---

# 5. Execution Phases

## Phase 0 — Freeze Scope and Build a Reproduction Baseline

### Tasks

- Document which command currently starts the supported product.
- Decide whether the primary runtime is the Python UI/server, the root Go pipeline, or an integrated combination. Use the recommended boundary above unless contradicted by a written product decision.
- Create three tiny deterministic media fixtures:
  - Short video with audio.
  - Short video without audio.
  - Still image.
- Create one damaged/invalid fixture.
- Add `docs/architecture/CURRENT_SYSTEM.md` containing the actual startup and data flow.
- Add `docs/architecture/TARGET_SYSTEM.md` containing the chosen boundary.
- Record the current failing commands and errors without fixing them yet.

### Required baseline commands

```bash
go test ./internal/... -count=1
go build ./cmd/...

cd open_edit
python -m pip install -e ".[dev,openai]"
ruff check open_edit/ tests/
mypy open_edit/ --ignore-missing-imports
pytest tests/ -q
```

Run system-dependent tests in an environment with `ffmpeg`, `ffprobe`, `melt`, Bubblewrap, and the Rust sandbox built.

### Done when

- One document states the primary product path.
- Every current failure is captured in a reproducible test or issue.
- No engineer is fixing an execution path that the product does not use.

---

## Phase 1 — Unify Providers, Models, Capabilities, and Keys

### Tasks

- Implement the canonical provider registry described in OE-P0-001.
- Remove duplicated provider lists.
- Make `/api/runtimes`, `/api/llm/providers`, project config, and the UI consume the same registry.
- Implement or hide JCode.
- Fix provider-specific key selection.
- Preserve all config tables on save.
- Add a health check per provider:
  - installed
  - authenticated
  - model discovery status
  - editing capability
  - session capability
- Never call a slow model-discovery command on the request thread without a bounded cache and timeout.

### API shape

Prefer a single endpoint such as:

```json
{
  "providers": [
    {
      "id": "opencode",
      "installed": true,
      "authenticated": true,
      "agent_mode": "chat_only",
      "supports_tools": false,
      "supports_images": false,
      "supports_sessions": false,
      "models": ["..."]
    }
  ]
}
```

### Done when

- Every listed provider can be selected successfully.
- Every selectable model is valid for that provider.
- Unsupported providers are absent or visibly disabled.
- No provider can receive another provider's secret.
- Saving LLM settings preserves unrelated config.

---

## Phase 2 — Repair the Agent and Tool Protocol

### Tasks

- Introduce the three explicit agent modes.
- Define one normalized event protocol:

```text
turn_started
text_delta
tool_requested
tool_started
tool_result
usage
render_created
warning
error
turn_finished
```

- Enforce event ordering and one terminal event per turn.
- Use stable IDs for turn, tool call, command, render, and correlation.
- Preserve full conversation context or declare stateless behavior.
- Enforce tool idempotency by command ID.
- Make cancellation propagate through model process, tool execution, render process, and verification.
- Make provider switching safe by storing a provider-independent transcript.
- Decide the OpenCode integration:
  - Preferred: implement an OpenEdit bridge/extension that exposes schema-validated tools and emits normalized events.
  - Temporary: chat-only mode, clearly disabled for edit requests.
- Add tool authorization boundaries so the model can only call registered project-scoped tools.

### Tool-loop invariants

- A tool request executes at most once.
- Every tool request receives exactly one result or explicit cancellation result.
- An edit mutation commits transactionally.
- A render result points to an existing, nonempty file before success is emitted.
- The model cannot access arbitrary paths outside its project/sandbox.

### Done when

The following prompt succeeds with a full-capability provider:

```text
Add the first ingested clip to track 1, trim it to five seconds,
add a short title overlay, render a proxy, and report what changed.
```

The UI must display each tool step, the edit graph must contain one copy of each intended operation, and the proxy must be playable.

---

## Phase 3 — Secure and Stabilize HTTP/WebSocket Boundaries

### Tasks

- Implement explicit WebSocket authentication and Origin validation.
- Add request/body/message size limits.
- Add per-IP, per-token, and per-project rate limits for expensive actions.
- Centralize error codes and response schemas.
- Add a WebSocket send lock/queue if multiple internal tasks can emit concurrently.
- Make disconnect cleanup deterministic.
- Ensure replacing a project socket cannot leak events from the old project.
- Add correlation IDs to HTTP requests, WS connections, turns, tools, and renders.
- Add CORS configuration only when remote browser origins are intentionally supported.

### Done when

Security tests prove unauthorized remote users cannot chat, mutate, upload, read assets, inspect diagnostics, or trigger renders.

---

## Phase 4 — Repair Project Creation and Media Ingestion

### Tasks

- Replace subprocess-based project initialization with a Python service where possible.
- Make project creation transactional.
- Implement the canonical multi-file upload contract.
- Add unique temporary paths, size limits, cleanup, and content probing.
- Preserve original filename as metadata, not as a writable project-root path.
- Return granular batch errors.
- Generate thumbnail/proxy metadata asynchronously where needed.
- Verify CAS sidecars and media metadata after ingest.
- Add a project-health endpoint that checks DB, asset sidecars, render folders, and schema versions.

### Done when

A fresh user can create a project, upload several media types, reload the server, and see/play all successfully ingested assets with no duplicates or vanished projects.

---

## Phase 5 — Make the Edit Graph a Correct Interactive Editor

### Tasks

- Define the edit graph's source-of-truth and append-only/mutable rules.
- Add graph revision and optimistic concurrency.
- Make status updates, reorder, revert, and supported deletion transactional.
- Validate every operation against assets, tracks, time ranges, and dependencies.
- Derive the visible timeline from the graph after every accepted mutation.
- Add manual timeline commands:
  - Add asset to track at time.
  - Move clip.
  - Trim in/out.
  - Split clip.
  - Delete/revert clip.
  - Change track.
  - Adjust overlay/effect parameters.
- Ensure the Edit Graph panel is an editor, not only an activity log:
  - Select operation.
  - Inspect normalized fields.
  - Edit permitted parameters.
  - Preview proposed change.
  - Apply with revision check.
  - Revert.
- Use the same service methods for AI changes and manual UI changes.

### Done when

A user can place and move a clip manually, then ask the AI to modify it, then manually revise the AI operation, with all three actions represented consistently in the graph and timeline.

---

## Phase 6 — Consolidate and Harden Rendering

### Tasks

- Build the single durable `RenderService` from OE-P1-009.
- Choose the canonical compiler/render backend.
- If Go/MLT is retained, expose it through a structured adapter instead of shell-output guessing.
- Store render input graph hash/revision with each job.
- Refuse or clearly label rendering from a stale/invalid graph.
- Add proxy/final profiles with explicit codec, resolution, bitrate, and timeout settings.
- Surface progress and logs safely.
- Make render artifacts reproducible from graph revision + profile.
- Integrate visual verification only after base rendering is reliable.

### Done when

Render, cancel, retry, restart recovery, and concurrent-project behavior pass integration tests, and no orphan `ffmpeg`, `melt`, browser, or sandbox processes remain.

---

## Phase 7 — Repair Frontend State and User Feedback

### Tasks

- Generate or validate the frontend API contract from backend schemas.
- Remove compatibility payloads that send multiple contradictory shapes.
- Implement a real upload queue with per-file progress and errors.
- Show provider capability/status in the selector.
- Disable Send during invalid provider states with a precise reason.
- Keep chat, project state, edit graph, timeline, assets, and render list synchronized by revision/event IDs rather than arbitrary refresh timers.
- Do not swallow render-list errors and pretend the list is empty; show a nonblocking degraded-state warning.
- Add pending, success, failure, retry, and cancellation states for every long operation.
- Ensure the timeline and graph remain usable on small screens.
- Preserve keyboard accessibility and focus behavior.

### Required browser tests

Use Playwright or an equivalent real-browser runner for:

- Create/select project.
- Upload one and many files.
- Asset preview.
- Provider selection.
- Two-turn chat.
- Tool cards.
- Stop/cancel.
- Manual timeline edit.
- Edit graph update/revert.
- Proxy render and playback.
- WebSocket drop/reconnect.
- Server error display.

Node DOM stubs may remain for small component tests, but they do not replace real browser end-to-end coverage.

---

## Phase 8 — Integrate the Go and Python Paths

### Tasks

- Decide which layer owns metadata analysis, EDL/IR compilation, and MLT emission.
- Define a versioned JSON schema exchanged between Python and Go.
- Add contract fixtures consumed by both languages.
- Remove or deprecate duplicate implementations after parity is proven.
- Make `run.sh`/`edit.sh` call the same canonical services or clearly label them as legacy tools.
- Replace hidden stage markers based only on file existence with graph/input hashes. A stale `edl.json` or `project.mlt` must not be reused after inputs change.
- Validate outputs after every stage rather than treating file existence as success.

### Done when

The same sample project produces equivalent canonical timeline and render outputs through the supported CLI and the UI path.

---

## Phase 9 — Observability, Security, and Recovery

### Tasks

- Replace print/traceback calls with structured logging.
- Redact keys, tokens, prompts where configured, filesystem secrets, and query credentials.
- Add stable error codes and user-action hints.
- Add project health/repair tooling:
  - DB integrity check.
  - Migration status.
  - Missing asset detection.
  - Corrupt sidecar report.
  - Orphan render cleanup.
  - Conversation JSONL validation.
- Back up DB/config before destructive migrations or repairs.
- Enforce sandbox and path containment for every tool and renderer.
- Add dependency and secret scanning in CI.
- Document remote-hosting security requirements.

### Done when

A corrupted project is reported as corrupted with a repair path; it never silently appears as an empty valid project.

---

## Phase 10 — CI, Release Gates, and Documentation

### CI jobs

1. Python lint/type/unit tests.
2. Go test/build.
3. Rust sandbox build/test.
4. Storage migration tests.
5. Mock-provider agent protocol tests.
6. Media integration tests with `ffmpeg`, `ffprobe`, and `melt`.
7. Real browser tests.
8. Security tests for auth, path containment, uploads, and WebSocket origin.
9. Optional external-provider smoke tests triggered manually with protected secrets.

### Release gates

A release is blocked unless:

- Fresh install passes.
- Upgrade from the previous schema passes.
- The golden end-to-end workflow passes.
- No P0/P1 issue is open.
- No provider is advertised without a passing capability test.
- No database migration is destructive without backup/recovery.
- Render cancellation leaves no child processes.

### Documentation to update

- Root README: supported architecture and startup command.
- Provider capability matrix.
- Local versus remote security.
- Project format and migrations.
- Troubleshooting with error codes.
- Developer test matrix.
- Legacy/deprecated paths.

---

# 6. Required Test Matrix

## Provider matrix

For every provider exposed to users, record and test:

| Capability | Anthropic | OpenAI | Pi | OpenCode | Antigravity | JCode |
|---|---:|---:|---:|---:|---:|---:|
| Listed consistently | Required | Required | Required | Required | Required | Required or hidden |
| Configure model | Required | Required | Required | Required | Required | Required or hidden |
| Authentication check | Required | Required | Required | Required | Required | Required or hidden |
| One-turn chat | Required | Required | Required | Required | Required | Required or hidden |
| Multi-turn context | Required | Required | Required | Required if advertised | Required if advertised | Required if advertised |
| OpenEdit tools | Required if full agent | Required if full agent | Required if full agent | Implement or label chat-only | Implement or label chat-only | Implement or hide |
| Cancellation | Required | Required | Required | Required | Required | Required if exposed |
| Usage/cost reporting | Honest result | Honest result | Correct delta | Honest result | Honest result | Honest result |

Do not fill unsupported cells with fake success. Mark them unsupported and reflect that in the UI.

## Golden end-to-end workflow

Automate this exact flow:

1. Start server in a temporary projects root.
2. Create project.
3. Upload two media files and one image.
4. Play each asset preview.
5. Manually add a clip to track 1.
6. Ask a full agent to trim it and add a title.
7. Inspect and modify the resulting operation manually.
8. Render proxy.
9. Cancel a second render.
10. Restart server.
11. Reload project, history, edit graph, and render records.
12. Render final output.
13. Validate output duration, streams, and nonzero size with `ffprobe`.

---

# 7. First Implementation Batch

The agent should begin with these changes because they are small enough to review and unblock later phases:

## Batch A — Tests first

- Add provider registry consistency test.
- Add API test showing Anthropic/OpenAI are currently absent from project config options.
- Add JCode selection/dispatch test.
- Add config-preservation test.
- Add wrong-provider-key test.
- Add multi-file ingest contract test.
- Add Pi second-turn cost-delta test.
- Add project-init failure test.

## Batch B — Canonical provider registry

- Introduce provider definitions and execution modes.
- Derive config validation and UI listing from it.
- Hide JCode unless implemented.
- Correct key mapping.
- Preserve TOML.

## Batch C — Upload and project creation

- Make project initialization transactional.
- Implement `files[]` ingestion with unique temp paths and limits.
- Update frontend to send one canonical payload.

## Batch D — Agent truthfulness

- Mark OpenCode/Antigravity chat-only immediately unless their tool bridge is implemented in the same batch.
- Prevent chat-only providers from claiming edit capability.
- Add full-history strategy.

These batches should land before timeline UI redesign or new effects.

---

# 8. Coding Rules

- Use typed domain exceptions, not strings, to distinguish expected failures.
- Do not catch `Exception` unless adding context and re-raising or returning an explicit error state.
- Do not use file existence alone as proof that a stage succeeded.
- Do not parse business results from the last stdout line.
- Do not mutate persistent state outside a transaction.
- Do not expose a feature in the UI before its capability test passes.
- Do not add a provider to more than one registry; there must be one registry.
- Do not allow AI and manual edits to use different mutation logic.
- Do not use arbitrary project filesystem paths supplied by the model or browser.
- Do not log credentials.
- Keep migrations forward-compatible and backed up.
- Maintain idempotency for retried tool commands and render requests.

---

# 9. Definition of Done

OpenEdit is considered stabilized only when all of the following are true:

- A fresh installation starts with one documented command.
- Project creation never returns a phantom/uninitialized project.
- Multi-file ingest is reliable, bounded, and recoverable.
- Assets preview correctly.
- Provider selection is consistent across registry, API, config, UI, and runtime.
- Every provider is accurately labeled as full agent, chat-only, unavailable, or hidden.
- Multi-turn context works for every provider that advertises it.
- Full agents can inspect assets and mutate the project through validated tools.
- Tool calls are never duplicated.
- Manual timeline editing and AI editing use the same graph service.
- The Edit Graph panel can edit and revert supported operations.
- Timeline duration and tracks are derived from the applied graph.
- Render jobs survive or recover cleanly after restart.
- Cancellation kills the entire process tree.
- WebSocket and HTTP remote access follow the same authentication policy.
- Corruption is visible and diagnosable, not converted to empty state.
- Python, Go, Rust, media integration, and browser test suites pass in CI.
- Root documentation matches the code users actually run.

---

# 10. Final Report Required From the Agent

After completing the work, produce `STABILIZATION_REPORT.md` containing:

1. Architecture chosen and deprecated paths.
2. Every fixed issue ID from this plan.
3. Files and schemas changed.
4. New migrations.
5. Provider capability matrix with evidence.
6. Test commands and exact pass counts.
7. Golden workflow result.
8. Remaining known limitations.
9. Security assumptions for local and remote use.
10. Upgrade and rollback instructions.

Do not report a feature as fixed merely because the code path was changed. Include the regression test or end-to-end evidence that proves it.
