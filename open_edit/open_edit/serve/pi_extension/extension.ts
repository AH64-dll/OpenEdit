// open_edit pi extension.
//
// Thin loader that imports the 11 tool definitions from
// ``open_edit.serve.tool_schemas`` (via a Python subprocess) and
// registers them with pi. All tool metadata (name, description,
// parameter schema) lives in Python. This file just wires them up.
//
// When pi loads this extension, every tool call dispatches to
// ``python -m open_edit.serve.pi_bridge --tool <name>`` which in
// turn calls the actual implementation in ``open_edit.agent.tools``.
//
// Environment variables:
//   OPEN_EDIT_PROJECT      path to the project folder (or project id).
//                          Required for tool invocations. Optional for
//                          tool registration.
//   OPEN_EDIT_PYTHON       Python interpreter to use for the bridge
//                          subprocess. Defaults to "python3".
//
// The extension is loaded by pi via:
//   pi --extension /path/to/open_edit/open_edit/serve/pi_extension/extension.ts ...

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { execFileSync, spawn } from "node:child_process";
import { realpathSync } from "node:fs";
import { resolve as resolvePath, dirname, join } from "node:path";

// Resolve the real path of THIS file (in case it's loaded via a symlink).
const REAL_FILE = realpathSync(new URL(import.meta.url).pathname);
const REAL_DIR = dirname(REAL_FILE);

// Path to the open_edit package root (one level up from open_edit/serve/pi_extension).
// e.g. .../open_edit/open_edit/serve/pi_extension/extension.ts
//   -> .../open_edit/open_edit/serve/pi_extension/
//   -> .../open_edit/open_edit/serve/
//   -> .../open_edit/open_edit/
const OPEN_EDIT_PKG = resolvePath(join(REAL_DIR, "..", ".."));

// ---- Tool def loading (Python -> JSON -> TS) ----

interface ToolDef {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;  // JSON Schema for the tool's params
}

function loadToolDefs(): ToolDef[] {
  const py = process.env.OPEN_EDIT_PYTHON || "python3";
  const out = execFileSync(
    py,
    ["-m", "open_edit.serve.pi_bridge", "--list-tools"],
    {
      cwd: OPEN_EDIT_PKG,
      encoding: "utf8",
      env: { ...process.env, PYTHONPATH: OPEN_EDIT_PKG + "/.." },
    },
  );
  const parsed = JSON.parse(out.trim());
  // --list-tools only returns the names; fetch the full schemas separately
  // by importing the tool_schemas module via a one-shot python invocation.
  const schemas = JSON.parse(
    execFileSync(
      py,
      [
        "-c",
        "import json; "
        + "from open_edit.serve.tool_schemas import TOOL_SCHEMAS; "
        + "print(json.dumps(TOOL_SCHEMAS))",
      ],
      {
        cwd: OPEN_EDIT_PKG,
        encoding: "utf8",
        env: { ...process.env, PYTHONPATH: OPEN_EDIT_PKG + "/.." },
      },
    ),
  );
  const byName: Record<string, any> = {};
  for (const s of schemas) byName[s.name] = s;
  return parsed.tools.map((name: string) => byName[name]);
}

// Build a TypeBox schema from a JSON Schema's properties+required.
// JSON Schema's `properties` is what Type.Object wants; `required`
// is a separate list. We wire them together.
function buildTypeBoxSchema(def: ToolDef) {
  const schema: any = def.input_schema || { type: "object", properties: {} };
  const properties = schema.properties || {};
  return Type.Object(properties, { additionalProperties: false });
}

// ---- Project path resolution ----

function resolveProjectPath(): string | null {
  return process.env.OPEN_EDIT_PROJECT || null;
}

// ---- Tool invocation (subprocess -> pi_bridge.py) ----

function runBridge(
  tool: string,
  args: Record<string, unknown>,
  project: string,
): Promise<{ ok: boolean; result?: unknown; error?: string; fatal?: boolean }> {
  return new Promise((resolve) => {
    const py = process.env.OPEN_EDIT_PYTHON || "python3";
    const proc = spawn(
      py,
      [
        "-m", "open_edit.serve.pi_bridge",
        "--tool", tool,
        "--project", project,
        "--args", JSON.stringify(args || {}),
      ],
      {
        cwd: OPEN_EDIT_PKG,
        env: { ...process.env, PYTHONPATH: OPEN_EDIT_PKG + "/.." },
      },
    );
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (d) => (stdout += d.toString()));
    proc.stderr.on("data", (d) => (stderr += d.toString()));
    proc.on("error", (e) =>
      resolve({ ok: false, fatal: true, error: `bridge spawn failed: ${e.message}` }),
    );
    proc.on("close", (code) => {
      // pi_bridge.py emits a single JSON object on stdout (success OR error).
      // We never use the process exit code to decide success — the bridge
      // returns 0 even on tool errors (so the TS layer sees a tool result,
      // not a process failure).
      const last = stdout.trim().split("\n").pop() || "{}";
      try {
        const parsed = JSON.parse(last);
        if (parsed.error) {
          resolve({ ok: false, error: parsed.error, result: parsed });
        } else {
          resolve({ ok: true, result: parsed });
        }
      } catch {
        resolve({
          ok: false,
          fatal: true,
          error: `malformed bridge output: ${stdout.slice(0, 300)} | stderr: ${stderr.slice(0, 300)} | exit=${code}`,
        });
      }
    });
  });
}

// ---- Tool result -> AgentToolResult shim ----
//
// pi 0.80+ expects every tool's `execute` to return an `AgentToolResult`:
//   { content: (TextContent | ImageContent)[], details: T, ... }
function toToolResult(rr: { ok: boolean; result?: unknown; error?: string }): any {
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

// ---- Extension entry ----

export default function (pi: ExtensionAPI): void {
  let toolDefs: ToolDef[];
  try {
    toolDefs = loadToolDefs();
  } catch (e: any) {
    throw new Error(`open_edit pi extension: failed to load tool defs: ${e.message}\n` +
      `Is OPEN_EDIT_PYTHON set? Is ${OPEN_EDIT_PKG} on PYTHONPATH?`);
  }

  for (const def of toolDefs) {
    pi.registerTool({
      name: def.name,
      label: def.name,
      description: def.description,
      parameters: buildTypeBoxSchema(def),
      execute: async (_id, params, _sig, _upd, _ctx) => {
        const project = resolveProjectPath();
        if (!project) {
          return toToolResult({
            ok: false,
            error:
              "OPEN_EDIT_PROJECT env var is not set.\n" +
              `fix: export OPEN_EDIT_PROJECT=/path/to/project (got cwd=${process.cwd()})`,
          });
        }
        const res = await runBridge(def.name, params || {}, project);
        return toToolResult(res);
      },
    });
  }
}
