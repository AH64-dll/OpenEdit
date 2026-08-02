#!/usr/bin/env node
/**
 * Phase-1 instrumentation bridge: same as open_edit/render/remotion_bridge.mjs
 * but forces --browser-executable to system Chrome because Remotion's
 * chrome-headless-shell download fails on this host.
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

function argValue(flag) {
  const i = process.argv.indexOf(flag);
  if (i < 0 || i + 1 >= process.argv.length) return null;
  return process.argv[i + 1];
}

function fail(message, extra = {}) {
  process.stdout.write(JSON.stringify({ ok: false, error: message, ...extra }) + "\n");
  process.exit(1);
}

const projectRoot = argValue("--project-root");
const entryPoint = argValue("--entry-point") || "src/index.ts";
const compositionId = argValue("--composition-id");
const propsFile = argValue("--props-file");
const output = argValue("--output");
const width = argValue("--width") || "1280";
const height = argValue("--height") || "720";
const fps = argValue("--fps") || "30";
const codec = argValue("--codec") || "h264";
const pixelFormat = argValue("--pixel-format");
const imageFormat = argValue("--image-format");
const proresProfile = argValue("--prores-profile");
const concurrency = argValue("--concurrency");
const chrome =
  process.env.OPEN_EDIT_CHROME_EXECUTABLE || "/usr/bin/google-chrome-stable";

if (!projectRoot || !compositionId || !output) {
  fail("missing required --project-root, --composition-id, or --output");
}

const absRoot = path.resolve(projectRoot);
const absEntry = path.resolve(absRoot, entryPoint);
const absOut = path.resolve(output);
if (!absEntry.startsWith(absRoot + path.sep) && absEntry !== absRoot) {
  fail("entry_point escapes project root", { entry_point: entryPoint });
}
if (!fs.existsSync(absEntry)) {
  fail("entry_point not found", { entry_point: absEntry });
}

if (propsFile) {
  const absProps = path.resolve(propsFile);
  if (!fs.existsSync(absProps)) {
    fail("props file not found", { props_file: absProps });
  }
  try {
    JSON.parse(fs.readFileSync(absProps, "utf8"));
  } catch (e) {
    fail("props file is not valid JSON");
  }
}

fs.mkdirSync(path.dirname(absOut), { recursive: true });

const remotionBinUnix = path.join(absRoot, "node_modules", ".bin", "remotion");
const remotionBin =
  process.env.OPEN_EDIT_REMOTION_CLI || remotionBinUnix;
const fallbackNpx = !fs.existsSync(remotionBin);

const cmd = fallbackNpx ? "npx" : remotionBin;
const extraArgs = [
  ...(pixelFormat ? [`--pixel-format=${pixelFormat}`] : []),
  ...(imageFormat ? [`--image-format=${imageFormat}`] : []),
  ...(proresProfile ? [`--prores-profile=${proresProfile}`] : []),
  ...(concurrency ? [`--concurrency=${concurrency}`] : []),
  `--browser-executable=${chrome}`,
];
const args = fallbackNpx
  ? [
      "--yes",
      "remotion",
      "render",
      entryPoint,
      compositionId,
      absOut,
      `--props=${propsFile || ""}`,
      `--width=${width}`,
      `--height=${height}`,
      `--fps=${fps}`,
      `--codec=${codec}`,
      ...extraArgs,
    ].filter((a) => a !== "--props=")
  : [
      "render",
      entryPoint,
      compositionId,
      absOut,
      ...(propsFile ? [`--props=${propsFile}`] : []),
      `--width=${width}`,
      `--height=${height}`,
      `--fps=${fps}`,
      `--codec=${codec}`,
      ...extraArgs,
    ];

const result = spawnSync(cmd, args, {
  cwd: absRoot,
  encoding: "utf8",
  env: process.env,
  maxBuffer: 32 * 1024 * 1024,
});

if (result.status !== 0) {
  fail("remotion render failed", {
    exit_code: result.status,
    stderr: (result.stderr || "").slice(-4000),
    stdout: (result.stdout || "").slice(-2000),
  });
}

if (!fs.existsSync(absOut) || fs.statSync(absOut).size === 0) {
  fail("remotion produced no output file");
}

process.stdout.write(
  JSON.stringify({
    ok: true,
    output_path: absOut,
    width: Number(width),
    height: Number(height),
    fps: Number(fps),
    codec,
    browser_executable: chrome,
    ...(proresProfile ? { prores_profile: proresProfile } : {}),
  }) + "\n"
);
