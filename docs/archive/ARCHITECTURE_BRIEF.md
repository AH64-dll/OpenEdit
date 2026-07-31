# Open Edit — Full Technical Architecture Brief

## 1. Elevator Pitch

AI-native video editor. Core: append-only edit graph (SQLite) stores typed operations
(AddClipOp, TrimClipOp, AddHtmlOverlayOp, etc.) as Pydantic models. A stack of
~24 op types forms a DAG. `derive_timeline()` replays ops to produce a
`Timeline` (tracks + clips + effects + overlays). Render via MLT (proxy/final)
or Chromium compositing (overlays). Frontend: vanilla JS ES modules, no bundler.
LLM: multi-provider (pi CLI via opencode-go, Anthropic SDK, OpenAI SDK).

## 2. Directory Layout

```
open_edit/
├── cli.py                   # CLI entry point (init, list, summary, render, serve, free-form)
├── ir/                      # Intermediate Representation
│   ├── types.py             # 24 Op types, Clip, Track, Effect, HtmlOverlay, Timeline, Asset, Project
│   ├── api.py               # IR class (26 methods: add_clip, trim_clip, ...)
│   ├── apply.py             # apply_operation() + derive_timeline()
│   ├── validate.py          # Reference validation for ops
│   ├── commutativity.py     # can_swap() for commuting ops
│   └── catalog/             # 12 YAML effect definitions
├── storage/                 # SQLite storage
│   ├── edit_graph.py        # EditGraphStore (append, load_all, update_status, reorder)
│   ├── assets.py            # Content-addressable asset store
│   ├── notes.py             # ReviewNotes + archived notes
│   ├── job_lock.py          # Single-slot job lock (partial unique index)
│   ├── render_snapshots.py  # Render version history
│   ├── config.py            # Project config TOML
│   ├── schema.sql           # DDL for project_meta, edits, jobs tables
│   └── transcription.py     # Optional faster-whisper integration
├── agent/                   # Agent runtime
│   ├── tools/               # 14 tool wrappers (list_assets, add_marker, run_python, ...)
│   ├── sandbox_bridge.py    # Rust bwrap+seccomp sandbox orchestrator (862 lines)
│   ├── libs.py              # Sandbox header parser (# ir_api_version: ...)
│   ├── exceptions.py        # FreeFormResult, RenderResult, SandboxError
│   └── skills/              # 4 skill modules (music_selector, sfx_placer, silence_cutter, motion_graphics)
├── serve/                   # FastAPI server + agent loop
│   ├── app.py               # FastAPI application
│   ├── agent.py             # Agent loop (1474 lines), system prompt, history, turn management
│   ├── llm.py               # LLM abstraction (pi, Anthropic, OpenAI, opencode) — 1025 lines
│   ├── cli_adapter.py       # CLI adapter (pi, opencode, antigravity) — 251 lines
│   ├── context_budget.py    # Token counting + sliding window truncation
│   ├── cost.py              # Cost computation (pricing.json, pi session parsing)
│   ├── tool_schemas.py      # 4 pillar tool JSON schemas
│   ├── schema_validator.py  # Hand-rolled JSON Schema validation
│   ├── pillar_tools.py      # Dispatch functions for 4 pillar tools
│   ├── tool_executor.py     # Canonical tool execution
│   ├── pi_bridge.py         # Python bridge (subprocess entry point for pi extension)
│   ├── result_capper.py     # Oversized tool result truncation
│   ├── visual_verify.py     # Post-render frame sampling + verification
│   ├── html_overlay.py      # Chromium compositing for HTML overlays
│   ├── serve_env.py         # All env var loading
│   ├── projects.py          # Project CRUD
│   ├── pricing.json         # Per-model rate cards
│   ├── pi_extension/        # TypeScript extension for pi CLI
│   │   ├── extension.ts     # Tool registration + bridge invocation
│   │   └── package.json
│   └── static/              # Frontend (JS ES modules, no bundler)
│       ├── index.html       # 3-column layout shell
│       ├── style.css        # Dark NLE theme (1425 lines)
│       ├── app.js           # Entry point
│       └── js/              # state.js, dom.js, api.js, chat.js, ws.js, assets.js
├── render/                  # MLT render engine
│   ├── emitter.py           # MLT XML emitter
│   ├── orchestrator.py      # Render orchestrator
│   ├── ingest.py            # MLT XML parser
│   ├── profiles.py          # 1080p/720p profiles
│   ├── cache.py             # Render cache (canonical JSON hash)
│   └── validators.py        # MLT XML validators
├── qc/                      # Quality checks
│   ├── black_frames.py, silence.py, gate.py, thumbnail.py
├── style/                   # Style profile system (event-sourced taste events)
└── sandbox/                 # Rust bwrap+seccomp sandbox (main.rs, jail.rs, render_jail.rs)
```

## 3. Database Schema (SQLite, WAL mode, per-project)

### Tables

**project_meta** (KV store)
```
key   TEXT PRIMARY KEY
value TEXT NOT NULL
```

**edits** (operation log — the edit graph)
```
edit_id      TEXT PRIMARY KEY
parent_id    TEXT FK → edits(edit_id)
kind         TEXT NOT NULL
author       TEXT NOT NULL
timestamp    TEXT NOT NULL
status       TEXT NOT NULL CHECK ('applied', 'reverted', 'superseded')
sequence_num INTEGER NOT NULL
payload      TEXT NOT NULL        -- JSON-serialized op-specific fields
```
Indexes: idx_edits_sequence, idx_edits_parent, idx_edits_status

**jobs** (job lock for sandbox/render)
```
job_id       TEXT PRIMARY KEY
kind         TEXT NOT NULL
status       TEXT NOT NULL CHECK ('running', 'completed', 'failed')
started_at   TEXT NOT NULL
finished_at  TEXT
error        TEXT
```
Indexes: idx_jobs_status
Unique partial: idx_jobs_one_running WHERE status='running'

**notes** (review notes / corrections)
```
note_id        TEXT PRIMARY KEY
project_id     TEXT NOT NULL
anchor_type    TEXT CHECK ('timestamp', 'region', 'op')
anchor         TEXT NOT NULL        -- JSON
text           TEXT
source         TEXT CHECK ('typed','voice','region','agent','form_correction')
status         TEXT CHECK ('pending','processed','dismissed')
created_at     TEXT
processed_at   TEXT
commit_token   TEXT
resulting_op_ids TEXT DEFAULT '[]'
```

**notes_archive** (same columns)

**render_snapshots**
```
version_id      TEXT PRIMARY KEY
project_id      TEXT NOT NULL
edit_graph_hash TEXT NOT NULL
render_path     TEXT NOT NULL
created_at      TEXT NOT NULL
status          TEXT CHECK ('rendering','ready','failed')
label           TEXT DEFAULT ''
```

### Migration Strategy
- `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` — purely additive
- No formal migration system (schema.sql is a snapshot)
- `JobLock._ensure_schema()` adds the unique partial index at runtime

## 4. IR Types (24 Operation Subclasses)

All inherit from `Operation(BaseModel)`:
```
kind: str                          # override by subclass
edit_id: str = Field(default_factory=new_id)
parent_id: Optional[str] = None
author: Literal["ai", "user"]
timestamp: str = Field(default_factory=now_iso8601)
status: Literal["applied","reverted","superseded"] = "applied"
originating_note_id: Optional[str] = None
```

### The 24 ops (kind literal in parens):

1. **AddClipOp** ("add_clip") — asset_hash, track_id, track_kind, position_sec, in_point_sec, out_point_sec?, clip_id
2. **RemoveClipOp** ("remove_clip") — clip_id
3. **MoveClipOp** ("move_clip") — clip_id, new_track_id, new_position_sec
4. **TrimClipOp** ("trim_clip") — clip_id, new_in_point_sec, new_out_point_sec
5. **AddTransitionOp** ("add_transition") — clip_a_id, clip_b_id, transition_type (luma/dissolve/wipe/fade/cut), duration_sec
6. **RemoveTransitionOp** ("remove_transition") — transition_id
7. **SetTransitionPropertyOp** ("set_transition_property") — transition_id, prop_name, value
8. **AddEffectOp** ("add_effect") — target_kind (clip/track), target_id, effect_type, params={}, effect_id
9. **RemoveEffectOp** ("remove_effect") — clip_id, effect_index
10. **SetEffectParamOp** ("set_effect_param") — clip_id, effect_index, param_name, value, effect_id=""
11. **SetKeyframeOp** ("set_keyframe") — effect_id, param, keyframes: list[(float,float,str)]
12. **RemoveKeyframeOp** ("remove_keyframe") — effect_id, param, frame
13. **SlipClipOp** ("slip_clip") — clip_id, delta_sec
14. **RippleDeleteClipOp** ("ripple_delete_clip") — clip_id
15. **ChangeClipSpeedOp** ("change_clip_speed") — clip_id, rate (gt=0)
16. **SplitClipOp** ("split_clip") — clip_id, at_sec, left_clip_id, right_clip_id
17. **ReplaceClipSourceOp** ("replace_clip_source") — clip_id, new_asset_hash
18. **SetClipSpeedRampOp** ("set_clip_speed_ramp") — clip_id, keyframes=[]
19. **SetAudioGainOp** ("set_audio_gain") — clip_id, gain_db, keyframe_op_id
20. **NormalizeAudioOp** ("normalize_audio") — target_kind (clip/track/project), target_id, target_dbfs=-16.0
21. **GroupEditsOp** ("group_edits") — edit_ids, label
22. **UngroupEditsOp** ("ungroup_edits") — label
23. **RawMltXmlOp** ("raw_mlt_xml") — xml, description (NO-OP at apply time)
24. **FreeFormCodeOp** ("free_form_code") — code, timeout_sec=30, mem_mb=512, label (NO-OP at apply time)
25. **AddHtmlOverlayOp** ("add_html_overlay") — template_path, variables={}, position_sec, duration_sec, overlay_id
26. **RemoveHtmlOverlayOp** ("remove_html_overlay") — overlay_id

### Derived types
- **Effect**: effect_id, effect_type, params, keyframes
- **Clip**: clip_id, asset_hash, track_id, track_kind, position_sec, in_point_sec, out_point_sec, effects=[]
- **Track**: track_id, kind (video/audio), clips=[], effects=[]
- **HtmlOverlay**: overlay_id (aliased as `id`), template_path, variables, position_sec, duration_sec
- **Timeline**: tracks=[], overlays=[], duration_sec=0.0
- **Asset**: asset_hash, original_path, stored_path, type (video/audio/image), duration_sec, fps, width, height, codec, has_audio, alignment=[], license="", attribution=""

### Effect Catalog (12 YAML files)
```
eq          → mlt_service="equalizer"       params: frequency, gain, bandwidth
luma        → mlt_service="luma"            params: softness, invert
panner      → mlt_service="panner"          params: start, end
contrast    → mlt_service="lumaliftgain"    params: value
dissolve    → mlt_service="dissolve"        no params
delay       → mlt_service="delay"           params: time
saturation  → mlt_service="saturation"      params: value
music_bed   → mlt_service="volume"          params: track_id, gain_db, t_start, t_end
volume      → mlt_service="volume"          params: gain (linear)
gain        → mlt_service="volume"          params: gain (dB)
sfx         → mlt_service="volume"          params: sfx_id, t_start, duration_s, gain_db
brightness  → mlt_service="brightness"      params: value
```

## 5. The 4 Pillar Tools (JSON Schemas)

### query_project
```json
{
  "name": "query_project",
  "input_schema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "query": {"type": "string", "enum": ["list_assets","get_pending_notes","get_style_profile","analyze_narrative","search_assets"]},
      "params": {"type": "object", "default": {}}
    },
    "required": ["query"]
  }
}
```

### edit_project
```json
{
  "name": "edit_project",
  "input_schema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "operation": {"type": "string", "description": "'add_marker'|'set_pinned_value'|'import_asset'|'apply_generated_ops'"},
      "params": {"type": "object", "default": {}},
      "generate": {"type": "string", "enum": ["sfx","music","visual","silence_cuts"]},
      "generate_params": {"type": "object", "default": {}}
    }
  }
}
```

### run_script
```json
{
  "name": "run_script",
  "input_schema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "code": {"type": "string"},
      "timeout_sec": {"type": "integer", "default": 30}
    },
    "required": ["code"]
  }
}
```

### trigger_render
```json
{
  "name": "trigger_render",
  "input_schema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "mode": {"type": "string", "enum": ["proxy","final","overlay"], "default": "proxy"}
    }
  }
}
```

## 6. Tool Dispatch Flow (Every Layer)

```
LLM → pi CLI (--session-id <sid>)
  → pi extension (extension.ts, TypeScript)
    → python -m open_edit.serve.pi_bridge --tool <name> --project <path> --args <json>
      → pi_bridge.main() → _run_agent_tool(tool_name, args, project_path)
        → validate_or_error() ← schema_validator.py (hand-rolled, no jsonschema lib)
        → pillar routing:
            query_project  → dispatch_query() → pillar_tools.py
            edit_project   → dispatch_edit() or dispatch_generate()
            (fallthrough)  → getattr(tools_mod, name) → fn(args, project_path)
        → result_capper.cap_tool_result()
        → JSON stdout
```

The TS extension:
1. Runs `python -m open_edit.serve.pi_bridge --list-tools` for names
2. Runs `python3 -c "from open_edit.serve.tool_schemas import TOOL_SCHEMAS; print(json.dumps(TOOL_SCHEMAS))"` for schemas
3. Builds TypeBox schemas from JSON Schema
4. Registers tools with pi's ExtensionAPI
5. On each execute: spawns the python bridge subprocess

## 7. Session & Cost System

### Session ID flow
1. Agent loop generates `conv_id = uuid4().hex`
2. `build_command()` passes `--session-id <conv_id>` to pi CLI
3. Pi creates session file at `~/.pi/agent/sessions/<encoded-cwd>/<timestamp>_<conv_id>.jsonl`
4. After pi exits, `_stream_pi()` calls `find_pi_session_file(conv_id, default_pi_sessions_dir())`
5. Reads usage delta from the session file

### Pi session file format (managed by pi CLI)
```
{"type":"session","version":3,"id":"<uuid>","timestamp":"<ISO>","cwd":"<abs-path>"}
{"type":"message","id":"...","parentId":"...","timestamp":"...",
 "message":{"role":"assistant","content":[...],"model":"...","usage":{...}}}
```

### Cost computation
- `cost.py` loads `pricing.json` (per-model rate cards)
- `compute_anthropic_cost(usage, model)` → (tokens, cost_usd)
- `compute_openai_cost(usage, model)` → (tokens, cost_usd)
- Pi cost from session file: sums `message.usage.totalTokens` + `message.usage.cost.total`
- `parse_pi_session_usage_delta(path, last_size)` — only scans appended bytes

### Conversation persistence
- `append_to_conversation(project_id, conv_id, message)` appends JSONL to `<project>/.open_edit/conversations/<conv_id>.jsonl`
- Messages are OpenAI-style: `{"role":"user"|"assistant"|"tool", "content": ...}`
- Every 50 appends: `_compact_jsonl()` calls `compact_history()` and atomically rewrites file
- `_make_slim_history()` in agent.py applies compact + prune images + truncate

## 8. Sandbox (Rust bwrap+seccomp)

The sandbox binary (`open-edit-sandbox`) lives at:
- `~/.local/bin/open-edit-sandbox`
- `sandbox/target/release/open-edit-sandbox`

### run_free_form flow
1. Validate workdir under `$OPEN_EDIT_PROJECTS_ROOT`
2. Auto-inject `# ir_api_version: 0.1; libs: {}` header if missing
3. Preflight: parse header, check version + libs against `allowed_libs.toml`
4. Acquire JobLock (single slot per project)
5. Create scratch dir: `<workdir>/.sandbox/run_<id>/`
6. Write `code.py` + `_bootstrap.py` (IR API + op models inlined)
7. Invoke Rust binary with args: `--scratch <path> --ops-output <path> --python-bin <sys.executable> --expected-py-version <py> --timeout <s> --mem <mb> --cpu <s> --json --source-ro <asset dirs> --project-meta <db_path>`
8. Rust binary creates bwrap jail with namespaces (user, pid, ipc, net) + seccomp + rlimits
9. Inside jail: run `python3 _bootstrap.py` which imports `code.py`
10. `code.py` has access to `ir` object (IR class + `_FlushingBuffer`)
11. Ops written to `ops.jsonl` by `_FlushingBuffer` (writes on first append, H10 optimization)
12. On completion: validate ops incrementally, return `FreeFormResult`
13. Cleanup: `shutil.rmtree` the scratch dir

## 9. Frontend Architecture (ES modules, no bundler)

```
serve/static/
├── index.html   # 3-column: assets | chat+timeline | renders
├── style.css    # Dark NLE theme, 1425 lines
├── app.js       # Entry point, imports all modules
└── js/
    ├── state.js     # Central state object + normalizers
    ├── dom.js       # $$, $, el(), showToast, showModal
    ├── api.js       # REST fetch wrappers
    ├── chat.js      # Chat UI (messages, status, cost badge, verify chip)
    ├── ws.js        # WebSocket (connect, reconnect, events)
    └── assets.js    # Asset list rendering
```

WebSocket handles: text_delta, tool_start, tool_result, render, error, done,
cost_update, verification_started, verification_result.

## 10. ALL Known Bugs, Workarounds, and Pain Points

### Critical
1. **Sandbox completely dead**: `bwrap: Creating new namespace failed: Resource temporarily unavailable`
   - Root cause: user namespace limit exhaustion (`max_user_namespaces` or `RLIMIT_NPROC`)
   - Every `run_script` call fails, including `print("hello")`
   - Workaround: direct SQLite writes using Pydantic models (bypasses safety)

2. **Tool validation layer rejects valid params**: `timeout_sec` in `run_script` rejected
   - The pi extension's TypeBox schema builder (`buildTypeBoxSchema`) may mangle integer defaults
   - `additionalProperties: false` on `edit_project` rejects `args` field as unexpected
   - No recursive/array validation — only top-level type checking
   - Old tool names bypass validation via `getattr` (removed from `TOOL_BY_NAME`) — unknown side effects

3. **Pi session format incompatibility** (Plan C regression, now fixed):
   - `--session <path>` expects pi-format JSONL (first line: `{"type":"session",...}`)
   - Our conversation JSONL has `{"role":"user","content":"..."}` — rejected
   - Fix: reverted to `--session-id`, but orphaned `.open_edit/conversations/*.jsonl` files can confuse pi's session lookup

### Architecture Problems

4. **Too many layers for tool dispatch**: FastAPI → agent.py → stream_chat → _stream_pi → pi subprocess → pi extension (TS) → pi_bridge.py (Python) → tool_executor → schema_validator → actual function. Every layer serializes/deserializes JSON, adding failure modes.

5. **No native subtitle operation**: No `AddSubtitleOp`. Text overlays go through `AddHtmlOverlayOp` → Chromium compositing (heavy). No OCR pipeline exists.

6. **Context budget wasted on debugging**: 80%+ of conversation history is tool call debugging/retries. The model burns tokens re-reading schemas and error messages.

7. **4-pillar abstraction adds noise**: The LLM must know both the pillar schema AND the underlying function signature. Simple operations (trim, add overlay) require 5-10 tool calls instead of 1-2.

8. **Two session store problem**: Pi manages its own session files (`~/.pi/agent/sessions/`). Our server manages separate conversation files (`.open_edit/conversations/`). These can diverge. Cost state is in a third file (`.open_edit/cost.json`).

### Infrastructure

9. **No formal database migration** — schema changes are purely additive via `IF NOT EXISTS`. No alembic, no version tracking.

10. **Rust sandbox binary resolution** — searched via allow-list of 3 paths. If not found, falls back to... actual fallback is missing for `run_sandboxed` (raises `FileNotFoundError`).

11. **MLT shared library loading** — `mlt_repository_init` fails to dlopen `libmltsox.so` (`libsox_ng.so.3` not found). This is a warning but may affect audio features.

12. **No Arabic/unicode testing** — The project path `/home/ah64/OpenEditProjects/خ` with Arabic characters may cause issues in path encoding in bwrap, CLI args, or SQLite.

## 11. Complete Env Var Reference (49 vars)

| Variable | Default | Purpose |
|----------|---------|---------|
| OPEN_EDIT_LLM_PROVIDER | anthropic | LLM provider selection |
| OPEN_EDIT_LLM_MODEL | per-provider | Model name |
| OPEN_EDIT_LLM_API_KEY | — | API key override |
| OPEN_EDIT_LLM_MAX_TOKENS | 4096 | Max output tokens |
| OPEN_EDIT_PI_BINARY | pi | Pi CLI binary path |
| OPEN_EDIT_PI_EXTENSION | <pkg>/extension.ts | Pi extension path |
| OPEN_EDIT_PI_PROVIDER | opencode-go | Pi provider name |
| OPEN_EDIT_PI_SESSIONS_DIR | ~/.pi/agent/sessions | Pi session dir for cost reading |
| OPEN_EDIT_AGENT_MAX_ITERATIONS | 10 | Max tool call loop iterations |
| OPEN_EDIT_CONTEXT_MAX_TOKENS | 32000 | Context budget ceiling |
| OPEN_EDIT_CONTEXT_RESERVE_TOKENS | 4000 | Reserve for system prompt |
| OPEN_EDIT_CONTEXT_MAX_STATE_CHARS | 10000 | Max state JSON in system prompt |
| OPEN_EDIT_PROJECT | — | Project path (set in subprocess env) |
| OPEN_EDIT_VERIFY_ENABLED | True | Visual verification on/off |
| OPEN_EDIT_VERIFY_FRAMES | 3 | Frame samples per render |
| OPEN_EDIT_VERIFY_MAX_RENDERS | 100 | Max renders kept |
| OPEN_EDIT_VERIFY_JPEG_QUALITY | 95 | Frame JPEG quality |
| OPEN_EDIT_VERIFY_TOTAL_TIMEOUT_SECONDS | 3600 | Verification timeout |
| OPEN_EDIT_VERIFY_MAX_IMAGE_BYTES | 100MB | Max image size for analysis |
| OPEN_EDIT_VERIFY_RENDER_MODE | proxy | Render mode for verification |
| OPEN_EDIT_VERIFY_ALLOW_NO_CHANGE_SKIP | True | Skip verify if no change |
| OPEN_EDIT_VERIFY_PERSIST_HISTORY | True | Store verification in conv history |
| OPEN_EDIT_HYPERFRAMES_BIN | — | Chromium compositing binary |
| OPEN_EDIT_HYPERFRAMES_TIMEOUT_SECONDS | 3600 | Chromium timeout |
| OPEN_EDIT_OVERLAY_TMPDIR | — | Overlay working directory |
| OPEN_EDIT_SERVE_HOST | 0.0.0.0 | Server bind host |
| OPEN_EDIT_SERVE_PORT | 8000 | Server bind port |
| OPEN_EDIT_PROJECTS_ROOT | — | Allowed project roots (os-pathsep separated) |
| OPEN_EDIT_PEXELS_API_KEY | — | Pexels stock media API key |
| OPEN_EDIT_FREESOUND_API_KEY | — | Freesound stock media API key |
| OPEN_EDIT_PYTHON | python3 | Python for bridge subprocess |
| OPEN_EDIT_SEARCH_CACHE_DIR | /tmp/... | Search results cache |
| PI_CODING_AGENT | true | Set by pi CLI |
| PI_CODING_AGENT_DIR | ~/.pi/agent | Pi config directory |
| PI_CODING_AGENT_SESSION_DIR | — | Pi session directory override |
| PI_OFFLINE | — | Pi offline mode |
| PI_TELEMETRY | — | Pi telemetry opt-out |

Plus standard keys: ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENCODE_API_KEY

## 12. Test Infrastructure

- **Framework**: pytest 9.1.1, asyncio mode=STRICT
- **Test count**: 869 tests, 5 skipped
- **117 test files** across: IR (8), Agent/Tools (8), Server (20), Storage (7), Render (8), QC (4), Skills (5), Style (5), Other (16)
- **Key test files**:
  - test_tools.py — 25 tests for individual tools
  - test_sandbox_bridge.py — ~30 tests (bootstrap, header, validation, render)
  - test_serve_pi_bridge.py — 20 tests (list tools, add_marker, search, import, render)
  - test_serve_agent.py — 9 tests (loop, tool error, persistence, triggers)
  - test_serve_cost.py — 12 tests (pricing, pi session parsing)
  - test_ir_types.py — Operation types testing
  - test_ir/test_apply.py — Apply layer tests

The mock pi scripts had to be updated for the --session → --session-id fix. They write
usage data to session files in OPEN_EDIT_PI_SESSIONS_DIR.

## 13. What I'd Prioritize for Rewrite

1. **Flatten tool dispatch**: LLM → single bridge → tool function. Remove pi extension, remove pi subprocess for tool calls (keep it as LLM provider only if needed).
2. **Replace bwrap sandbox**: Too unreliable. Either fix namespaces or provide a subprocess fallback for local dev.
3. **Add AddSubtitleOp to IR**: Native subtitle op with font, position, and timing. Skip Chromium compositing for subtitles.
4. **Kill 4-pillar abstraction**: One function per operation. Simple validation. No `additionalProperties: false` unless needed.
5. **Single session store**: Either own the pi session file format or have a separate simple store. Don't split between pi and project JSONL.
6. **Unified error handling**: Every layer should produce the same error shape. Currently errors get mangled through JSON serialization at every boundary.
7. **Reduce context waste**: Give the LLM direct IR functions rather than making it explore the codebase with bash/grep to understand tool signatures.
