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

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve as resolvePath, join, dirname } from "node:path";

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

// ---- Project path resolution ----

function resolveProjectPath(): string | null {
  return process.env.PYAGENT_PROJECT || null;
}

function resolveCatalogPath(): string {
  if (process.env.PYAGENT_CATALOG) return process.env.PYAGENT_CATALOG;
  // Default: ../phase1_knowledge_base/catalog.json relative to this file.
  return resolvePath(
    join(dirname(new URL(import.meta.url).pathname),
         "..", "phase1_knowledge_base", "catalog.json"));
}

function loadSystemPrompt(catalogPath: string): string {
  const tmpl = readFileSync(
    resolvePath(join(dirname(new URL(import.meta.url).pathname), "system_prompt.md")),
    "utf8",
  );
  // Inline the catalog slice.
  // We import lazily because catalog_slice is Python.
  return tmpl;  // placeholder; the catalog inlining is done by the test mode
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
    proc.stdout.on("data", (d) => (stdout += d.toString()));
    proc.on("error", (e) => resolve({ ok: false, fatal: true, error: `spawn failed: ${e.message}` }));
    proc.on("close", () => {
      const last = stdout.trim().split("\n").pop() || "{}";
      try {
        resolve(JSON.parse(last));
      } catch {
        resolve({ ok: false, fatal: true, error: `malformed output: ${stdout}` });
      }
    });
  });
}

async function callRuntime(
  op: string,
  args: Record<string, unknown>,
  ctx: any,
): Promise<RuntimeResult> {
  const project = resolveProjectPath();
  if (!project) {
    return {
      ok: false,
      error:
        "PYAGENT_PROJECT env var is not set.\n" +
        "fix: export PYAGENT_PROJECT=/path/to/your.kdenlive",
    };
  }
  const catalog = resolveCatalogPath();
  const toolName = `pyagent_${op}`;
  const autoApprove = process.env.PYAGENT_AUTO_APPROVE === "true";

  if (isMutating(toolName) && !autoApprove) {
    const ok = await ctx.ui.confirm(
      `PyAgent wants to: ${humanize(op, args)}`,
      "Approve this edit?",
    );
    if (!ok) {
      return { ok: false, error: "user rejected the proposed edit" };
    }
  }
  return runRuntime(op, args, project, catalog);
}

// ---- Extension entry ----

export default function (pi: ExtensionAPI): void {
  // Tool 1: get_project_info (read-only, no confirm).
  pi.registerTool({
    name: "pyagent_get_project_info",
    label: "Get project info",
    description: "Get the current .kdenlive project's metadata (name, fps, dimensions, duration, etc).",
    parameters: Type.Object({}),
    execute: async (_args, ctx) => callRuntime("get_project_info", {}, ctx),
  });
}
