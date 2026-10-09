// Real interactive/export parity and durable studio interaction acceptance.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const { chromium } = require('playwright-core');
const directory = path.resolve('open_edit/integrations/diffusion/browser');
const { compile } = require(path.join(directory, 'compile.cjs'));
const esbuild = require(path.join(directory, 'node_modules/esbuild'));
const artifacts = path.join(__dirname, 'artifacts');
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
// The timeline repaints clips after every snapshot; re-query until laid out.
async function boxOf(locator) { for (let i = 0; i < 50; i++) { const box = await locator.boundingBox().catch(() => null); if (box) return box; await wait(100); } throw new Error('Element never laid out'); }

async function bundle(name) {
  const alias = {};
  for (const part of ['runtime','reconciler','encoder','assets','jsx']) alias[`@diffusionstudio/${part}`] = path.join(directory, 'vendor', part, 'src/index.ts');
  return (await esbuild.build({entryPoints:[path.join(directory, name)], bundle:true, platform:'browser', format:'iife', target:'chrome130',
    alias, conditions:['browser'], write:false, banner:{js:'"use strict";'}, legalComments:'inline', logLevel:'silent'})).outputFiles[0].text;
}
async function parity(browser) {
  const source = `export default function Graphics() { return <stage id="stage"><scene id="scene" width={320} height={180} active>
    <group id="outer" x={40} y={30} rotation={20}><group id="inner" x={20} y={10} scale={1.2}>
      <rect id="animated" x={0} y={0} width={60} height={40} fill="#dd3355" end={2}>
        <keyframeTrack id="motion" property="x"><keyframe id="a" time={0} value={0} easing="easeIn"/><keyframe id="b" time={1} value={80}/></keyframeTrack>
      </rect></group></group></scene></stage>; }`;
  const compiled = await compile(source), editorCode = await bundle('editor-runtime.ts'), exportCode = await bundle('runtime.ts');
  const page = await browser.newPage();
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('.woff2')) return route.fulfill({contentType:'font/woff2', path:path.join(directory,'fonts/OpenEditSans.woff2')});
    if (url.pathname === '/') return route.fulfill({contentType:'text/html',body:'<!doctype html><canvas id="editor"></canvas>'});
    return route.abort();
  });
  await page.goto('https://openedit.invalid/'); await page.addScriptTag({content:editorCode});
  const result = await page.evaluate(async ({code}) => {
    const canvas = document.querySelector('#editor');
    const editor = await window.OpenEditCanvas.create(canvas, {code, fps:30, assets:[]});
    const first = await editor.frame(0), firstPixels = [...canvas.getContext('2d').getImageData(0,0,320,180).data];
    const later = await editor.frame(.5), interactive = [...canvas.getContext('2d').getImageData(0,0,320,180).data];
    await editor.frame(0); const seekBack = [...canvas.getContext('2d').getImageData(0,0,320,180).data];
    await editor.dispose();
    return {interactive, firstPixels, seekBack, first, later};
  }, {code:compiled.code});
  // Each production host has its own realm. Koota installs Number.prototype
  // entity methods; loading two independent bundles into one realm replaces
  // those methods with the other bundle's world registry.
  await page.reload(); await page.addScriptTag({content:exportCode});
  const exported = await page.evaluate(async ({code}) => {
    await window.openEdit.mount(code,30,[]);
    const png = await window.openEdit.frame(15), bytes = Uint8Array.from(atob(png), c=>c.charCodeAt(0));
    const bitmap = await createImageBitmap(new Blob([bytes],{type:'image/png'}));
    const comparison = document.createElement('canvas'); comparison.width=320; comparison.height=180;
    comparison.getContext('2d').drawImage(bitmap,0,0); bitmap.close();
    const pixels = [...comparison.getContext('2d').getImageData(0,0,320,180).data];
    await window.openEdit.dispose(); return pixels;
  }, {code:compiled.code});
  result.maxDifference = result.interactive.reduce((max,v,i)=>Math.max(max,Math.abs(v-exported[i])),0);
  result.seekDifference = result.firstPixels.reduce((max,v,i)=>Math.max(max,Math.abs(v-result.seekBack[i])),0);
  // Geometry must use the same matrix which put the colored rectangle here.
  fs.writeFileSync(path.join(artifacts,'studio-geometry.json'),JSON.stringify({first:result.first,later:result.later},null,2));
  const animated = result.later.find(g=>g.id==='animated'); assert.ok(animated, 'Missing source-ID geometry');
  assert.ok(animated.x>24 && animated.x<27,'Named easing did not use the shared Bezier evaluator');
  const center = animated.corners.reduce((p,c)=>[p[0]+c[0]/4,p[1]+c[1]/4],[0,0]);
  const pixel = (Math.round(center[1])*320+Math.round(center[0]))*4;
  result.color = exported.slice(pixel,pixel+4);
  delete result.interactive; delete result.firstPixels; delete result.seekBack;
  assert.equal(result.maxDifference,0,'Interactive pixels differ from checked export pixels');
  assert.equal(result.seekDifference,0,'Backward seeking changed the authored frame');
  assert.deepEqual(result.color,[221,51,85,255]);
  assert.ok(result.first.some(g=>g.id==='inner') && result.later.some(g=>g.id==='animated'));
  assert.notDeepEqual(result.first.find(g=>g.id==='animated').corners,result.later.find(g=>g.id==='animated').corners);
  fs.writeFileSync(path.join(artifacts,'studio-render-parity.json'),JSON.stringify(result,null,2)); await page.close();
}

(async () => {
  fs.mkdirSync(artifacts,{recursive:true});
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  const root = fs.mkdtempSync(path.join(os.tmpdir(),'openedit-studio-')), python = process.env.OPEN_EDIT_TEST_PYTHON || 'python';
  let server, page;
  try {
    await parity(browser);
    const seeded = spawnSync(python,[path.join(__dirname,'fixture.py'),root],{encoding:'utf8'}); assert.equal(seeded.status,0,seeded.stderr);
    const projectPath = JSON.parse(seeded.stdout.trim().split('\n').at(-1)).project_path;
    const log = fs.openSync(path.join(root,'server.log'),'w'), base='http://127.0.0.1:18764';
    server = spawn(python,['-m','open_edit.cli','serve','--review-only','--port','18764'],{env:{...process.env,OPEN_EDIT_PROJECTS_ROOT:root,OPEN_EDIT_SOURCE_PROXY_AUTO:'0'},stdio:['ignore',log,log]}); fs.closeSync(log);
    let ready=false;
    for(let i=0;i<120;i++){try{ready=(await fetch(`${base}/api/health`)).ok;}catch{} if(ready)break; if(server.exitCode!==null)throw new Error(fs.readFileSync(path.join(root,'server.log'),'utf8')); await wait(100);}
    assert.ok(ready,'Studio server did not start');
    const projects=await (await fetch(`${base}/api/projects`)).json(), id=projects[0].id;
    const api = async (suffix,body) => { const response=await fetch(`${base}/api/projects/${encodeURIComponent(id)}${suffix}`,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}); const result=await response.json(); assert.ok(response.ok,JSON.stringify(result));return result; };
    page=await browser.newPage({viewport:{width:1600,height:1050}}); const errors=[]; page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base);
    await page.locator('.timeline-clip[data-clip-id="hero"]').waitFor();
    await page.waitForFunction(()=>Number.isInteger(window.OpenEdit.state.editingSelection?.expected_revision));
    // Actual pointer edits use the guarded IR path, without opening Code.
    const hero = page.locator('.timeline-clip[data-clip-id="hero"]');
    let clipBox = await boxOf(hero);
    const pps = Number(await page.locator('#timeline-tracks-area').getAttribute('data-pixels-per-second'));
    // Media-space marks are timed source objects, shared with AI and undoable.
    await page.locator('#media-mark-toolbar select').selectOption('rectangle');
    const mediaBox=await page.locator('#media-mark-overlay').boundingBox();
    await page.mouse.move(mediaBox.x+mediaBox.width*.2,mediaBox.y+mediaBox.height*.2);await page.mouse.down();
    await page.mouse.move(mediaBox.x+mediaBox.width*.5,mediaBox.y+mediaBox.height*.5,{steps:8});await page.mouse.up();
    await page.locator('#media-mark-properties textarea[name=text]').fill('Align the video edit here');
    await page.locator('#media-mark-properties').getByRole('button',{name:'Save mark',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#media-mark-properties textarea[name=text]').value==='Align the video edit here');
    const marked=await api('/editing-context',{annotation_ids:[],selected_ids:[],playhead_sec:0});
    assert.ok(marked.annotations.some(o=>o.data.text==='Align the video edit here'));
    await page.screenshot({path:path.join(artifacts,'studio-video-marks.png'),fullPage:true});
    await page.locator('#media-marks-inspector').getByRole('button',{name:'Convert to graphic',exact:true}).click();
    await page.waitForFunction(()=>window.OpenEdit.state.currentProjectState.timeline_full.tracks.flatMap(t=>t.clips).length===2);
    assert.equal((await api('/studio?include_source=true')).objects.filter(o=>o.kind==='document').length,1);
    await page.locator('#history-undo').click();
    await page.waitForFunction(()=>window.OpenEdit.state.currentProjectState.timeline_full.tracks.flatMap(t=>t.clips).length===1);
    await page.locator('#media-mark-toolbar select').selectOption('off');
    await hero.waitFor({state:'visible'});clipBox=await boxOf(hero);
    await page.mouse.move(clipBox.x+clipBox.width/2,clipBox.y+clipBox.height/2);
    await page.mouse.down();await page.mouse.move(clipBox.x+clipBox.width/2+pps,clipBox.y+clipBox.height/2,{steps:8});await page.mouse.up();
    await page.waitForFunction(()=>window.OpenEdit.state.currentProjectState.timeline_full.tracks.flatMap(t=>t.clips).find(c=>c.clip_id==='hero')?.position_sec===1);
    await hero.waitFor({state:'visible'});
    clipBox = await boxOf(hero);
    await page.mouse.move(clipBox.x+clipBox.width-3,clipBox.y+clipBox.height/2);await page.mouse.down();
    await page.mouse.move(clipBox.x+clipBox.width-3-pps*.5,clipBox.y+clipBox.height/2,{steps:8});await page.mouse.up();
    await page.waitForFunction(()=>window.OpenEdit.state.currentProjectState.timeline_full.tracks.flatMap(t=>t.clips).find(c=>c.clip_id==='hero')?.out_point_sec===1.5);
    await hero.click();await page.locator('#timeline-inspector select[aria-label="Add effect"]').selectOption('brightness');
    await page.locator('#timeline-inspector .effect-card input[name=value]').fill('0.7');
    await page.locator('#timeline-inspector').getByRole('button',{name:'Update effect',exact:true}).click();
    await page.waitForFunction(()=>window.OpenEdit.state.currentProjectState.timeline_full.tracks.flatMap(t=>t.clips).find(c=>c.clip_id==='hero')?.effects[0]?.params.value===.7);
    await page.locator('#timeline-inspector').getByRole('button',{name:'Bypass',exact:true}).click();
    await page.waitForFunction(()=>window.OpenEdit.state.currentProjectState.timeline_full.tracks.flatMap(t=>t.clips).find(c=>c.clip_id==='hero')?.effects[0]?.enabled===false);
    await page.locator('#timeline-inspector .studio-layer-actions').getByRole('button',{name:'Duplicate',exact:true}).click();
    await page.waitForFunction(()=>window.OpenEdit.state.currentProjectState.timeline_full.tracks.flatMap(t=>t.clips).length===2);
    const duplicate = await page.evaluate(()=>window.OpenEdit.state.currentProjectState.timeline_full.tracks.flatMap(t=>t.clips).find(c=>c.clip_id!=='hero').clip_id);
    await hero.click();
    await page.locator('#timeline-inspector').getByRole('button',{name:'Add visual transition',exact:true}).click();
    await page.waitForFunction(()=>window.OpenEdit.state.currentProjectState.timeline_full.visual_transitions.length===1);
    await page.locator('#timeline-inspector select[aria-label="Visual transition type"]').selectOption('wipe');
    await page.locator('#timeline-inspector').getByRole('button',{name:'Update transition',exact:true}).click();
    await page.waitForFunction(()=>window.OpenEdit.state.currentProjectState.timeline_full.visual_transitions[0]?.kind==='wipe');
    await page.locator('#timeline-inspector').getByRole('button',{name:'Bypass transition',exact:true}).click();
    await page.waitForFunction(()=>window.OpenEdit.state.currentProjectState.timeline_full.visual_transitions.length===0);
    await page.locator('#timeline-inspector').getByRole('button',{name:'Remove transition',exact:true}).click();
    await page.waitForFunction(()=>!window.OpenEdit.state.currentProjectState.timeline_full.tracks.flatMap(t=>t.clips).find(c=>c.clip_id==='hero').effects.some(e=>e.effect_type.startsWith('transition_')));
    await page.locator(`.timeline-clip[data-clip-id="${duplicate}"]`).click();
    await page.locator('#timeline-inspector .studio-layer-actions').getByRole('button',{name:'Ripple delete',exact:true}).click();
    await page.waitForFunction(()=>window.OpenEdit.state.currentProjectState.timeline_full.tracks.flatMap(t=>t.clips).length===1);
    await page.screenshot({path:path.join(artifacts,'studio-timeline-effects.png'),fullPage:true});
    await page.locator('#workspace-graphics').click();
    await page.waitForFunction(()=>document.querySelector('#graphics-status').textContent.startsWith('Interactive canvas'),null,{timeout:60000});
    await page.locator('#graphics-commit').click(); await page.waitForFunction(()=>document.querySelector('#graphics-status').textContent.startsWith('Saved editable'));
    await page.locator('.tab[data-tab="layers"]').click();
    await page.locator('[data-object-id="title"]').click();
    await page.locator('#graphics-properties [name=text]').fill('Manually editable title');
    await page.locator('#graphics-properties [type=submit]').click();
    await page.waitForFunction(()=>document.querySelector('#graphics-status').textContent.startsWith('Saved editable') && document.querySelector('#graphics-source').value.includes('Manually editable title'));
    const current=await api('/studio?include_source=true'), doc=current.objects.find(o=>o.kind==='document');
    assert.ok(doc.data.source.includes('Manually editable title'));
    await page.locator('#graphics-locked').check();
    await page.waitForFunction(()=>document.querySelector('#graphics-selection-status').textContent.includes('locked'));
    assert.ok(await page.locator('#graphics-properties [name=x]').isDisabled());
    const locked=await api('/studio?include_source=true');
    const rejected=await fetch(`${base}/api/projects/${id}/studio`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:locked.graph_revision,changes:[{kind:'document',object_id:doc.object_id,data:{...locked.objects.find(o=>o.kind==='document').data,source:doc.data.source.replace('Manually editable title','Locked change')}}]})});
    assert.equal(rejected.status,400);
    await page.locator('#graphics-locked').uncheck();
    await page.waitForFunction(()=>!document.querySelector('#graphics-properties [name=x]').disabled);
    // Keyframes are real source children; auto-key is off until explicitly set.
    const animation=page.locator('#graphics-animation');
    assert.equal(await animation.getByRole('checkbox',{name:'Auto-key'}).isChecked(),false);
    await animation.getByRole('combobox',{name:'Animated property'}).selectOption('x');
    await animation.locator('form').first().locator('input[name=value]').fill('120');
    await animation.getByRole('button',{name:'Add keyframe at playhead',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#graphics-source').value.includes('keyframeTrack'));
    await page.locator('#graphics-seek').fill('0.5');await page.locator('#graphics-seek').dispatchEvent('input');
    await animation.locator('form').first().locator('input[name=value]').fill('160');
    await animation.getByRole('button',{name:'Add keyframe at playhead',exact:true}).click();
    await page.waitForFunction(()=>document.querySelectorAll('#graphics-animation .keyframe-row').length===2);
    await animation.locator('.keyframe-row').first().locator('summary').click();
    await animation.locator('.keyframe-row').first().getByRole('combobox',{name:'Segment easing'}).selectOption('cubicBezier');
    await animation.locator('.keyframe-row').first().getByRole('button',{name:'Update keyframe',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#graphics-source').value.includes('cubicBezier'));
    await animation.getByRole('checkbox',{name:'Auto-key'}).check();
    await page.locator('#graphics-properties input[name=x]').fill('170');await page.locator('#graphics-properties [type=submit]').click();
    await page.waitForFunction(()=>document.querySelector('#graphics-source').value.includes('value={170}'));
    await animation.getByRole('checkbox',{name:'Auto-key'}).uncheck();
    await page.locator('#graphics-properties input[name=x]').fill('110');await page.locator('#graphics-properties [type=submit]').click();
    await page.waitForFunction(()=>document.querySelector('#graphics-source').value.includes('x={110}') && !document.querySelector('#graphics-commit').disabled);
    const animatedDoc=(await api('/studio?include_source=true')).objects.find(o=>o.kind==='document').data;
    const motion=animatedDoc.elements.find(e=>e.parent_id==='title' && e.tag==='keyframeTrack' && e.property==='x');
    assert.deepEqual(animatedDoc.elements.filter(e=>e.parent_id===motion.id).map(e=>e.value),[130,180]);
    await page.screenshot({path:path.join(artifacts,'studio-animation.png'),fullPage:true});
    await page.locator('#graphics-tool').selectOption('arrow');
    const box=await page.locator('#graphics-canvas').boundingBox();
    await page.mouse.move(box.x+box.width*.25,box.y+box.height*.3);await page.mouse.down();await page.mouse.move(box.x+box.width*.6,box.y+box.height*.6);await page.mouse.up();
    await page.locator('#graphics-mark-properties').waitFor({state:'visible'});
    await page.locator('#graphics-mark-properties [name=text]').fill('Move this title along this arrow');await page.locator('#graphics-mark-properties [type=submit]').click();
    await page.waitForFunction(()=>document.querySelector('#graphics-marks').textContent.includes('Move this title'));
    const context=await api('/editing-context',{document_id:doc.object_id,selected_ids:['title'],annotation_ids:[],playhead_sec:0});
    // The earlier video mark stays after conversion; find the graphics arrow itself.
    const arrow=context.annotations.find(o=>o.data.text==='Move this title along this arrow'); assert.ok(arrow); assert.equal(arrow.data.coordinate_space,'object'); assert.ok(context.documents[0].data.source.includes('Manually editable title'));
    // An external MCP agent uses the same durable source, with AI attribution.
    const latest=await api('/studio?include_source=true'), latestDoc=latest.objects.find(o=>o.kind==='document');
    const agent=spawnSync(python,['-c','import json,sys; from pathlib import Path; from open_edit.kernel.pillar_tools import dispatch_edit; x=json.load(sys.stdin); print(json.dumps(dispatch_edit("apply_studio_changes",x["params"],Path(x["path"]))))'],{
      input:JSON.stringify({path:projectPath,params:{expected_revision:latest.graph_revision,request_id:'browser-ai-request',label:'AI refine title',changes:[{kind:'document',object_id:latestDoc.object_id,data:{...latestDoc.data,source:latestDoc.data.source.replace('Manually editable title','AI refined title')}}]}}),encoding:'utf8'});
    assert.equal(agent.status,0,agent.stderr);assert.equal(JSON.parse(agent.stdout).status,'ok');
    await page.waitForFunction(()=>document.querySelector('#graphics-source').value.includes('AI refined title'),null,{timeout:20000});
    const history=await api('/history'); assert.equal(history.actions[0].author,'ai');assert.equal(history.actions[0].request_id,'browser-ai-request');
    await page.locator('#history-undo').click(); await page.waitForFunction(()=>document.querySelector('#graphics-source').value.includes('Manually editable title'));
    await page.locator('#history-redo').click(); await page.waitForFunction(()=>document.querySelector('#graphics-source').value.includes('AI refined title'));
    await page.waitForFunction(()=>!document.querySelector('#graphics-properties button').disabled);
    await page.locator('#graphics-properties input[name=fontSize]').fill('64');
    await page.locator('#graphics-properties button').click();
    await page.waitForFunction(()=>document.querySelector('#graphics-source').value.includes('fontSize={64}') && !document.querySelector('#graphics-commit').disabled);
    await page.locator('.tab[data-tab=edits]').click();
    await page.locator('[data-revert-request="browser-ai-request"]').click();
    await page.waitForFunction(()=>document.querySelector('#graphics-source').value.includes('Manually editable title') && document.querySelector('#graphics-source').value.includes('fontSize={64}'));
    assert.ok((await page.locator('#history-status').textContent()).includes('Unrelated later edits preserved'));
    await page.locator('#history-undo').click(); await page.waitForFunction(()=>document.querySelector('#graphics-source').value.includes('AI refined title'));
    await page.locator('#history-redo').click(); await page.waitForFunction(()=>document.querySelector('#graphics-source').value.includes('Manually editable title'));
    await page.screenshot({path:path.join(artifacts,'studio-editable-desktop.png'),fullPage:true});
    await page.reload();await page.locator('#workspace-graphics').click();
    await page.waitForFunction(()=>document.querySelector('#graphics-source').value.includes('Manually editable title') && document.querySelector('#graphics-source').value.includes('fontSize={64}'));
    assert.ok((await api('/studio?kind=annotation')).objects.some(o=>o.data.text==='Move this title along this arrow'));
    await page.locator('#workspace-review').click();
    await page.locator('.tab[data-tab="captions"]').click();
    await page.locator('#caption-editor').getByRole('button',{name:'Add caption',exact:true}).click();
    await page.locator('#caption-properties [name=text]').fill('Editable export caption');
    await page.locator('#caption-properties [name=start_sec]').fill('0');
    await page.locator('#caption-properties [name=end_sec]').fill('1');
    await page.locator('#caption-properties [name=font_size]').fill('72');
    await page.locator('#caption-properties [type=submit]').click();
    await page.waitForFunction(()=>window.OpenEdit.state.currentProjectState.timeline_full.captions && Object.values(window.OpenEdit.state.currentProjectState.timeline_full.captions).some(c=>c.text==='Editable export caption'));
    const srt=await fetch(`${base}/api/projects/${id}/captions.srt`);assert.ok((await srt.text()).includes('Editable export caption'));
    await page.locator('#caption-editor [name=style_name]').fill('Browser caption style');
    await page.locator('#caption-editor').getByRole('button',{name:'Save reusable style',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#caption-editor select[aria-label="Caption style"]').textContent.includes('Browser caption style'));
    await page.screenshot({path:path.join(artifacts,'studio-captions.png'),fullPage:true});
    // Export opens settings and produces a verified local file from this revision.
    await page.locator('#btn-render-final').click();
    await page.locator('#export-dialog').waitFor({state:'visible'});
    const outputFolder=path.join(root,'Local Desktop');
    await page.locator('#export-form [name=folder]').fill(outputFolder);
    await page.locator('#export-form [name=filename]').fill('Browser final');
    await page.locator('#export-form [name=encoder]').selectOption('cpu');
    await page.screenshot({path:path.join(artifacts,'studio-export-settings.png'),fullPage:true});
    await page.locator('#export-submit').click();
    await page.waitForFunction(()=>document.querySelector('#export-status').textContent==='Export verified and saved.',null,{timeout:120000});
    const output=path.join(outputFolder,'Browser final.mp4');assert.ok(fs.statSync(output).size>1000);
    assert.equal(await page.locator('#export-result').getByRole('button',{name:'Open folder'}).count(),1);
    const probe=spawnSync('ffprobe',['-v','error','-show_streams','-of','json',output],{encoding:'utf8'});
    assert.equal(probe.status,0,probe.stderr);const video=JSON.parse(probe.stdout).streams.find(s=>s.codec_type==='video');
    assert.equal(video.width,640);assert.equal(video.height,360);
    fs.writeFileSync(path.join(artifacts,'studio-browser-export.json'),JSON.stringify({output,video},null,2));
    await page.locator('#export-dialog').getByRole('button',{name:'Close export settings'}).click();
    await page.locator('#quality-check-form input[name=start_sec]').fill('0');
    await page.locator('#quality-check-form input[name=end_sec]').fill('0.5');
    await page.locator('#quality-check-form').getByRole('button',{name:'Check range',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#quality-check-status').textContent==='Full-quality range verified',null,{timeout:120000});
    await page.locator('#quality-check-dialog video').waitFor();
    await page.screenshot({path:path.join(artifacts,'studio-range-check.png'),fullPage:true});
    await page.locator('#quality-check-dialog').getByRole('button',{name:'Close',exact:true}).click();
    await page.locator('#workspace-graphics').click();
    await page.setViewportSize({width:390,height:844});await page.locator('#graphics-panel').scrollIntoViewIfNeeded();
    assert.ok((await page.locator('#graphics-canvas').boundingBox()).width>250);
    await page.screenshot({path:path.join(artifacts,'studio-editable-mobile.png'),fullPage:true}); assert.deepEqual(errors,[]);
    console.log('Studio source, manual/AI edits, locks, marks, history, reopen and exact interactive/export pixels passed');
  } catch(error) {
    if(page)await page.screenshot({path:path.join(artifacts,'studio-failure.png'),fullPage:true}).catch(()=>{});
    if(fs.existsSync(path.join(root,'server.log')))fs.copyFileSync(path.join(root,'server.log'),path.join(artifacts,'studio-server.log'));
    throw error;
  } finally { await browser.close();server?.kill();fs.rmSync(root,{recursive:true,force:true}); }
})().catch(error=>{console.error(error);process.exitCode=1;});
