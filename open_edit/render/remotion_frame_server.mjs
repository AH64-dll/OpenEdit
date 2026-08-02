import {createHash} from "node:crypto";
import {realpath, stat} from "node:fs/promises";
import {relative, resolve, sep} from "node:path";
import {once} from "node:events";
import readline from "node:readline";

import {bundle} from "@remotion/bundler";
import {
  makeCancelSignal,
  renderStill,
  selectComposition,
} from "@remotion/renderer";

// Remotion's progress/browser messages use console.log in some releases.
// Stdout is reserved for the binary protocol; diagnostics belong on stderr.
for (const method of ["log", "info", "warn", "debug"]) {
  console[method] = (...args) => console.error(...args);
}

const REMOTION_VERSION = "4.0.278";
const DEFAULT_MAX_PROPS_JSON_BYTES = 1_000_000;
const DEFAULT_MAX_RESPONSE_BYTES = 64 * 1024 * 1024;
const MAX_FRAME_DIMENSION = 8192;
const MAX_FPS = 240;
const MAX_ERROR_BYTES = 512;
const PNG_SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

function parseArgs(argv) {
  const values = {
    projectRoot: null,
    requestTimeoutMs: 600_000,
    maxPropsJsonBytes: DEFAULT_MAX_PROPS_JSON_BYTES,
    maxResponseBytes: DEFAULT_MAX_RESPONSE_BYTES,
    browserExecutable: process.env.OPEN_EDIT_REMOTION_CHROME_BIN ||
      process.env.OPEN_EDIT_REMOTION_BROWSER_EXECUTABLE ||
      null,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--project-root") {
      values.projectRoot = argv[++index] ?? null;
    } else if (arg === "--request-timeout-ms") {
      values.requestTimeoutMs = Number(argv[++index]);
    } else if (arg === "--max-props-json-bytes") {
      values.maxPropsJsonBytes = Number(argv[++index]);
    } else if (arg === "--max-response-bytes") {
      values.maxResponseBytes = Number(argv[++index]);
    } else if (arg === "--browser-executable") {
      values.browserExecutable = argv[++index] ?? null;
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }
  if (!values.projectRoot) {
    throw new Error("--project-root is required");
  }
  for (const [name, value] of [
    ["request timeout", values.requestTimeoutMs],
    ["maximum props JSON bytes", values.maxPropsJsonBytes],
    ["maximum response bytes", values.maxResponseBytes],
  ]) {
    if (!Number.isSafeInteger(value) || value <= 0) {
      throw new Error(`${name} must be a positive integer`);
    }
  }
  return values;
}

function isInside(child, parent) {
  const childRelative = relative(parent, child);
  return childRelative === "" || (
    childRelative !== ".." &&
    !childRelative.startsWith(`..${sep}`) &&
    !childRelative.startsWith(sep) &&
    !/^[A-Za-z]:[\\/]/.test(childRelative)
  );
}

async function resolveProjectRoots(projectRootArg) {
  const projectRoot = await realpath(resolve(projectRootArg));
  const remotionRoot = await realpath(
    resolve(projectRoot, ".open_edit", "remotion"),
  );
  if (!isInside(remotionRoot, projectRoot)) {
    throw new Error("Remotion root must remain under the project root");
  }
  return {projectRoot, remotionRoot};
}

async function resolveEntryPoint(remotionRoot, entryPoint) {
  if (
    typeof entryPoint !== "string" ||
    !entryPoint ||
    entryPoint.includes("\0") ||
    entryPoint.startsWith("/") ||
    entryPoint.startsWith("\\") ||
    /^[A-Za-z]:[\\/]/.test(entryPoint)
  ) {
    throw new Error("entry_point must be relative under .open_edit/remotion");
  }
  const normalized = entryPoint.replaceAll("\\", "/");
  if (normalized.split("/").some((part) => part === "..")) {
    throw new Error("entry_point parent traversal is forbidden");
  }
  const candidate = resolve(remotionRoot, normalized);
  if (!isInside(candidate, remotionRoot)) {
    throw new Error("entry_point escapes the Remotion root");
  }
  const resolved = await realpath(candidate);
  if (!isInside(resolved, remotionRoot)) {
    throw new Error("entry_point resolves outside the Remotion root");
  }
  const info = await stat(resolved);
  if (!info.isFile()) {
    throw new Error(`entry_point is not a file: ${entryPoint}`);
  }
  return resolved;
}

function boundedError(error) {
  const message = error instanceof Error ? error.message : String(error);
  return message.replaceAll("\0", " ").replaceAll(/\r?\n/g, " ").slice(0, MAX_ERROR_BYTES) ||
    "unknown frame server error";
}

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) =>
      `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function validateRequest(request, config) {
  if (!request || typeof request !== "object" || Array.isArray(request)) {
    throw new Error("request must be a JSON object");
  }
  if (
    typeof request.request_id !== "string" ||
    !request.request_id ||
    request.request_id.length > 256
  ) {
    throw new Error("request_id must be a bounded non-empty string");
  }
  if (
    typeof request.composition_id !== "string" ||
    !request.composition_id ||
    request.composition_id.length > 256
  ) {
    throw new Error("composition_id must be a bounded non-empty string");
  }
  if (
    !request.props ||
    typeof request.props !== "object" ||
    Array.isArray(request.props)
  ) {
    throw new Error("props must be a JSON object");
  }
  const propsBytes = Buffer.byteLength(JSON.stringify(request.props), "utf8");
  if (propsBytes > config.maxPropsJsonBytes) {
    throw new Error(
      `props JSON exceeds ${config.maxPropsJsonBytes} bytes`,
    );
  }
  if (!Number.isSafeInteger(request.frame) || request.frame < 0) {
    throw new Error("frame must be a non-negative integer");
  }
  for (const [name, value] of [
    ["width", request.width],
    ["height", request.height],
  ]) {
    if (
      !Number.isSafeInteger(value) ||
      value <= 0 ||
      value > MAX_FRAME_DIMENSION
    ) {
      throw new Error(`${name} must be a positive bounded integer`);
    }
  }
  if (
    typeof request.fps !== "number" ||
    !Number.isFinite(request.fps) ||
    request.fps <= 0 ||
    request.fps > MAX_FPS
  ) {
    throw new Error("fps must be a positive bounded number");
  }
  if (typeof request.alpha !== "boolean") {
    throw new Error("alpha must be a boolean");
  }
  if (request.remotion_version !== REMOTION_VERSION) {
    throw new Error(`unsupported Remotion version; expected ${REMOTION_VERSION}`);
  }
  return request;
}

function writeStdout(data) {
  if (process.stdout.write(data)) {
    return Promise.resolve();
  }
  return once(process.stdout, "drain").then(() => undefined);
}

async function writeError(requestId, error) {
  const header = {
    request_id: typeof requestId === "string" ? requestId : "",
    ok: false,
    error: boundedError(error),
    remotion_version: REMOTION_VERSION,
  };
  await writeStdout(Buffer.from(`${JSON.stringify(header)}\n`, "utf8"));
}

async function writeFrame(request, buffer) {
  if (!Buffer.isBuffer(buffer) || buffer.length === 0) {
    throw new Error("renderStill returned no image buffer");
  }
  if (!buffer.subarray(0, PNG_SIGNATURE.length).equals(PNG_SIGNATURE)) {
    throw new Error("renderStill did not return PNG bytes");
  }
  if (buffer.length > config.maxResponseBytes) {
    throw new Error(`frame response exceeds ${config.maxResponseBytes} bytes`);
  }
  const header = {
    request_id: request.request_id,
    ok: true,
    content_type: "image/png",
    byte_length: buffer.length,
    width: request.width,
    height: request.height,
    frame: request.frame,
    remotion_version: REMOTION_VERSION,
    diagnostics: {
      browser_reuse: false,
      browser_lifecycle: "per-render",
    },
  };
  await writeStdout(
    Buffer.concat([
      Buffer.from(`${JSON.stringify(header)}\n`, "utf8"),
      buffer,
    ]),
  );
}

function withTimeout(work, timeoutMs, onTimeout) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      onTimeout();
      reject(new Error(`frame render timed out after ${timeoutMs}ms`));
    }, timeoutMs);
  });
  return Promise.race([work, timeout]).finally(() => clearTimeout(timer));
}

const config = parseArgs(process.argv.slice(2));
const {projectRoot, remotionRoot} = await resolveProjectRoots(config.projectRoot);
const bundleCache = new Map();
const compositionCache = new Map();
let activeCancel = null;
let shuttingDown = false;

async function getBundle(entryPoint) {
  if (!bundleCache.has(entryPoint)) {
    const pending = bundle({
      entryPoint,
      onProgress: () => {},
    }).catch((error) => {
      bundleCache.delete(entryPoint);
      throw error;
    });
    bundleCache.set(entryPoint, pending);
  }
  return bundleCache.get(entryPoint);
}

async function getComposition(request, serveUrl) {
  const propsHash = createHash("sha256")
    .update(stableStringify(request.props))
    .digest("hex");
  const key = [
    request.composition_id,
    propsHash,
    request.width,
    request.height,
    request.fps,
  ].join("|");
  if (!compositionCache.has(key)) {
    const pending = selectComposition({
      serveUrl,
      id: request.composition_id,
      inputProps: request.props,
      ...(config.browserExecutable
        ? {browserExecutable: config.browserExecutable}
        : {}),
    }).catch((error) => {
      compositionCache.delete(key);
      throw error;
    });
    compositionCache.set(key, pending);
  }
  const composition = await compositionCache.get(key);
  if (
    !Number.isSafeInteger(composition.durationInFrames) ||
    composition.durationInFrames <= 0
  ) {
    throw new Error("selected composition has an invalid durationInFrames");
  }
  if (request.frame >= composition.durationInFrames) {
    throw new Error(
      `frame ${request.frame} is outside durationInFrames ${composition.durationInFrames}`,
    );
  }
  if (
    typeof composition.fps === "number" &&
    Math.abs(composition.fps - request.fps) > 1e-6
  ) {
    throw new Error(
      `fps ${request.fps} does not match composition fps ${composition.fps}`,
    );
  }
  const scaleX = request.width / composition.width;
  const scaleY = request.height / composition.height;
  if (
    !Number.isFinite(scaleX) ||
    !Number.isFinite(scaleY) ||
    scaleX <= 0 ||
    Math.abs(scaleX - scaleY) > 1e-6
  ) {
    throw new Error("requested dimensions do not preserve composition aspect ratio");
  }
  return {composition, scale: scaleX, serveUrl};
}

async function renderFrame(request) {
  const cancelState = makeCancelSignal();
  activeCancel = cancelState.cancel;
  const work = (async () => {
    const entryPoint = await resolveEntryPoint(remotionRoot, request.entry_point);
    const serveUrl = await getBundle(entryPoint);
    const selected = await getComposition(request, serveUrl);
    // `output` is intentionally omitted: renderStill returns the image bytes
    // in its buffer field and no media/CAS artifact is produced.
    const still = await renderStill({
      composition: selected.composition,
      serveUrl: selected.serveUrl,
      frame: request.frame,
      inputProps: request.props,
      imageFormat: "png",
      scale: selected.scale,
      cancelSignal: cancelState.cancelSignal,
      logLevel: "error",
      ...(config.browserExecutable
        ? {browserExecutable: config.browserExecutable}
        : {}),
    });
    return still.buffer;
  })();
  work.catch(() => {});
  try {
    return await withTimeout(work, config.requestTimeoutMs, cancelState.cancel);
  } finally {
    if (activeCancel === cancelState.cancel) {
      activeCancel = null;
    }
  }
}

const input = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

process.once("SIGTERM", () => {
  shuttingDown = true;
  if (activeCancel) {
    activeCancel();
  }
  input.close();
  process.exitCode = 143;
});
process.once("SIGINT", () => {
  shuttingDown = true;
  if (activeCancel) {
    activeCancel();
  }
  input.close();
  process.exitCode = 130;
});

for await (const line of input) {
  if (shuttingDown) {
    break;
  }
  let request = null;
  try {
    if (Buffer.byteLength(line, "utf8") > config.maxPropsJsonBytes + 8192) {
      throw new Error("request line is too large");
    }
    request = JSON.parse(line);
    validateRequest(request, config);
    const buffer = await renderFrame(request);
    await writeFrame(request, buffer);
  } catch (error) {
    await writeError(request?.request_id, error);
  }
}

// Remotion may leave a local browser/server handle alive after stdin closes.
// The frame server owns that lifecycle, so close the private process now.
process.exit(process.exitCode ?? 0);
