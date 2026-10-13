// Real playhead-first preview, precise seeking, durable AI instructions and reopen.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn, spawnSync} = require('node:child_process');
const {chromium} = require('playwright-core');
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'openedit-core-ui-'));
  const python = process.env.OPEN_EDIT_TEST_PYTHON || 'python';
  const artifacts = path.join(__dirname, 'artifacts'); fs.mkdirSync(artifacts, {recursive:true});
  let server, browser, page;
  try {
    const seeded = spawnSync(python, [path.join(__dirname, 'fixture.py'), root], {encoding:'utf8'});
    assert.equal(seeded.status, 0, seeded.stderr);
    const project = JSON.parse(seeded.stdout.trim().split('\n').at(-1)).project_path;
    const extended = spawnSync(python, ['-c',
      'import sys; from pathlib import Path; from open_edit.storage.edit_graph import EditGraphStore; from open_edit.ir.types import AddClipOp; s=EditGraphStore(Path(sys.argv[1])/".open_edit/edit_graph.db"); h=s.load_all()[0].asset_hash; s.append_many([AddClipOp(author="user",clip_id="part"+str(i),asset_hash=h,track_id="main",position_sec=i*2,out_point_sec=2) for i in range(1,6)])',
      project], {encoding:'utf8'});
    assert.equal(extended.status, 0, extended.stderr);
    const base = 'http://127.0.0.1:18769', log = fs.openSync(path.join(root, 'server.log'), 'w');
    server = spawn(python, ['-m', 'open_edit.cli', 'serve', '--review-only', '--port', '18769'], {
      env:{...process.env, OPEN_EDIT_PROJECTS_ROOT:root, OPEN_EDIT_SOURCE_PROXY_AUTO:'0'}, stdio:['ignore', log, log]});
    fs.closeSync(log);
    let ready = false;
    for (let i=0;i<120;i++) { try {ready=(await fetch(base+'/api/health')).ok;} catch {} if (ready) break; await wait(100); }
    assert.ok(ready, 'Editor server did not start');
    const projects = await (await fetch(base+'/api/projects')).json(), id = projects[0].id;
    browser = await chromium.launch({executablePath:process.env.OPEN_EDIT_CHROMIUM, headless:true, args:['--no-sandbox']});
    page = await browser.newPage({viewport:{width:1440,height:900}});
    const errors=[], requests=[]; page.on('pageerror', error=>errors.push(error.message));
    page.on('request', request=>{if(request.url().endsWith('/render') && request.method()==='POST') requests.push(request.postDataJSON());});
    const start = performance.now(); await page.goto(base);
    await page.waitForFunction(()=>document.querySelector('#preview-freshness').dataset.status==='partial', null, {timeout:90000});
    const firstPreviewMs = performance.now()-start;
    assert.ok(requests[0].ranges.length && requests[0].ranges[0].end_sec<12, JSON.stringify(requests));
    assert.ok(await page.locator('#preview-player').getAttribute('src'));
    await page.waitForFunction(()=>document.querySelector('#preview-freshness').dataset.status==='current', null, {timeout:90000});
    assert.ok(requests.some(r=>r.priority==='background'));
    await page.locator('.timeline-clip[data-clip-id=hero]').click();
    await page.locator('#editor-request').fill('Cut the pause at this frame');
    await page.locator('#editor-request-form button').click();
    await page.waitForFunction(()=>document.querySelector('#editor-request-status').textContent.startsWith('Saved'));
    const snapshot = await (await fetch(`${base}/api/projects/${id}/studio`)).json();
    const instruction = snapshot.objects.find(o=>o.kind==='annotation' && o.data.text==='Cut the pause at this frame');
    assert.ok(instruction && instruction.data.target_ids.includes('hero'));
    await page.reload(); await page.locator('.timeline-clip[data-clip-id=hero]').waitFor();
    const reopened = await (await fetch(`${base}/api/projects/${id}/studio`)).json();
    assert.ok(reopened.objects.some(o=>o.object_id===instruction.object_id));
    await page.waitForFunction(()=>document.querySelector('#preview-freshness').dataset.status==='current', null, {timeout:90000});
    const seekStart = performance.now();
    await page.evaluate(()=>window.dispatchEvent(new CustomEvent('openedit:seek', {detail:11})));
    await page.waitForFunction(()=>{const p=document.querySelector('#preview-player');return p.readyState>=2 && !p.seeking && Math.abs(p.currentTime+window.OpenEdit.state.previewChunkStart-11)<1/60;});
    const seekMs=performance.now()-seekStart;
    await page.locator('#btn-skip-fwd').click();
    await page.waitForFunction(()=>Math.abs(window.OpenEdit.state.playheadSec-(11+1/30))<.00001);
    await page.screenshot({path:path.join(artifacts,'core-editor.png'),fullPage:true});
    assert.deepEqual(errors, []);
    const result={first_preview_ms:Math.round(firstPreviewMs),cached_seek_ms:Math.round(seekMs),
      first_requested_range:requests[0].ranges[0],timeline_duration_sec:12,background_fill:true,
      ai_instruction_saved_and_reopened:true,frame_step_correct:true,javascript_errors:errors};
    fs.writeFileSync(path.join(artifacts,'core-editor-metrics.json'), JSON.stringify(result,null,2));
    console.log(JSON.stringify(result));
  } catch (error) {
    if (page) await page.screenshot({path:path.join(artifacts,'core-editor-failure.png'),fullPage:true}).catch(()=>{});
    throw error;
  } finally {
    await browser?.close(); server?.kill(); fs.rmSync(root,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error);process.exitCode=1});
