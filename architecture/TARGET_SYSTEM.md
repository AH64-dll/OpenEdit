# Target System Architecture

## Decision

The Python server/UI (`open_edit/`) is the product surface.
The Go/MLT pipeline is a legacy path used for compilation/rendering through a deliberate adapter.
Do not maintain two unrelated project formats and two independent render orchestration systems.

## Architecture

```
Browser UI (React/TypeScript)
   |
FastAPI application / WebSocket gateway
   |
Application services
   |-- ProjectService      (transactional create, health, discovery)
   |-- AssetService        (ingest, CAS, preview, metadata, transcription)
   |-- EditGraphService    (IR ops, apply, derive timeline, optimistic concurrency)
   |-- AgentService        (LLM provider adapters, normalized event protocol, tool dispatch)
   |-- RenderService       (durable SQLite job records, concurrency limits, cancellation)
   |-- ReviewService       (notes, markers, review workflow)
   |
Canonical IR + SQLite stores
   |
Compiler/render backend
   |-- Go/MLT adapter where stable
   |-- Python components only where they add required functionality
```

## Canonical Project Layout

```
project/
  .open_edit/
    edit_graph.db           # Append-only IR op log
    notes.db                # Review notes
    config.toml             # LLM config (preserves all TOML sections)
    assets/                 # CAS asset store
    renders/                # Render job records and output
    remotion/               # Remotion compositions (src/, public/, out/)
    conversations/          # Agent conversation logs
    temp/                   # Temporary upload staging
    logs/                   # Structured server logs
```

## Motion Graphics Backends

Open Edit uses three complementary engines — do not collapse them:

| Backend | Role | When to use |
|---|---|---|
| **MLT / melt** | Multi-track timeline, audio, trims, transitions | All proxy/final A/V composites |
| **HyperFrames** (`AddHtmlOverlayOp`) | Simple HTML/CSS templates with `{{var}}` | Lower thirds, banners, captions |
| **Remotion** (`AddRemotionCompositionOp`) | React motion graphics, materialize → CAS → clip | Kinetic titles, charts, springs, code anim |
| **moviepy templates** | Legacy procedural fills via render sandbox | Quick beat fills when Remotion is overkill |

**Remotion contract:** compositions are declared in the edit graph and
**materialized to CAS media before emit**. Proxy/final then:

1. melt the talk/timeline **without** Remotion graphics tracks
2. burn Remotion CAS clips onto the melt output with **ffmpeg overlay**

MLT multitrack composite of opaque Remotion clips is not relied on (known
gap). Remotion is **not** routed through the HyperFrames `mode=overlay`
late-composite path.

**Failure policy:** if Remotion materialization or ffmpeg burn-in fails, the
render fails with a clear error. Do not silently omit the composition.

### Transcription (Whisper)

- Default model: `base` (fast). Override with `OPEN_EDIT_WHISPER_MODEL=small`.
- Default language: auto-detect. For Arabic talks set
  `OPEN_EDIT_WHISPER_LANGUAGE=ar`.
- `edit_project operation=ingest_local` accepts any readable absolute local
  path; symlinks are resolved and copied into the project CAS.

### Experimental limits (honest)

- Sandbox `run_script` needs bwrap/seccomp **or** `OPEN_EDIT_SANDBOX_BACKEND=dev`.
- Remotion CLI: prefer Node 24 (`OPEN_EDIT_NODE_BIN`); Node 26 ESM pitfalls.
- Go pipeline remains the repo's production renderer boundary.

## Provider Registry (Single Source of Truth)

Each provider has one entry with:

```
id, label, transport (sdk|cli), agent_mode (openedit_loop|external_loop|chat_only),
installed check, default model, auth strategy, tool/image/session support
```

All UI, config, dispatch derived from this registry.

### Provider Modes
- `openedit_loop`: OpenEdit calls model, executes tools locally (Anthropic, OpenAI)
- `external_loop`: Provider executes tools through verified bridge (Pi)
- `chat_only`: Provider cannot mutate project (OpenCode, Antigravity — unless bridge implemented)
- `hidden`: Not exposed (JCode — until implemented)

## Agent Tool Protocol

Every tool:
- Validates required params explicitly — returns friendly error with `expected_keys`
- Returns `retry: bool` on temporary failures (missing alignment, transcription in progress)
- Never raises raw KeyError or crashes
- Has documented params in the LLM-visible schema

## Event Protocol (Normalized)

```
turn_started | text_delta | tool_requested | tool_started |
tool_result | usage | render_created | warning | error | turn_finished
```

One terminal event per turn. Stable IDs for turn, tool, command, render.

## Security

- WebSocket: explicit auth before `accept()`, Origin validation for remote
- Tools: project-scoped only, sandbox enforced
- Paths: no arbitrary paths from model or browser
- Credentials: never logged, provider-specific key mapping
- Rate limits: per-IP, per-token, per-project

## Immutable Principles

1. One provider registry — all derived from it
2. Agent mode determines capability labeling in UI
3. Tool calls execute at most once
4. Every mutation is an IR op in the append-only graph
5. Timeline derived from applied graph, not raw assets
6. Render jobs survive server restart
7. Corruption is visible — never silently empty
8. Schema changes have versioned migrations
