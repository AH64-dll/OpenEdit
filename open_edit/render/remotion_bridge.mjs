#!/usr/bin/env node
/**
 * Thin Remotion CLI bridge for Open Edit.
 *
 * Usage:
 *   node remotion_bridge.mjs \
 *     --project-root <dir> \
 *     --entry-point src/index.ts \
 *     --composition-id TitleCard \
 *     --props-file /tmp/props.json \
 *     --output /tmp/out.mp4 \
 *     --width 1280 --height 720 --fps 30 \
 *     [--codec h264|vp8|prores] \
 *     [--pixel-format ...] [--image-format ...] [--prores-profile ...]
 *
 * Prints one JSON object to stdout on success/failure.
 * Props are always read from a file (never interpolated into the shell).
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import {remotionRuntime} from './remotion_runtime.mjs';

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
const browserExecutable =
  argValue("--browser-executable") ||
  process.env.OPEN_EDIT_REMOTION_BROWSER ||
  process.env.REMOTION_BROWSER_EXECUTABLE ||
  null;

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

let propsJson = "{}";
if (propsFile) {
  const absProps = path.resolve(propsFile);
  if (!fs.existsSync(absProps)) {
    fail("props file not found", { props_file: absProps });
  }
  propsJson = fs.readFileSync(absProps, "utf8");
  try {
    JSON.parse(propsJson);
  } catch (e) {
    fail("props file is not valid JSON");
  }
}

fs.mkdirSync(path.dirname(absOut), { recursive: true });

const binName = process.platform === "win32" ? "remotion.cmd" : "remotion";
const remotionBin = process.env.OPEN_EDIT_REMOTION_CLI || [
  path.join(absRoot, 'node_modules', '.bin', binName),
  path.join(path.dirname(absRoot), 'node_modules', '.bin', binName),
  path.join(path.dirname(path.dirname(absRoot)), 'node_modules', '.bin', binName),
].find(candidate => fs.existsSync(candidate));
const cmd = remotionBin;
const extraArgs = [
  ...(pixelFormat ? [`--pixel-format=${pixelFormat}`] : []),
  ...(imageFormat ? [`--image-format=${imageFormat}`] : []),
  ...(proresProfile ? [`--prores-profile=${proresProfile}`] : []),
  ...(concurrency ? [`--concurrency=${concurrency}`] : []),
  ...(browserExecutable
    ? [`--browser-executable=${browserExecutable}`]
    : []),
];
const args = [
  'render', entryPoint, compositionId, absOut,
  ...(propsFile ? [`--props=${propsFile}`] : []),
  `--width=${width}`, `--height=${height}`, `--fps=${fps}`, `--codec=${codec}`, ...extraArgs,
];

if (remotionBin) {
const result = spawnSync(cmd, args, {
  cwd: absRoot,
  encoding: "utf8",
  env: process.env,
  maxBuffer: 32 * 1024 * 1024,
  shell: process.platform === "win32",
});

if (result.status !== 0) {
  fail("remotion render failed", {
    exit_code: result.status,
    stderr: (result.stderr || "").slice(-4000),
    stdout: (result.stdout || "").slice(-2000),
  });
}
} else {
  // A project without its own install uses the independent compatibility
  // package. Add its module directory to Webpack without changing the project.
  for (const method of ['log', 'info', 'warn', 'debug']) console[method] = (...values) => console.error(...values);
  try {
    const {bundle, selectComposition, renderMedia, webpackOverride} = remotionRuntime(absRoot);
    const serveUrl = await bundle({entryPoint: absEntry, webpackOverride, onProgress: () => {}});
    const inputProps = JSON.parse(propsJson);
    const composition = await selectComposition({serveUrl, id: compositionId, inputProps,
      ...(browserExecutable ? {browserExecutable} : {}), logLevel: 'error'});
    await renderMedia({serveUrl, composition: {...composition, width: Number(width), height: Number(height), fps: Number(fps)},
      inputProps, outputLocation: absOut, codec,
      ...(pixelFormat ? {pixelFormat} : {}), ...(imageFormat ? {imageFormat} : {}),
      ...(proresProfile ? {proResProfile: proresProfile} : {}),
      ...(concurrency ? {concurrency: Number(concurrency)} : {}),
      ...(browserExecutable ? {browserExecutable} : {}), logLevel: 'error'});
  } catch (error) { fail('Legacy Remotion render failed', {detail: String(error.message).slice(-4000)}); }
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
    ...(proresProfile ? { prores_profile: proresProfile } : {}),
  }) + "\n"
);
