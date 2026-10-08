// MIT. Browser is spawned in the host's process group, including its encoder children.
const fs = require('node:fs/promises');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright-core');
const esbuild = require('esbuild');
const { compile } = require('./compile.cjs');
const delay = ms => new Promise(r => setTimeout(r, ms));
let chrome; let browser;
async function cleanup() {
  if (browser) await browser.close().catch(() => {});
  if (chrome && chrome.exitCode === null) chrome.kill('SIGTERM');
}
process.on('SIGTERM', () => cleanup().finally(() => process.exit(143)));
process.on('SIGINT', () => cleanup().finally(() => process.exit(130)));
(async () => {
  const request = JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
  const { document, code } = await compile(request.source);
  if (request.validate_only) {
    process.stdout.write(JSON.stringify({ ok: true, document })); return;
  }
  const alias = {};
  for (const name of ['runtime', 'reconciler', 'encoder', 'assets', 'jsx']) alias[`@diffusionstudio/${name}`] = path.join(__dirname, 'vendor', name, 'src/index.ts');
  const bundled = await esbuild.build({ entryPoints: [path.join(__dirname, 'runtime.ts')], bundle: true,
    platform: 'browser', format: 'iife', target: 'chrome130', alias, conditions: ['browser'],
    write: false, legalComments: 'inline', logLevel: 'silent' });
  const executable = process.env.OPEN_EDIT_CHROMIUM || chromium.executablePath();
  const profile = path.join(request.scratch, 'chromium'); await fs.mkdir(profile);
  chrome = spawn(executable, ['--headless', '--disable-gpu', '--disable-dev-shm-usage',
    '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
    ...(process.env.OPEN_EDIT_CHROMIUM_NO_SANDBOX === '1' ? ['--no-sandbox'] : [])],
    { stdio: 'ignore', detached: false });
  chrome.on('error', () => {});
  await fs.writeFile(path.join(request.scratch, 'processes.json'), JSON.stringify({ node: process.pid, chromium: chrome.pid }));
  let port;
  for (let i = 0; i < 300; i++) {
    if (chrome.exitCode !== null) throw new Error('Chromium exited before capture; install browser dependencies');
    try { port = (await fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; break; } catch {}
    await delay(100);
  }
  if (!port) throw new Error('Chromium startup timed out');
  browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
  const page = await browser.newPage(); page.setDefaultTimeout(30000);
  const assets = new Map(request.assets.map(a => [a.id, a]));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== 'https://openedit.invalid') return route.abort();
    const headers = { 'Cross-Origin-Opener-Policy': 'same-origin', 'Cross-Origin-Embedder-Policy': 'require-corp' };
    if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><body></body>', headers });
    if (url.pathname === '/runtime.js') return route.fulfill({ contentType: 'text/javascript', body: bundled.outputFiles[0].text, headers });
    if (url.pathname === '/font.woff2') return route.fulfill({ contentType: 'font/woff2', path: path.join(__dirname, 'fonts/OpenEditSans.woff2'), headers });
    const asset = assets.get(url.pathname.slice(8));
    if (url.pathname.startsWith('/assets/') && asset) return route.fulfill({ contentType: asset.mimeType, path: asset.file, headers });
    return route.abort();
  });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto('https://openedit.invalid/');
  await page.addScriptTag({ url: 'https://openedit.invalid/runtime.js' });
  await page.evaluate(async ({ code, fps, assets }) => window.openEdit.mount(code, fps, assets), {
    code, fps: request.fps, assets: request.assets.map(({ file, ...a }) => ({ ...a, url: `https://openedit.invalid/assets/${a.id}` })),
  });
  for (let frame = 0; frame < request.frames; frame++) {
    const encoded = await page.evaluate(i => window.openEdit.frame(i), frame);
    await fs.writeFile(path.join(request.scratch, `frame-${String(frame).padStart(6, '0')}.png`), Buffer.from(encoded, 'base64'));
  }
  if (errors.length) throw new Error(errors[0]);
  await page.evaluate(() => window.openEdit.dispose());
  process.stdout.write(JSON.stringify({ ok: true, document, frames: request.frames, browser_version: browser.version() }));
})().catch(error => { process.stdout.write(JSON.stringify({ ok: false, error: String(error.message).slice(0, 500) })); process.exitCode = 1; })
  .finally(cleanup);
