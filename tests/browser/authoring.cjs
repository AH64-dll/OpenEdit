// Actual browser, HTTP server, compiler and SQLite writeback acceptance.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const { chromium } = require('playwright-core');

(async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'openedit-browser-'));
  const python = process.env.OPEN_EDIT_TEST_PYTHON || 'python';
  const seeded = spawnSync(python, [path.join(__dirname, 'fixture.py'), root], { encoding: 'utf8' });
  assert.equal(seeded.status, 0, seeded.stderr);
  const port = 18763;
  const base = `http://127.0.0.1:${port}`;
  const log = fs.openSync(path.join(root, 'server.log'), 'w');
  const server = spawn(python, ['-m', 'open_edit.cli', 'serve', '--review-only', '--port', String(port)], {
    env: { ...process.env, OPEN_EDIT_PROJECTS_ROOT: root, OPEN_EDIT_SOURCE_PROXY_AUTO: '0' },
    stdio: ['ignore', log, log],
  });
  let browser;
  try {
    let ready = false;
    for (let i = 0; i < 100; i++) {
      try { ready = (await fetch(`${base}/api/health`)).ok; } catch {}
      if (ready) break;
      if (server.exitCode !== null) throw new Error(fs.readFileSync(path.join(root, 'server.log'), 'utf8'));
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert.ok(ready, 'Review Studio did not start');
    const projects = await (await fetch(`${base}/api/projects`)).json();
    assert.equal(projects.length, 1);
    const id = projects[0].id;
    const endpoint = `${base}/api/projects/${encodeURIComponent(id)}/authoring`;
    browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base);
    await page.waitForFunction(() => document.querySelector('#preview-player').readyState >= 2);
    await page.locator('#authoring-panel summary').click();
    const editor = page.locator('#authoring-source');
    await editor.waitFor({ state: 'visible' });
    await page.waitForFunction(() => document.querySelector('#authoring-source').value.includes('c-hero'));
    const initial = await editor.inputValue();
    await editor.fill('// Browser-authored draft\n' + initial);
    await page.locator('#authoring-apply').click();
    await page.waitForFunction(() => document.querySelector('#authoring-status').textContent.startsWith('Saved'));
    assert.ok((await editor.inputValue()).includes('Browser-authored draft'));
    await page.locator('#authoring-properties input[name=start]').fill('3');
    await page.locator('#authoring-apply-properties').click();
    await page.waitForFunction(() => document.querySelector('#authoring-source').value.includes('start={3}'));
    const current = await (await fetch(`${endpoint}?include_source=true`)).json();
    assert.equal(current.elements[0].start, 3);
    assert.ok(current.source.includes('Browser-authored draft'));
    await editor.fill('// Keep my unsaved work\n' + current.source);
    const changed = await fetch(endpoint, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_revision: current.graph_revision, edits: [
        { kind: 'set', source: 'index.tsx:c-hero', props: { start: 5 } },
      ] }),
    });
    assert.ok(changed.ok, await changed.text());
    await page.locator('#authoring-apply').click({ force: true });
    await page.waitForFunction(() => document.querySelector('#authoring-status').textContent.includes('Project changed'));
    assert.ok((await editor.inputValue()).includes('Keep my unsaved work'));
    assert.ok(await page.locator('#authoring-apply').isDisabled());
    fs.mkdirSync(path.join(__dirname, 'artifacts'), { recursive: true });
    await page.screenshot({ path: path.join(__dirname, 'artifacts/authoring-conflict.png'), fullPage: true });
    await page.locator('#authoring-reload').click();
    await page.waitForFunction(() => document.querySelector('#authoring-source').value.includes('start={5}'));
    assert.ok(!(await editor.inputValue()).includes('Keep my unsaved work'));
    assert.notEqual(await editor.evaluate(el => getComputedStyle(el).color), await editor.evaluate(el => getComputedStyle(el).backgroundColor));
    await page.screenshot({ path: path.join(__dirname, 'artifacts/authoring-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('#authoring-panel').scrollIntoViewIfNeeded();
    assert.ok(await editor.isVisible());
    assert.ok((await editor.boundingBox()).width > 250);
    assert.equal(await page.locator('#right-panel').isVisible(), false);
    await page.screenshot({ path: path.join(__dirname, 'artifacts/authoring-mobile.png'), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.locator('#graphics-panel summary').click();
    const graphics = page.locator('#graphics-source');
    await page.waitForFunction(() => document.querySelector('#graphics-source').value.includes('Your title'));
    await graphics.fill((await graphics.inputValue()).replace('Your title', 'OpenEdit graphics').replace('</scene>',
      '<group id="group-contract" x={10} y={10} hidden><rect id="group-child" width={30} height={20}/></group></scene>'));
    await page.locator('#graphics-duration').fill('0.5');
    await page.locator('#graphics-preview').click();
    await page.waitForFunction(() => document.querySelector('#graphics-status').textContent.includes('passed quality'), null, { timeout: 120000 });
    await page.waitForFunction(() => document.querySelector('#graphics-video').readyState >= 2);
    await page.locator('#graphics-element').selectOption('group-contract');
    assert.ok(await page.locator('#graphics-properties input[name=width]').isDisabled());
    await page.locator('#graphics-properties input[name=x]').fill('15');
    await page.locator('#graphics-properties button').click();
    await page.waitForFunction(() => document.querySelector('#graphics-source').value.includes('id="group-contract" x={15}'));
    await page.locator('#graphics-element').selectOption('title');
    await page.locator('#graphics-properties input[name=x]').fill('125');
    await page.locator('#graphics-properties button').click();
    await page.waitForFunction(() => document.querySelector('#graphics-source').value.includes('x={125}'));
    assert.ok(await page.locator('#graphics-commit').isDisabled());
    const bounds = await page.locator('#graphics-canvas').boundingBox();
    // Move the text by 30 scene pixels using the actual canvas pointer path.
    const sx = bounds.width / 960, sy = bounds.height / 540;
    await page.mouse.move(bounds.x + 150 * sx, bounds.y + 380 * sy);
    await page.mouse.down();
    await page.mouse.move(bounds.x + 180 * sx, bounds.y + 395 * sy);
    await page.mouse.up();
    await page.waitForFunction(() => document.querySelector('#graphics-source').value.includes('x={155}') && document.querySelector('#graphics-source').value.includes('y={375}'));
    await page.locator('#graphics-preview').click();
    await page.waitForFunction(() => document.querySelector('#graphics-status').textContent.includes('passed quality'), null, { timeout: 120000 });
    await page.locator('#graphics-commit').click();
    await page.waitForFunction(() => document.querySelector('#graphics-status').textContent.includes('Graphics saved'));
    const savedGraphics = await (await fetch(`${base}/api/projects/${encodeURIComponent(id)}/graphics`)).json();
    assert.ok(savedGraphics.existing);
    assert.ok(savedGraphics.source.includes('OpenEdit graphics'));
    assert.ok(savedGraphics.source.includes('x={155}'));
    await page.locator('#graphics-panel').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(__dirname, 'artifacts/graphics-desktop.png'), fullPage: true });
    await graphics.fill('// Keep this graphics draft\n' + savedGraphics.source);
    const latest = await (await fetch(`${endpoint}?include_source=true`)).json();
    const external = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      expected_revision: latest.graph_revision, edits: [{ kind: 'set', source: 'index.tsx:c-hero', props: { start: 6 } }],
    }) });
    assert.ok(external.ok, await external.text());
    await page.waitForFunction(() => document.querySelector('#graphics-status').textContent.includes('Project changed'));
    assert.ok((await graphics.inputValue()).includes('Keep this graphics draft'));
    assert.ok(await page.locator('#graphics-preview').isDisabled());
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('#graphics-panel').scrollIntoViewIfNeeded();
    assert.ok((await graphics.boundingBox()).width > 250);
    assert.equal(await page.locator('#right-panel').isVisible(), false);
    await page.screenshot({ path: path.join(__dirname, 'artifacts/graphics-mobile-conflict.png'), fullPage: true });
    assert.deepEqual(errors, []);
    console.log('Browser media/graphics source, canvas drag, QC preview, IR commit, stale conflicts and responsive captures passed');
  } finally {
    if (browser) await browser.close();
    server.kill();
    fs.closeSync(log);
    fs.rmSync(root, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
