// pyagent pi extension.
//
// Thin loader: imports the 19 tool definitions from Python (via
// runtime.list_tools()) and registers them with pi. All tool
// metadata (name, label, description, parameter schema, is_mutating,
// backend op) lives in phase3_pyagent_core/tools/*.py as ToolDef
// dataclasses. This file just wires them up.
//
// Environment variables:
//   PYAGENT_PROJECT      path to the .kdenlive file (required)
//   PYAGENT_AUTO_APPROVE "true" to skip the per-tool confirm prompt
//   PYAGENT_CATALOG      path to catalog.json (default: ../phase1_knowledge_base/catalog.json)
//   PYAGENT_LIVE         "1" to route mutating tools through Phase 5 D-Bus sync

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { readFileSync, realpathSync } from "node:fs";
import { resolve as resolvePath, join, dirname } from "node:path";

// When this extension is loaded via a symlink (the install path:
// `~/.pi/agent/extensions/pyagent.ts` -> `phase3_pyagent_core/extension.ts`),
// `import.meta.url` resolves to the *symlink* path, not the real file.
const REAL_FILE = realpathSync(new URL(import.meta.url).pathname);
const REAL_DIR = dirname(REAL_FILE);

// ---- Tool def loading (Python -> JSON -> TS) ----

interface ToolDef {
  name: string;
  label: string;
  description: string;
  op: string;             // backend op name, or "" for Phase 6 tools
  is_mutating: boolean;
  parameters_schema: Record<string, unknown>;
}

// Spawn Python to import the tool defs from phase3_pyagent_core.tools
// and return them as JSON. This keeps the source of truth in Python
// and avoids re-declaring the 19 tool schemas in TypeScript.
function loadToolDefs(): ToolDef[] {
  const out = execFileSync("python3", [
    "-c",
    "import json; "
    + "from phase3_pyagent_core.runtime import list_tools; "
    + "print(json.dumps(list_tools()))",
  ], { encoding: "utf8" });
  return JSON.parse(out);
}

const TOOL_DEFS: ToolDef[] = loadToolDefs();
const MUTATING_TOOL_NAMES: Set<string> = new Set(
  TOOL_DEFS.filter((d) => d.is_mutating).map((d) => d.name)
);

// ---- Project path resolution ----

function resolveProjectPath(): string | null {
  return process.env.PYAGENT_PROJECT || null;
}

function resolveCatalogPath(): string {
  if (process.env.PYAGENT_CATALOG) return process.env.PYAGENT_CATALOG;
  return resolvePath(join(REAL_DIR, "..", "phase1_knowledge_base", "catalog.json"));
}

function resolveLiveSyncDir(): string {
  return resolvePath(join(REAL_DIR, "..", "phase5_dbus_sync"));
}

function resolveRenderQcDir(): string {
  return resolvePath(join(REAL_DIR, "..", "phase6_render_qc"));
}

function liveSyncEnabled(): boolean {
  return process.env.PYAGENT_LIVE === "1";
}

// ---- Live sync (Phase 5 D-Bus) ----

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

// ---- System prompt loading ----

function loadSystemPrompt(catalogPath: string): string {
  const tmpl = readFileSync(
    resolvePath(join(REAL_DIR, "system_prompt.md")),
    "utf8",
  );
  const slice = execFileSync("python3", [
    "-c",
    "import json, sys; sys.path.insert(0, '.'); "
    + "from phase3_pyagent_core.catalog_slice import build_catalog_slice; "
    + "print(build_catalog_slice(" + JSON.stringify(catalogPath) + "))",
  ], { encoding: "utf8" });
  return tmpl.replace("{{CATALOG_SLICE}}", slice);
}

// ---- Runtime result -> AgentToolResult shim ----

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

  if (liveSyncEnabled() && MUTATING_TOOL_NAMES.has(toolName)) {
    const liveErr = liveApply(toolName, args);
    if (liveErr === null) {
      return toToolResult({ ok: true, mode: "live" });
    }
    ctx?.ui?.notify?.(`Live sync unavailable (${liveErr}); using file-mode.`, "warn");
  }

  if (MUTATING_TOOL_NAMES.has(toolName) && !autoApprove) {
    const summary = Object.entries(args)
      .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
      .join(", ");
    const ok = await ctx.ui.confirm(
      `PyAgent wants to: ${op}(${summary})`,
      "Approve this edit?",
    );
    if (!ok) {
      return toToolResult({ ok: false, error: "user rejected the proposed edit" });
    }
  }
  const res = await runRuntime(op, args, project, catalog);
  if (res.ok && MUTATING_TOOL_NAMES.has(toolName)) {
    await runRuntime("save", {}, project, catalog);
  }
  return toToolResult(res);
}

// ---- Per-tool Phase 6 dispatch (for the 6 render_qc tools) ----
//
// These are the tools whose `op` is "" — they call Phase 6 directly
// instead of going through the Python backend. We keep their specific
// CLI flag mappings here because Phase 6 has its own CLI conventions
// (different from the JSON-dict args the backend takes).

function phase6Handler(name: string): ((params: any) => any) | null {
  switch (name) {
    case "pyagent_render":
      return (params: any) => {
        const project = resolveProjectPath();
        if (!project) return { ok: false, error: "PYAGENT_PROJECT not set" };
        const args = ["--project", project, "--output", params.output, "--mode", params.mode];
        if (params.in_sec !== undefined) args.push("--in-sec", String(params.in_sec));
        if (params.out_sec !== undefined) args.push("--out-sec", String(params.out_sec));
        return callPhase6("render", args);
      };
    case "pyagent_get_thumbnail":
      return (params: any) => callPhase6("thumbnails", [
        "--video", params.video,
        "--timestamp-sec", String(params.timestamp_sec),
        "--output", params.output,
      ]);
    case "pyagent_get_qc_crop":
      return (params: any) => callPhase6("thumbnails", [
        "--video", params.video,
        "--timestamp-sec", String(params.timestamp_sec),
        "--region", JSON.stringify(params.region),
        "--output", params.output,
      ]);
    case "pyagent_list_black_frames":
      return (params: any) => callPhase6("black_frames", [
        "--video", params.video,
        "--in-sec", String(params.in_sec ?? 0),
        "--out-sec", String(params.out_sec ?? 0),
        "--threshold", String(params.threshold ?? 0.10),
        "--min-sec", String(params.min_sec ?? 0.5),
      ]);
    case "pyagent_list_silence":
      return (params: any) => callPhase6("audio", [
        "silence",
        "--video", params.video,
        "--in-sec", String(params.in_sec ?? 0),
        "--out-sec", String(params.out_sec ?? 0),
        "--threshold-db", String(params.threshold_db ?? -35),
        "--min-sec", String(params.min_sec ?? 1.0),
      ]);
    case "pyagent_get_audio_levels":
      return (params: any) => callPhase6("audio", [
        "levels",
        "--video", params.video,
        "--in-sec", String(params.in_sec ?? 0),
        "--out-sec", String(params.out_sec ?? 0),
      ]);
    default:
      return null;
  }
}

// ---- Extension entry ----

export default function (pi: ExtensionAPI): void {
  // System prompt with the inlined catalog slice.
  const snippet = loadSystemPrompt(resolveCatalogPath());
  if (typeof (pi as any).appendSystemPrompt === "function") {
    (pi as any).appendSystemPrompt(snippet);
  } else {
    // Fallback: expose via env so --append-system-prompt can pick it up.
    process.env.PYAGENT_SYSTEM_PROMPT_SNIPPET = snippet;
  }

  // Register each tool. Backend-routed tools (op != "") go through
  // callRuntime; render_qc tools (op == "") go through Phase 6.
  for (const def of TOOL_DEFS) {
    if (def.op !== "") {
      pi.registerTool({
        name: def.name,
        label: def.label,
        description: def.description,
        parameters: Type.Object(def.parameters_schema as any),
        execute: async (_id, params, _sig, _upd, ctx) =>
          callRuntime(def.op, params, ctx),
      });
    } else {
      const handler = phase6Handler(def.name);
      if (!handler) {
        throw new Error(`No Phase 6 handler for tool ${def.name}`);
      }
      pi.registerTool({
        name: def.name,
        label: def.label,
        description: def.description,
        parameters: Type.Object(def.parameters_schema as any),
        execute: async (_id, params) => handler(params),
      });
    }
  }
}
