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
  let browser, page;
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
    page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [], requests = [], cancellations = [];
    page.on('request', request => { requests.push(request.url()); if (request.method() === 'POST' && request.url().endsWith('/cancel')) cancellations.push(request.url()); });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base);
    await page.waitForFunction(() => document.querySelector('#preview-freshness').textContent === 'Current', null, { timeout: 120000 });
    assert.equal(await page.locator('#authoring-source').isVisible(), false);
    assert.equal(await page.locator('#graphics-source').isVisible(), false);
    assert.equal(await page.locator('#preview-player').getAttribute('controls'), null);
    await page.waitForFunction(() => {
      const svg = document.querySelector('#btn-play svg');
      return svg?.namespaceURI === 'http://www.w3.org/2000/svg' && svg.getBBox().width > 0;
    });
    assert.ok(!requests.some(url => /\/(chat|ws)\.js|llm-config|\/api\/runtimes/.test(url)), 'Agent extension loaded in review mode');
    const timelineBounds = await page.locator('#timeline-panel').boundingBox();
    assert.ok(timelineBounds && timelineBounds.y + timelineBounds.height <= 1001, 'Timeline is outside the desktop workspace');
    const barBounds = await page.locator('.workspace-bar').boundingBox();
    assert.ok(barBounds.y < 100 && barBounds.height < 80, 'Workspace bar consumed the editing area');
    const playerBounds = await page.locator('#preview-player').boundingBox();
    assert.ok(playerBounds.height > 300 && playerBounds.y < 200, 'Preview stage is cropped');
    const manifest = await (await fetch(`${base}/api/projects/${id}/preview-chunks`)).json();
    assert.ok(manifest.manifest.chunks.length >= 2);
    await page.locator('#preview-seek').evaluate(input => { input.value = '1.25'; input.dispatchEvent(new Event('input', {bubbles:true})); });
    await page.waitForFunction(() => window.OpenEdit.state.previewChunkStart === 1 && document.querySelector('#preview-player').readyState >= 2);
    await page.waitForFunction(() => Math.abs(window.OpenEdit.state.playheadSec - 1.25) < .1);
    await page.locator('#preview-seek').evaluate(input => { input.value = '0'; input.dispatchEvent(new Event('input', {bubbles:true})); });
    await page.waitForFunction(() => window.OpenEdit.state.previewChunkStart === 0 && document.querySelector('#preview-player').readyState >= 2);
    await page.waitForFunction(() => !document.querySelector('#history-undo').disabled);
    await page.locator('#history-undo').click();
    await page.waitForFunction(() => document.querySelector('#preview-freshness').textContent === 'No clips');
    assert.equal(await page.locator('#preview-player').getAttribute('src'), null);
    await page.locator('#history-redo').click();
    await page.waitForFunction(() => document.querySelector('#preview-freshness').textContent === 'Current', null, {timeout:120000});
    await page.locator('#btn-setup').click();
    await page.waitForFunction(() => document.querySelector('#setup-checks').textContent.includes('Timeline preview and export'));
    await page.locator('#modal-setup [data-modal-close]').last().click();
    fs.mkdirSync(path.join(__dirname, 'artifacts'), { recursive: true });
    await page.screenshot({ path: path.join(__dirname, 'artifacts/workspace-review.png'), fullPage: true });
    await page.waitForFunction(() => document.querySelector('#preview-player').readyState >= 2);
    await page.locator('.timeline-clip').first().click();
    await page.waitForFunction(() => document.querySelector('#authoring-clip').value.includes('c-hero'));
    await page.locator('#workspace-code').click();
    const editor = page.locator('#authoring-source');
    await editor.waitFor({ state: 'visible' });
    await page.waitForFunction(() => document.querySelector('#authoring-source').value.includes('c-hero'));
    const initial = await editor.inputValue();
    await editor.fill('// Browser-authored draft\n' + initial);
    await page.locator('#authoring-apply').click();
    await page.waitForFunction(() => document.querySelector('#authoring-status').textContent.startsWith('Saved'));
    assert.ok((await editor.inputValue()).includes('Browser-authored draft'));
    // Hold polling long enough to exercise cancellation of an obsolete automatic update.
    await page.route('**/render_jobs/*', route => route.request().method() === 'GET' ? route.fulfill({json:{status:'running'}}) : route.continue());
    const autoSubmitted = page.waitForRequest(request => request.method() === 'POST' && request.url().endsWith('/render') && request.postDataJSON()?.mode === 'preview-chunks');
    await page.locator('#authoring-properties input[name=start]').fill('3');
    await page.locator('#authoring-apply-properties').click();
    await page.waitForFunction(() => document.querySelector('#authoring-source').value.includes('start={3}'));
    await page.waitForFunction(() => !document.querySelector('#history-undo').disabled);
    await autoSubmitted;
    const retained = await page.locator('#preview-player').getAttribute('src');
    assert.ok(retained.includes('/preview-chunks/files/'), 'Last good preview was lost during update');
    await page.locator('#history-undo').click();
    await page.waitForFunction(expected => document.querySelector('#authoring-source').value === expected, '// Browser-authored draft\n' + initial);
    await page.waitForFunction(() => document.querySelector('#preview-freshness').textContent !== 'Current');
    await page.unroute('**/render_jobs/*');
    assert.ok(cancellations.length, 'Obsolete preview was not cancelled');
    await page.locator('#history-redo').click();
    await page.waitForFunction(() => document.querySelector('#authoring-source').value.includes('start={3}'));
    await page.waitForFunction(() => document.querySelector('#preview-freshness').textContent === 'Current', null, {timeout:120000});
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
    await page.locator('#workspace-graphics').click();
    await page.locator('.graphics-source-details summary').click();
    const graphics = page.locator('#graphics-source');
    await page.waitForFunction(() => document.querySelector('#graphics-source').value.includes('Your title'));
    await graphics.fill((await graphics.inputValue()).replace('Your title', 'OpenEdit graphics').replace('</scene>',
      '<group id="group-contract" x={10} y={10} hidden><rect id="group-child" width={30} height={20}/></group></scene>'));
    await page.locator('#graphics-duration').fill('0.5');
    await page.locator('#graphics-commit').click();
    await page.waitForFunction(() => document.querySelector('#graphics-status').textContent.includes('Saved editable source'));
    await page.locator('#graphics-preview').click();
    await page.waitForFunction(() => document.querySelector('#graphics-status').textContent.includes('passed quality'), null, { timeout: 120000 });
    await page.waitForFunction(() => document.querySelector('#graphics-video').readyState >= 2);
    await page.locator('#graphics-element').selectOption('group-contract');
    assert.ok(await page.locator('#graphics-properties input[name=width]').isDisabled());
    await page.locator('#graphics-properties input[name=x]').fill('15');
    await page.locator('#graphics-properties button').click();
    await page.waitForFunction(() => /id="group-contract"\s+x=\{15\}/.test(document.querySelector('#graphics-source').value));
    await page.locator('#graphics-element').selectOption('title');
    await page.locator('#graphics-properties input[name=x]').fill('125');
    await page.locator('#graphics-properties button').click();
    await page.waitForFunction(() => document.querySelector('#graphics-source').value.includes('x={125}'));
    assert.ok(!(await page.locator('#graphics-commit').isDisabled()));
    await page.waitForFunction(() => document.querySelector('#graphics-status').textContent.startsWith('Saved editable'));
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
    const savedGraphics = await (await fetch(`${base}/api/projects/${encodeURIComponent(id)}/graphics`)).json();
    assert.ok(savedGraphics.existing);
    assert.ok(savedGraphics.source.includes('OpenEdit graphics'));
    assert.ok(savedGraphics.source.includes('x={155}'));
    await page.locator('#graphics-panel').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(__dirname, 'artifacts/graphics-desktop.png'), fullPage: true });
    await graphics.fill('// Keep this graphics draft\n' + savedGraphics.source);
    const latest = await (await fetch(`${endpoint}?include_source=true`)).json();
    const objects = await (await fetch(`${base}/api/projects/${encodeURIComponent(id)}/studio?include_source=true`)).json();
    const doc = objects.objects.find(o=>o.kind === 'document');
    const external = await fetch(`${base}/api/projects/${encodeURIComponent(id)}/studio`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      expected_revision: latest.graph_revision, changes: [{kind:'document',object_id:doc.object_id,data:{...doc.data,source:doc.data.source.replace('OpenEdit graphics','External title')}}],
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
    await page.locator('#workspace-review').click();
    await page.locator('.timeline-clip').first().click();
    await page.waitForFunction(() => document.querySelector('#right-panel').classList.contains('open'));
    assert.ok(await page.locator('#authoring-properties').isVisible());
    await page.screenshot({ path:path.join(__dirname, 'artifacts/workspace-mobile-inspector.png'), fullPage:true });
    await page.locator('#btn-right-panel').click();
    await page.locator('#project-select').selectOption('');
    await page.waitForFunction(() => !window.OpenEdit.state.currentProjectId && !document.querySelector('#preview-player').getAttribute('src'));
    assert.ok(await page.locator('#history-undo').isDisabled());
    await page.locator('#project-select').selectOption(id);
    await page.waitForFunction(() => document.querySelector('#preview-freshness').textContent === 'Current', null, {timeout:120000});
    const setupBounds = await page.locator('#btn-setup').boundingBox();
    assert.ok(setupBounds.x >= 0 && setupBounds.x + setupBounds.width <= 390, 'Mobile Setup is clipped');
    const playBounds = await page.locator('#btn-play').boundingBox();
    const volumeBounds = await page.locator('#preview-volume').boundingBox();
    assert.ok(volumeBounds.y - playBounds.y < 70, 'Transport split into too many rows');
    await page.screenshot({ path:path.join(__dirname, 'artifacts/workspace-mobile-review.png'), fullPage:true });
    assert.deepEqual(errors, []);
    console.log('Browser media/graphics source, canvas drag, QC preview, IR commit, stale conflicts and responsive captures passed');
  } catch (error) {
    const artifacts = path.join(__dirname, 'artifacts'); fs.mkdirSync(artifacts, {recursive:true});
    fs.copyFileSync(path.join(root, 'server.log'), path.join(artifacts, 'workspace-server.log'));
    if (page) {
      await page.screenshot({path:path.join(artifacts,'workspace-failure.png'),fullPage:true}).catch(() => {});
      fs.writeFileSync(path.join(artifacts,'workspace-failure.json'), JSON.stringify(await page.evaluate(() => ({
        history:document.querySelector('#history-status')?.textContent,
        sourceStatus:document.querySelector('#authoring-status')?.textContent,
        graphicsStatus:document.querySelector('#graphics-status')?.textContent,
        graphicsSource:document.querySelector('#graphics-source')?.value,
        graphicsLayers:document.querySelector('#graphics-element')?.innerHTML,
        source:document.querySelector('#authoring-source')?.value,
        preview:document.querySelector('#preview-freshness')?.outerHTML,
        project:window.OpenEdit.state.currentProjectState,
      })),null,2));
    }
    throw error;
  } finally {
    if (browser) await browser.close();
    server.kill();
    fs.closeSync(log);
    fs.rmSync(root, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
