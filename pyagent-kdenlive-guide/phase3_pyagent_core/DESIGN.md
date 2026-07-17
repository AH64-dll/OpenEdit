# Phase 3 — Design Spec: pyagent as a pi extension

**Status:** design approved by user, 2026-07-17
**Depends on:** Phase 1 (`phase1_knowledge_base/`), Phase 2 (`phase2_project_engine/`)
**Unlocks:** Phase 4 (chat UI) and Phase 5 (sync/reload via D-Bus)
**Pinned decisions from brainstorming:**
- Model layer = pi (no provider code in pyagent)
- Tool implementations = one-shot Python subprocess per tool call
- Chat UI = pi in a separate terminal (cheap path, Phase 8 stretch is the embedded dock)

---

## 1. What this phase builds

A pi extension (`phase3_pyagent_core/extension.ts`) that registers 13 tools with pi. Each tool is a thin wrapper that shells out to `pyagent_runtime.py` (a Python CLI), which loads the project, runs one operation against Phase 2's `KdenliveFileBackend`, and emits a JSON result. No TypeScript compilation needed — pi loads `.ts` files via jiti at runtime.

**PyAgent has zero LLM code.** pi handles provider, model, api key, session, compaction, retry, streaming. pyagent is purely the bridge from pi to Phase 2.

## 2. Architecture

```
+-----------------------------------+
|  pi (existing CLI, user types     |
|  chat here)                       |
|  - provider, model, api key       |
|  - session, compaction, retry     |
|  - LLM stream, tool execution     |
+----------------+------------------+
                 |  pi's normal LLM tool-call protocol
                 v
+-----------------------------------+
|  pyagent extension (TypeScript,   |
|  one file, ~150 lines)            |
|  - registers 13 tools with pi     |
|  - reads PYAGENT_PROJECT env      |
|  - on tool call (mutating):       |
|      if !auto_approve:            |
|          ctx.ui.confirm()         |
|      spawn pyagent_runtime.py     |
|  - wraps JSON result for pi       |
+----------------+------------------+
                 |  python3 invocation
                 |  args: --op, --project, --catalog, --args-json
                 v
+-----------------------------------+
|  pyagent_runtime.py (Python)      |
|  - imports Phase 2's              |
|    KdenliveFileBackend            |
|  - loads project from --project   |
|  - runs ONE operation             |
|  - serializes result as JSON      |
|  - exits 0 on success, 1 on       |
|    validation error, 2 on fatal   |
+-----------------------------------+
                 |  uses
                 v
+-----------------------------------+
|  Phase 2: KdenliveFileBackend     |
|  (31 tests pass)                  |
+-----------------------------------+
```

## 3. The 13 tools

| # | Tool name (pi) | Backend method | Args JSON | Returns |
|---|---|---|---|---|
| 1 | `pyagent_get_project_info` | `get_project_info()` | `{}` | `ProjectInfo` dict |
| 2 | `pyagent_get_timeline_summary` | `get_timeline_summary()` | `{}` | `TimelineSummary` dict |
| 3 | `pyagent_import_media` | `import_media(paths)` | `{"paths": [str]}` | `[clip_id, ...]` |
| 4 | `pyagent_insert_clip` | `insert_clip(...)` | `{"track_index": int, "position_sec": float, "source_id": str, "source_in_sec"?: float, "source_out_sec"?: float}` | `clip_id` |
| 5 | `pyagent_append_clip` | `append_clip(...)` | `{"track_index": int, "source_id": str, "source_in_sec"?: float, "source_out_sec"?: float}` | `clip_id` |
| 6 | `pyagent_move_clip` | `move_clip(...)` | `{"clip_id": str, "new_track": int, "new_position_sec": float}` | `null` |
| 7 | `pyagent_trim_clip` | `trim_clip(...)` | `{"clip_id": str, "new_in_sec": float, "new_out_sec": float}` | `null` |
| 8 | `pyagent_delete_clip` | `delete_clip(...)` | `{"clip_id": str}` | `null` |
| 9 | `pyagent_add_transition` | `add_transition(...)` | `{"clip_a_id": str, "clip_b_id": str, "kind"?: str, "duration_sec"?: float}` | `transition_id` |
| 10 | `pyagent_apply_effect` | `apply_effect(...)` | `{"clip_id": str, "effect_id": str, "params"?: dict}` | `effect_id` |
| 11 | `pyagent_add_marker` | `add_marker(...)` | `{"position_sec": float, "label": str, "kind"?: str}` | `null` |
| 12 | `pyagent_save_project` | `save(path=None)` | `{"path"?: str}` | `null` |
| 13 | `pyagent_list_catalog` | (Phase 1 catalog) | `{"kind": "effects"\|"transitions"\|"generators", "filter"?: str}` | `[entry, ...]` |

Tools 1, 2, 13 are read-only — no `ctx.ui.confirm()` regardless of `auto_approve`.
Tools 3-11 are mutating.
Tool 12 (`save`) is now an explicit "force a save now" call but the runtime auto-saves after every mutating op, so it's effectively a no-op. It IS still considered mutating for `auto_approve` (you confirm before the save is triggered, even though one already happened).
The `?` suffix means "optional, defaults match the backend signature."

**Auto-save behavior:** The runtime calls `backend.save()` after every successful mutating op (3-12) so that subsequent tool calls in the same conversation see the change. This is required because each tool call is a fresh subprocess that loads the project from disk. Read-only ops (1, 2, 13) do not save.

## 4. TS↔Python contract (one tool call)

**Invocation (extension → Python):**

```bash
python3 -m pyagent_runtime <op-name> \
  --project /path/to/video.kdenlive \
  --catalog phase1_knowledge_base/catalog.json \
  --args-json '{"track_index":0,"position_sec":0.0,"source_id":"abc"}'
```

**Success (Python → extension, one JSON line on stdout):**

```json
{"ok": true, "result": "clip_xyz"}
```

**Validation error with fix hint (exit 1):**

```json
{"ok": false, "error": "out_sec (12.0) must be > in_sec (5.0)\nfix: set out_sec=5.1 (or any value > in_sec)"}
```

**Fatal error (exit 2):**

```json
{"ok": false, "error": "BackendError: project file not found at /path/to/video.kdenlive", "fatal": true}
```

The extension's wrapper:
- Exit 0 → returns the `result` field to pi (as the tool's return value)
- Exit 1 → returns the `error` field to pi as a tool error (pi will feed this back to the LLM as a "the tool said:" message — the LLM uses the `fix:` line to self-correct)
- Exit 2 → returns the `error` field AND logs to stderr; pi sees a fatal tool error

## 5. Auto-approve gate (propose-then-apply)

The extension reads `PYAGENT_AUTO_APPROVE` env var (default `false`).

When `false`, before calling any mutating tool (3-12), the extension calls `ctx.ui.confirm()`:

```typescript
const ok = await ctx.ui.confirm(
  "PyAgent wants to: " + humanReadableSummary(toolName, args),
  "Approve this edit?"
);
if (!ok) return { ok: false, error: "user rejected the proposed edit" };
```

`ctx.ui.confirm` works in pi's TUI mode natively, and via the `extension_ui_request` / `extension_ui_response` sub-protocol in RPC mode (Phase 4 will use this). The `humanReadableSummary` function maps `(toolName, args)` to a one-line human description like "insert_clip(track=0, pos=0, src=abc)" or "apply_effect(clip=clip_xyz, effect=brightness, level=0.5)".

When `true`, the confirm step is skipped.

## 6. System prompt composition

The extension registers an `--append-system-prompt` block via pi's mechanism. Three sub-blocks, in order:

### 6.1 Identity block (~3 lines)
```
You are PyAgent, a video-editing assistant. You edit .kdenlive project files
via the pyagent_* tools. The user has Kdenlive open; your edits show up after
they reload the project (or automatically if Phase 5's D-Bus bridge is wired).
```

### 6.2 Hard rules block (~6 lines, adapted from prompts/edl_writer.md and the spec)
```
- Never shell out to ffmpeg/melt directly; always use the pyagent_* tools.
- Never edit the .kdenlive file by hand or via pi's built-in edit/write tools.
- Every effect_id and transition kind must come from the catalog slice below.
  If the user asks for something not in the catalog, say so; do not invent.
- Before planning any edit, call pyagent_get_timeline_summary() to see the
  current state. Don't trust your memory from earlier turns — state may have
  changed.
- Before calling any mutating tool, briefly state what you're about to do.
  The user will be asked to confirm (unless auto_approve is on).
- If a tool returns a fix:-hinted error, fix the call and retry. After 3
  failed attempts on the same operation, stop and tell the user.
```

### 6.3 Catalog slice (~50-80 KB)
One line per catalog entry:
```
{tag} | {kdenlive_id} | {name} | {description}
```
Built once at extension-load time by `catalog_slice.py` from Phase 1's `catalog.json`. Only effects/transitions/generators with a `name` and a `description` are included.

The LLM can call `pyagent_list_catalog` (tool #13) to get full param details for a specific entry on demand, or to look up effects/transitions by name when the user asks for something not already named.

## 7. File layout

```
phase3_pyagent_core/
├── extension.ts            # pi extension entry point (~150 lines)
├── runtime.py              # pyagent_runtime.py — one-operation-per-invocation shim
├── catalog_slice.py        # builds the filtered catalog slice
├── system_prompt.md        # identity + hard rules blocks (versioned, reviewable)
├── __init__.py             # python package init, exposes pyagent_runtime entry
├── __main__.py             # `python3 -m pyagent_runtime <op> ...`
├── pyproject.toml          # so the runtime is installable as a CLI
├── README.md
├── test_runtime.py         # unit tests for runtime.py (no pi, no LLM)
├── test_extension.py       # tests the extension's pi-tool wrappers (stubbed SDK)
├── test_integration.py     # spawns `pi --mode rpc` e2e (skipped if no provider)
└── tests/
    └── fixtures/
        └── demo.kdenlive   # small real .kdenlive for tests
```

## 8. The runtime in more detail

`pyagent_runtime.py` is a tiny CLI dispatcher. Pseudocode:

```python
def main():
    op = sys.argv[1]                              # e.g. "insert_clip"
    args = json.loads(get_arg("--args-json"))     # {"track_index": 0, ...}
    project_path = get_arg("--project")
    catalog_path = get_arg("--catalog")

    backend = KdenliveFileBackend(
        project_path=project_path,
        catalog=Catalog.from_json(catalog_path),
    )

    try:
        method = getattr(backend, op)
        result = method(**args)
        emit({"ok": True, "result": _to_jsonable(result)})
        sys.exit(0)
    except ValidationError as e:
        emit({"ok": False, "error": str(e)})      # includes `fix:` line
        sys.exit(1)
    except BackendError as e:
        emit({"ok": False, "error": f"BackendError: {e}", "fatal": True})
        sys.exit(2)
    except Exception as e:
        emit({"ok": False, "error": f"Unexpected: {e}", "fatal": True})
        sys.exit(2)
```

`_to_jsonable` handles the dataclasses → dict conversion for `ProjectInfo`, `TimelineSummary`, etc.

Per-process cost: ~150ms Python startup + ~50ms lxml project load + ~50ms lxml project save (mutating ops only) = ~250ms for mutating ops, ~200ms for read-only. Fine for the conversational pace (a turn with 3-5 tool calls takes ~1-2s total). Optimization (long-running subprocess) is deferred to a future phase if it actually matters.

**Why auto-save:** The runtime is a per-call subprocess that loads the project from disk on entry. Without auto-save, mutating ops would not persist to the next call (which loads the project again, fresh). Auto-saving after every mutating op makes the tool palette's chained calls (e.g., "import → append → add_transition") work as a single coherent edit. The `save` op is kept as an explicit call (idempotent — re-saves), primarily so the LLM can signal "I'm done editing" to the user.

## 9. The extension in more detail

`extension.ts` is a pi extension that registers 13 tools via `pi.registerTool()`. Skeleton:

```typescript
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { spawn } from "node:child_process";

const MUTATING = new Set([
  "pyagent_import_media", "pyagent_insert_clip", "pyagent_append_clip",
  "pyagent_move_clip", "pyagent_trim_clip", "pyagent_delete_clip",
  "pyagent_add_transition", "pyagent_apply_effect", "pyagent_add_marker",
  "pyagent_save_project",
]);

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "pyagent_get_project_info",
    label: "Get project info",
    description: "Get the current project's metadata (name, fps, duration, etc).",
    parameters: Type.Object({}),
    execute: async (_args, ctx) => callRuntime("get_project_info", {}, ctx),
  });

  // ... 12 more, same shape ...

  // pyagent_save_project
  pi.registerTool({
    name: "pyagent_save_project",
    label: "Save project",
    description: "Save the .kdenlive file. Writes to disk; the user can then reload in Kdenlive.",
    parameters: Type.Object({
      path: Type.Optional(Type.String()),
    }),
    execute: async (args, ctx) => callRuntime("save", args, ctx),
  });
}

async function callRuntime(op: string, args: any, ctx: any): Promise<any> {
  const project = process.env.PYAGENT_PROJECT;
  const catalog = process.env.PYAGENT_CATALOG
    || `${process.env.HOME}/apps/mlt-pipeline/pyagent-kdenlive-guide/phase1_knowledge_base/catalog.json`;
  if (!project) {
    return { ok: false, error: "PYAGENT_PROJECT env var is not set.\nfix: export PYAGENT_PROJECT=/path/to/video.kdenlive" };
  }
  const isMutating = MUTATING.has(`pyagent_${op}`) || op === "save";
  const autoApprove = process.env.PYAGENT_AUTO_APPROVE === "true";

  if (isMutating && !autoApprove) {
    const ok = await ctx.ui.confirm(
      `PyAgent wants to: ${humanize(op, args)}`,
      "Approve this edit?"
    );
    if (!ok) return { ok: false, error: "user rejected the proposed edit" };
  }
  return runRuntime(op, args, project, catalog);
}

function runRuntime(op: string, args: any, project: string, catalog: string): Promise<any> {
  return new Promise((resolve) => {
    const proc = spawn("python3", [
      "-m", "pyagent_runtime", op,
      "--project", project,
      "--catalog", catalog,
      "--args-json", JSON.stringify(args),
    ]);
    let stdout = "";
    proc.stdout.on("data", (d) => stdout += d);
    proc.on("close", (_code) => {
      try {
        const last = stdout.trim().split("\n").pop() || "{}";
        resolve(JSON.parse(last));
      } catch (e) {
        resolve({ ok: false, error: `malformed runtime output: ${stdout}`, fatal: true });
      }
    });
  });
}

function humanize(op: string, args: any): string {
  // Map (op, args) to a one-line human description.
  // Examples:
  //   ("insert_clip", {track_index:0, position_sec:0, source_id:"abc"})
  //     -> "insert_clip(track=0, pos=0.0s, src=abc)"
  //   ("apply_effect", {clip_id:"xyz", effect_id:"brightness", params:{level:0.5}})
  //     -> "apply_effect(clip=xyz, effect=brightness, params={level:0.5})"
  const summary = Object.entries(args)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
  return `${op}(${summary})`;
}
```

## 10. Install + run

```bash
# one-time, from the pyagent-kdenlive-guide/ directory
make install    # does both: ln -s ./phase3_pyagent_core ~/.pi/agent/extensions/pyagent
                #           && pip install -e ./phase3_pyagent_core

# day-to-day
export PYAGENT_PROJECT=/path/to/video.kdenlive   # or set in shell rc
export PYAGENT_AUTO_APPROVE=false                # safe default
pi    # start pi normally; the pyagent_* tools appear in the tool palette
```

Two install mechanisms:
- **Extension:** A symlink from `~/.pi/agent/extensions/pyagent` → `./phase3_pyagent_core/` (pi auto-discovers this directory at startup). No compilation; pi loads the `.ts` via jiti.
- **Runtime:** `pip install -e .` makes `python3 -m pyagent_runtime` importable from anywhere, so the extension's `subprocess` call works regardless of cwd.

Day-to-day UX: terminal 1 has Kdenlive open, terminal 2 has `pi` running. User types chat in pi, pi calls pyagent tools, the .kdenlive file is edited, the user reloads in Kdenlive (or Phase 5 wires auto-reload via D-Bus).

## 11. Tests + acceptance criteria

**`test_runtime.py`** — 30+ unit tests, no pi, no LLM. Each test:
1. Loads a fixture `.kdenlive` (a small, real one)
2. Calls `pyagent_runtime.py <op> --project fixture.kdenlive --args-json '{...}'` via subprocess
3. Asserts the JSON output and/or that the saved file has the expected structural change

This is the bulk of confidence. No flakiness, no provider required.

**`test_extension.py`** — 10+ tests, written in Python against the JSONL contract:
- Spawns the extension as a subprocess in a "test mode" that exposes its dispatch logic over JSONL (the extension gains a tiny `__test__` mode that returns the list of registered tools and runs synthetic tool calls)
- Verifies the extension registers exactly 13 tools
- Verifies the extension's `callRuntime` shim maps args correctly
- Verifies that when `PYAGENT_AUTO_APPROVE=false`, `ctx.ui.confirm` is called for mutating ops
- Verifies that when `ctx.ui.confirm` returns false, the tool returns `user rejected` without spawning Python
- Verifies the extension does NOT cache `get_timeline_summary` (verifiable by checking it spawns a fresh subprocess each time)

(We do not write `test_extension.ts` because pi's extension API is a Node.js module — testing it from Python via JSONL is simpler and matches how Phase 4 will exercise the extension. The unit tests for the *Python* runtime cover the data-handling side; the JSONL tests cover the *bridge* side.)

**`test_integration.py`** — guarded by `if not has_provider(): skipUnittest()`:
- Detects a provider via env vars (`OPENAI_API_KEY`, `GEMINI_API_KEY`, etc., same list pi uses)
- Spawns `pi --mode rpc --no-session` in a subprocess
- Drives a 2-turn conversation over JSONL
- Asserts: (a) LLM chains `pyagent_import_media` → `pyagent_append_clip` × 2 → `pyagent_add_transition` for "add these two clips with a crossfade"
- Asserts: (b) a deliberately invalid `pyagent_trim_clip` (e.g., 50s on a 10s clip) triggers the `fix:` retry path
- Asserts: (c) `pyagent_get_timeline_summary` is called once per turn, not cached

If no provider is configured, this test is skipped with a clear "set OPENAI_API_KEY to enable" message.

**Acceptance criteria** (the gate for "Phase 3 is done"):

- ✅ 13 tools registered with pi when the extension is installed (verified by `pi list` showing them and by `test_extension`).
- ✅ `piagent_get_project_info` returns correct `ProjectInfo` from a real .kdenlive (test).
- ✅ `pyagent_get_timeline_summary` returns correct `TimelineSummary` (test).
- ✅ `pyagent_import_media` + `pyagent_append_clip` × 2 + `pyagent_add_transition` produces a valid .kdenlive that opens in Kdenlive without "Untitled" and renders via melt (test).
- ✅ `pyagent_apply_effect` with an invalid `effect_id` returns a `fix:`-hinted error that the LLM can use to self-correct (test against the runtime; integration test against the LLM only if a provider is configured).
- ✅ `pyagent_get_timeline_summary` is called fresh per turn (verified by test that the extension does NOT cache — the runtime is always respawned).
- ✅ `auto_approve=false` (default) → `ctx.ui.confirm` fires for every mutating tool (3-12); not for read-only tools (1, 2, 13) (test via JSONL).
- ✅ `auto_approve=true` → no confirm for any tool (test).
- ✅ 30+ runtime unit tests pass, no pi or model needed (run with `python3 -m unittest test_runtime`).
- ✅ Integration test passes if a provider is configured; cleanly skipped otherwise.

## 12. Explicit non-goals (per the spec)

- No chat UI work — pi is the UI.
- No D-Bus backend — Phase 7 was cancelled; Phase 5 will use upstream Kdenlive's D-Bus for *sync/reload*, not for the tool implementations.
- No Phase 6 render/QC tools — those are a future phase.
- No embedded dock widget — Phase 8 stretch.
- No model code in this repo — pi is the model layer.

## 13. Cost / complexity budget

- `extension.ts` ~150 lines
- `runtime.py` ~50 lines
- `catalog_slice.py` ~30 lines
- `system_prompt.md` ~20 lines
- `test_runtime.py` ~400 lines (30+ tests)
- `test_extension.py` ~200 lines (10+ tests)
- `test_integration.py` ~150 lines (skipped without provider)

Total: ~1000 lines. One new language (TypeScript) but only for the bridge, not for the brain. No compile step — pi loads `.ts` via jiti at runtime. No new global deps beyond what pi already requires.

## 14. Open risks

- **Process startup is slow.** ~200ms per call. Acceptable for v1; revisit if it actually matters.
- **pi's extension API may evolve.** pi 0.80.2 is what's installed; the extension API is documented but could change. Mitigation: pin to a known-working pi version in the README, document the version used.
- **System prompt token cost.** ~50-80 KB for the catalog slice is large for small context models. Mitigation: catalog_slice can be filtered further (e.g., only effects with "common" tags) for small-model mode; a follow-up if needed.
- **No provider configured locally.** The integration test is skipped if no `OPENAI_API_KEY` / `GEMINI_API_KEY` / etc. is set. The 30+ runtime tests cover most confidence; the integration test is a smoke test for the LLM↔tool loop when a provider IS available.
