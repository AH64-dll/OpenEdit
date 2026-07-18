// pyagent pi extension.
//
// Registers 13 tools that let the LLM edit .kdenlive project files via
// Phase 2's KdenliveFileBackend. Each tool spawns a short-lived Python
// subprocess that performs one backend op and emits a JSON result.
//
// Environment variables:
//   PYAGENT_PROJECT      path to the .kdenlive file (required)
//   PYAGENT_AUTO_APPROVE "true" to skip the per-tool confirm prompt
//   PYAGENT_CATALOG      path to catalog.json (default: ../phase1_knowledge_base/catalog.json)
//   PYAGENT_LIVE         "1" to route live-capable tools through Phase 5 D-Bus sync

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { spawn, execFileSync, spawnSync } from "node:child_process";
import { readFileSync, realpathSync } from "node:fs";
import { resolve as resolvePath, join, dirname } from "node:path";

// When this extension is loaded via a symlink (the install path:
// `~/.pi/agent/extensions/pyagent.ts` -> `phase3_pyagent_core/extension.ts`),
// `import.meta.url` resolves to the *symlink* path, not the real file. That
// makes `dirname(import.meta.url)` point at the symlink's parent, where
// `system_prompt.md` and the catalog do not exist. Resolve the real path
// before deriving any other file paths.
const REAL_FILE = realpathSync(new URL(import.meta.url).pathname);
const REAL_DIR = dirname(REAL_FILE);

// ---- Op name (pi) -> backend method (Python) ----

const MUTATING = new Set([
  "pyagent_import_media",
  "pyagent_insert_clip",
  "pyagent_append_clip",
  "pyagent_move_clip",
  "pyagent_trim_clip",
  "pyagent_delete_clip",
  "pyagent_add_transition",
  "pyagent_apply_effect",
  "pyagent_add_marker",
  "pyagent_save_project",
]);

function isMutating(toolName: string): boolean {
  return MUTATING.has(toolName);
}

// Live-capable tools: those that D-Bus can apply directly to a running
// Kdenlive instance (vs. file-only edits that always require a reload).
const LIVE_CAPABLE = new Set([
  "pyagent_import_media",
  "pyagent_append_clip",
  "pyagent_apply_effect",
]);

// ---- Project path resolution ----

function resolveProjectPath(): string | null {
  return process.env.PYAGENT_PROJECT || null;
}

function resolveCatalogPath(): string {
  if (process.env.PYAGENT_CATALOG) return process.env.PYAGENT_CATALOG;
  // Default: ../phase1_knowledge_base/catalog.json relative to this file.
  // Use REAL_DIR (not dirname(import.meta.url)) to handle symlinked installs.
  return resolvePath(join(REAL_DIR, "..", "phase1_knowledge_base", "catalog.json"));
}

function resolveLiveSyncDir(): string {
  return resolvePath(join(REAL_DIR, "..", "phase5_dbus_sync"));
}

function liveSyncEnabled(): boolean {
  return process.env.PYAGENT_LIVE === "1";
}

// Route a live-capable tool call through Phase 5's Python LiveSync, which
// (a) tries to apply the change in-place via D-Bus, (b) falls back to the
// Phase 3 file backend + notify-and-reload if Kdenlive is not responding.
//
// Returns null on success, or an error string if the live path could not be
// taken (caller should fall through to the file-mode path).
function liveApply(toolName: string, args: Record<string, unknown>): string | null {
  if (!liveSyncEnabled()) return "PYAGENT_LIVE not set";
  const project = resolveProjectPath();
  if (!project) return "PYAGENT_PROJECT not set";
  const liveDir = resolveLiveSyncDir();
  const payload = JSON.stringify({ tool: toolName, args, project });
  const r = spawnSync(
    "python3",
    ["-m", "phase5_dbus_sync", "apply"],
    {
      cwd: resolvePath(join(liveDir, "..")),
      input: payload,
      encoding: "utf8",
      timeout: 10_000,
    },
  );
  if (r.status !== 0) {
    return `live sync failed (status=${r.status}, stderr=${(r.stderr || "").slice(0, 200)})`;
  }
  return null;
}

// ---- Phase 6 render + QC ----

function resolveRenderQcDir(): string {
  return resolvePath(join(REAL_DIR, "..", "phase6_render_qc"));
}

// Call into the Phase 6 Python module. Args become CLI flags; the module
// writes JSON to stdout and exits 0 on success. Caller parses the result.
function callPhase6(module: string, args: string[]): any {
  const qcDir = resolveRenderQcDir();
  const r = spawnSync(
    "python3",
    ["-m", `phase6_render_qc.${module}`, ...args],
    {
      cwd: resolvePath(join(qcDir, "..")),
      encoding: "utf8",
      timeout: 600_000,  // 10 min upper bound; melt proxy renders in seconds
    },
  );
  if (r.status !== 0) {
    return toToolResult({
      ok: false,
      error: `phase6.${module} failed (status=${r.status}): ${(r.stderr || r.stdout || "").slice(0, 400)}`,
    });
  }
  try {
    return toToolResult({ ok: true, result: JSON.parse(r.stdout || "{}"), mode: "render-qc" as const });
  } catch (e: any) {
    return toToolResult({ ok: false, error: `phase6.${module} returned non-JSON: ${(r.stdout || "").slice(0, 200)}` });
  }
}

function loadSystemPrompt(catalogPath: string): string {
  const tmpl = readFileSync(
    resolvePath(join(REAL_DIR, "system_prompt.md")),
    "utf8",
  );
  // Build the slice by invoking catalog_slice via a small Python one-liner.
  // This avoids re-implementing the slice in TypeScript.
  const slice = execFileSync("python3", [
    "-c",
    "import json, sys; sys.path.insert(0, '.'); "
    + "from phase3_pyagent_core.catalog_slice import build_catalog_slice; "
    + "print(build_catalog_slice(" + JSON.stringify(catalogPath) + "))",
  ], { encoding: "utf8" });
  return tmpl.replace("{{CATALOG_SLICE}}", slice);
}

// ---- Human-readable summary for the confirm dialog ----

function humanize(op: string, args: Record<string, unknown>): string {
  const parts = Object.entries(args)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
  return parts ? `${op}(${parts})` : op;
}

// ---- Subprocess invocation ----

interface RuntimeResult {
  ok: boolean;
  result?: unknown;
  error?: string;
  fatal?: boolean;
  mode?: "live" | "file" | "render-qc";
}

// pi 0.80+ expects every tool's `execute` to return an `AgentToolResult`:
//   { content: (TextContent | ImageContent)[], details: T, ... }
// Our tools instead produce a plain `RuntimeResult` ({ ok, result, error }).
// Convert one to the other so the model actually receives the tool output
// (otherwise pi serializes the result as an empty `content: []` array and
// the LLM sees nothing).
function toToolResult(rr: RuntimeResult): any {
  let text: string;
  if (!rr.ok) {
    text = `error: ${rr.error ?? "unknown failure"}`;
  } else if (typeof rr.result === "string") {
    text = rr.result;
  } else {
    text = JSON.stringify(rr.result ?? {});
  }
  return {
    content: [{ type: "text", text }],
    details: rr.result ?? { ok: rr.ok, error: rr.error },
  };
}

function runRuntime(
  op: string,
  args: Record<string, unknown>,
  project: string,
  catalog: string,
): Promise<RuntimeResult> {
  return new Promise((resolve) => {
    const proc = spawn("python3", [
      "-m", "phase3_pyagent_core", op,
      "--project", project,
      "--catalog", catalog,
      "--args-json", JSON.stringify(args),
    ]);
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (d) => (stdout += d.toString()));
    proc.stderr.on("data", (d) => (stderr += d.toString()));
    proc.on("error", (e) => resolve({ ok: false, fatal: true, error: `spawn failed: ${e.message}` }));
     proc.on("close", () => {
       const last = stdout.trim().split("\n").pop() || "{}";
       try {
         const parsed = JSON.parse(last);
         if (!parsed.ok) {
           parsed.error = (parsed.error || "unknown failure") + ` | stderr: ${stderr.slice(0, 300)}`;
         }
         resolve(parsed);
       } catch {
         resolve({ ok: false, fatal: true, error: `malformed output: ${stdout} | stderr: ${stderr.slice(0, 300)}` });
       }
     });
  });
}

async function callRuntime(
  op: string,
  args: Record<string, unknown>,
  ctx: any,
): Promise<any> {
  const project = resolveProjectPath();
  if (!project) {
    return toToolResult({
      ok: false,
      error:
        "PYAGENT_PROJECT env var is not set.\n" +
        "fix: export PYAGENT_PROJECT=/path/to/your.kdenlive",
    });
  }
  const catalog = resolveCatalogPath();
  const toolName = `pyagent_${op}`;
  const autoApprove = process.env.PYAGENT_AUTO_APPROVE === "true";

  // In live mode, route EVERY mutating tool through LiveSync. Live-capable
  // tools (import/append/effect) push straight to the running Kdenlive via
  // D-Bus; the rest edit the file and LiveSync auto-reloads the open
  // project (cleanRestart) so the change shows in real time. Skipping this
  // for non-live-capable tools meant their edits only appeared after a
  // manual close/reopen.
  if (liveSyncEnabled() && isMutating(toolName)) {
    const liveErr = liveApply(toolName, args);
    if (liveErr === null) {
      // LiveSync.apply returns {mode:"live"} for D-Bus pushes and
      // {mode:"file"} (with an auto-reload already triggered) for the
      // file-mode path. Either way the edit is now visible in Kdenlive.
      return toToolResult({ ok: true, mode: "live" });
    }
    ctx?.ui?.notify?.(`Live sync unavailable (${liveErr}); using file-mode.`, "warn");
  }

  if (isMutating(toolName) && !autoApprove) {
    const ok = await ctx.ui.confirm(
      `PyAgent wants to: ${humanize(op, args)}`,
      "Approve this edit?",
    );
    if (!ok) {
      return toToolResult({ ok: false, error: "user rejected the proposed edit" });
    }
  }
  return toToolResult(await runRuntime(op, args, project, catalog));
}

// ---- Extension entry ----

export default function (pi: ExtensionAPI): void {
  // Build the system-prompt append with the inlined catalog slice.
  // pi's append-system-prompt flag accepts a string; we register it via
  // a flag-like hook. pi 0.80+ exposes pi.appendSystemPrompt(snippet).
  const snippet = loadSystemPrompt(resolveCatalogPath());
  if (typeof (pi as any).appendSystemPrompt === "function") {
    (pi as any).appendSystemPrompt(snippet);
  } else {
    // Fallback: set the env var so the user can pipe it via --append-system-prompt
    // at startup. (Most users will not hit this; the function is in pi 0.80+.)
    process.env.PYAGENT_SYSTEM_PROMPT_SNIPPET = snippet;
  }

  // Tool 1: get_project_info (read-only, no confirm).
  pi.registerTool({
    name: "pyagent_get_project_info",
    label: "Get project info",
    description: "Get the current .kdenlive project's metadata (name, fps, dimensions, duration, etc).",
    parameters: Type.Object({}),
    execute: async (_args, ctx) => callRuntime("get_project_info", {}, ctx),
  });

  // Tool 2: get_timeline_summary (read-only).
  pi.registerTool({
    name: "pyagent_get_timeline_summary",
    label: "Get timeline summary",
    description:
      "Get the current timeline: tracks, clips, transitions, markers. " +
      "Call this BEFORE planning any edit (per the system prompt rules).",
    parameters: Type.Object({}),
    execute: async (_args, ctx) => callRuntime("get_timeline_summary", {}, ctx),
  });

  // Tool 13: list_catalog (read-only).
  pi.registerTool({
    name: "pyagent_list_catalog",
    label: "List catalog",
    description:
      "Look up available effects, transitions, or generators from the catalog. " +
      "Use kind='effects'|'transitions'|'generators' and an optional filter substring.",
    parameters: Type.Object({
      kind: Type.String({ enum: ["effects", "transitions", "generators"] }),
      filter: Type.Optional(Type.String()),
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => callRuntime("list_catalog", params, ctx),
  });

  // Tool 3: import_media.
  pi.registerTool({
    name: "pyagent_import_media",
    label: "Import media",
    description: "Add media files to the project bin. Returns the new source ids.",
    parameters: Type.Object({
      paths: Type.Array(Type.String(), { minItems: 1 }),
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => callRuntime("import_media", params, ctx),
  });

  // Tool 4: insert_clip.
  pi.registerTool({
    name: "pyagent_insert_clip",
    label: "Insert clip",
    description:
      "Insert a clip from the bin onto the timeline at the given position. " +
      "Pass `source_id` as the bin source id (see get_timeline_summary()'s " +
      "source_id field, or a clip_id from that summary, or import_media()'s return).",
    parameters: Type.Object({
      track_index: Type.Integer({ minimum: 0 }),
      position_sec: Type.Number({ minimum: 0 }),
      source_id: Type.String(),
      source_in_sec: Type.Optional(Type.Number({ minimum: 0 })),
      source_out_sec: Type.Optional(Type.Number({ minimum: 0 })),
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => callRuntime("insert_clip", params, ctx),
  });

  // Tool 5: append_clip.
  pi.registerTool({
    name: "pyagent_append_clip",
    label: "Append clip",
    description:
      "Append a clip from the bin to the end of the given track. " +
      "Pass `source_id` as the bin source id: either the `source_id` " +
      "field from get_timeline_summary(), or a `clip_id` from that same " +
      "summary, or the id returned by import_media().",
    parameters: Type.Object({
      track_index: Type.Integer({ minimum: 0 }),
      source_id: Type.String(),
      source_in_sec: Type.Optional(Type.Number({ minimum: 0 })),
      source_out_sec: Type.Optional(Type.Number({ minimum: 0 })),
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => callRuntime("append_clip", params, ctx),
  });

  // Tool 6: move_clip.
  pi.registerTool({
    name: "pyagent_move_clip",
    label: "Move clip",
    description: "Move a clip to a different track and/or position.",
    parameters: Type.Object({
      clip_id: Type.String(),
      new_track: Type.Integer({ minimum: 0 }),
      new_position_sec: Type.Number({ minimum: 0 }),
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => callRuntime("move_clip", params, ctx),
  });

  // Tool 7: trim_clip.
  pi.registerTool({
    name: "pyagent_trim_clip",
    label: "Trim clip",
    description:
      "Trim a clip's in/out points. Both in_sec and out_sec are required " +
      "and must be within the source clip's range.",
    parameters: Type.Object({
      clip_id: Type.String(),
      new_in_sec: Type.Number({ minimum: 0 }),
      new_out_sec: Type.Number({ minimum: 0 }),
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => callRuntime("trim_clip", params, ctx),
  });

  // Tool 8: delete_clip.
  pi.registerTool({
    name: "pyagent_delete_clip",
    label: "Delete clip",
    description: "Remove a clip from the timeline.",
    parameters: Type.Object({
      clip_id: Type.String(),
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => callRuntime("delete_clip", params, ctx),
  });

  // Tool 9: add_transition.
  pi.registerTool({
    name: "pyagent_add_transition",
    label: "Add transition",
    description:
      "Add a transition between two adjacent clips on the same track. " +
      "kind must be a transition id from the catalog (e.g. 'dissolve', 'composite', 'wipe').",
    parameters: Type.Object({
      clip_a_id: Type.String(),
      clip_b_id: Type.String(),
      kind: Type.Optional(Type.String()),
      duration_sec: Type.Optional(Type.Number({ minimum: 0 })),
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => callRuntime("add_transition", params, ctx),
  });

  // Tool 10: apply_effect.
  pi.registerTool({
    name: "pyagent_apply_effect",
    label: "Apply effect",
    description:
      "Apply an effect to a clip. effect_id must come from the catalog " +
      "(use pyagent_list_catalog to look it up). params is {name: value}.",
    parameters: Type.Object({
      clip_id: Type.String(),
      effect_id: Type.String(),
      params: Type.Optional(Type.Record(Type.String(), Type.Unknown())),
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => callRuntime("apply_effect", params, ctx),
  });

  // Tool 11: add_marker.
  pi.registerTool({
    name: "pyagent_add_marker",
    label: "Add marker",
    description: "Add a marker (or guide/chapter) at the given position.",
    parameters: Type.Object({
      position_sec: Type.Number({ minimum: 0 }),
      label: Type.String(),
      kind: Type.Optional(Type.String({ enum: ["marker", "guide", "chapter"] })),
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => callRuntime("add_marker", params, ctx),
  });

  // Tool 12: save_project.
  pi.registerTool({
    name: "pyagent_save_project",
    label: "Save project",
    description: "Write the .kdenlive file to disk. Use this when you are done editing.",
    parameters: Type.Object({
      path: Type.Optional(Type.String()),
    }),
    execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => callRuntime("save", params, ctx),
  });

  // ---- Phase 6: render + QC tools ----
  // These do NOT mutate the project — they read it. Listed in the order
  // recommended by PHASE_6 §"The conversational QC loop": render first,
  // then cheap deterministic checks, then expensive visual / audio samples.

  // Tool 13: render (proxy or final).
  pi.registerTool({
    name: "pyagent_render",
    label: "Render project",
    description:
      "Render the .kdenlive project to an MP4. " +
      "mode='proxy' (640x360, fast) is the default for iteration; " +
      "mode='final' uses the project's own profile and is slow. " +
      "Optional in_sec/out_sec for a ranged render.",
    parameters: Type.Object({
      mode: Type.Union([Type.Literal("proxy"), Type.Literal("final")], { default: "proxy" }),
      output: Type.String({ description: "absolute path for the rendered MP4" }),
      in_sec: Type.Optional(Type.Number({ minimum: 0 })),
      out_sec: Type.Optional(Type.Number({ minimum: 0 })),
    }),
    execute: async (_toolCallId, params) => {
      const project = resolveProjectPath();
      if (!project) return { ok: false, error: "PYAGENT_PROJECT not set" };
      const args = ["--project", project, "--output", params.output, "--mode", params.mode];
      if (params.in_sec !== undefined) args.push("--in-sec", String(params.in_sec));
      if (params.out_sec !== undefined) args.push("--out-sec", String(params.out_sec));
      return callPhase6("render", args);
    },
  });

  // Tool 14: get_thumbnail.
  pi.registerTool({
    name: "pyagent_get_thumbnail",
    label: "Get thumbnail",
    description:
      "Extract a single JPEG frame at the given timestamp. " +
      "Output is capped at <=480px on the long edge, ~70 quality, <250KB. " +
      "Use this to visually verify a frame without pulling full-resolution data.",
    parameters: Type.Object({
      video: Type.String({ description: "path to the rendered video (from pyagent_render)" }),
      timestamp_sec: Type.Number({ minimum: 0 }),
      output: Type.String({ description: "absolute path for the output JPEG" }),
    }),
    execute: async (_toolCallId, params) => callPhase6("thumbnails", [
      "--video", params.video,
      "--timestamp-sec", String(params.timestamp_sec),
      "--output", params.output,
    ]),
  });

  // Tool 15: get_qc_crop.
  pi.registerTool({
    name: "pyagent_get_qc_crop",
    label: "Get QC crop",
    description:
      "Extract a small crop of the frame at the given timestamp. " +
      "region = {x, y, w, h} in source pixels. Same size/quality caps as get_thumbnail.",
    parameters: Type.Object({
      video: Type.String(),
      timestamp_sec: Type.Number({ minimum: 0 }),
      region: Type.Object({
        x: Type.Integer({ minimum: 0 }),
        y: Type.Integer({ minimum: 0 }),
        w: Type.Integer({ minimum: 1 }),
        h: Type.Integer({ minimum: 1 }),
      }),
      output: Type.String(),
    }),
    execute: async (_toolCallId, params) => callPhase6("thumbnails", [
      "--video", params.video,
      "--timestamp-sec", String(params.timestamp_sec),
      "--region", JSON.stringify(params.region),
      "--output", params.output,
    ]),
  });

  // Tool 16: list_black_frames.
  pi.registerTool({
    name: "pyagent_list_black_frames",
    label: "List black frames",
    description:
      "Return ranges where the average luma is below `threshold` (0..1) " +
      "for at least `min_sec` consecutive seconds. Cheap deterministic check; " +
      "use before pulling thumbnails.",
    parameters: Type.Object({
      video: Type.String(),
      in_sec: Type.Optional(Type.Number({ minimum: 0 })),
      out_sec: Type.Optional(Type.Number({ minimum: 0 })),
      threshold: Type.Optional(Type.Number({ minimum: 0, maximum: 1 })),
      min_sec: Type.Optional(Type.Number({ minimum: 0 })),
    }),
    execute: async (_toolCallId, params) => callPhase6("black_frames", [
      "--video", params.video,
      "--in-sec", String(params.in_sec ?? 0),
      "--out-sec", String(params.out_sec ?? 0),
      "--threshold", String(params.threshold ?? 0.10),
      "--min-sec", String(params.min_sec ?? 0.5),
    ]),
  });

  // Tool 17: list_silence.
  pi.registerTool({
    name: "pyagent_list_silence",
    label: "List silence",
    description:
      "Return ranges where audio falls below `threshold_db` dB for at least " +
      "`min_sec` consecutive seconds. Cheap deterministic check.",
    parameters: Type.Object({
      video: Type.String(),
      in_sec: Type.Optional(Type.Number({ minimum: 0 })),
      out_sec: Type.Optional(Type.Number({ minimum: 0 })),
      threshold_db: Type.Optional(Type.Number({ maximum: 0 })),
      min_sec: Type.Optional(Type.Number({ minimum: 0 })),
    }),
    execute: async (_toolCallId, params) => callPhase6("audio", [
      "silence",
      "--video", params.video,
      "--in-sec", String(params.in_sec ?? 0),
      "--out-sec", String(params.out_sec ?? 0),
      "--threshold-db", String(params.threshold_db ?? -35),
      "--min-sec", String(params.min_sec ?? 1.0),
    ]),
  });

  // Tool 18: get_audio_levels.
  pi.registerTool({
    name: "pyagent_get_audio_levels",
    label: "Get audio levels",
    description:
      "Return RMS and peak dB for the audio over the requested range. " +
      "Numeric only — no waveform image.",
    parameters: Type.Object({
      video: Type.String(),
      in_sec: Type.Optional(Type.Number({ minimum: 0 })),
      out_sec: Type.Optional(Type.Number({ minimum: 0 })),
    }),
    execute: async (_toolCallId, params) => callPhase6("audio", [
      "levels",
      "--video", params.video,
      "--in-sec", String(params.in_sec ?? 0),
      "--out-sec", String(params.out_sec ?? 0),
    ]),
  });
}
