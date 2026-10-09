// Actual selection -> local tracker -> editable effect -> preview/export -> reopen.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn,spawnSync} = require('node:child_process');
const {chromium} = require('playwright-core');
const wait = ms => new Promise(resolve=>setTimeout(resolve,ms));
const artifacts = path.join(__dirname,'artifacts');
(async()=>{
  fs.mkdirSync(artifacts,{recursive:true});
  const root = fs.mkdtempSync(path.join(process.env.OPEN_EDIT_TEST_TMP || os.tmpdir(),'openedit-tracking-'));
  const python = process.env.OPEN_EDIT_TEST_PYTHON || 'python', base='http://127.0.0.1:18765';
  let server,browser,page;
  try {
    const seed=spawnSync(python,[path.join(__dirname,'tracking_fixture.py'),root],{encoding:'utf8'});
    assert.equal(seed.status,0,seed.stderr);
    const log=fs.openSync(path.join(root,'server.log'),'w');
    server=spawn(python,['-m','open_edit.cli','serve','--review-only','--port','18765'],{
      env:{...process.env,OPEN_EDIT_PROJECTS_ROOT:root,OPEN_EDIT_SOURCE_PROXY_AUTO:'0'},stdio:['ignore',log,log]}); fs.closeSync(log);
    let ready=false;
    for(let i=0;i<150;i++){try{ready=(await fetch(`${base}/api/health`)).ok;}catch{}if(ready)break;if(server.exitCode!==null)throw new Error(fs.readFileSync(path.join(root,'server.log'),'utf8'));await wait(100);}
    assert.ok(ready,'Server did not start');
    const projects=await(await fetch(`${base}/api/projects`)).json(), id=projects[0].id;
    const api=async(suffix,body)=>{const response=await fetch(`${base}/api/projects/${encodeURIComponent(id)}${suffix}`,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await response.json();assert.ok(response.ok,JSON.stringify(result));return result;};
    browser=await chromium.launch({headless:true,args:['--no-sandbox']});page=await browser.newPage({viewport:{width:1600,height:1050}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base); await page.locator('.timeline-clip[data-clip-id="hero"]').waitFor();
    await page.waitForFunction(()=>Number.isInteger(window.OpenEdit.state.editingSelection?.expected_revision));
    await page.locator('#media-mark-toolbar select').selectOption('select');
    const box=await page.locator('#media-mark-overlay').boundingBox();
    await page.mouse.move(box.x+box.width*20/320,box.y+box.height*65/180);await page.mouse.down();
    await page.mouse.move(box.x+box.width*68/320,box.y+box.height*101/180,{steps:8});await page.mouse.up();
    await page.locator('#tracking-target-mode').selectOption('region');
    await page.locator('#tracking-start-button').click();
    await page.locator('[data-apply-track]').waitFor({timeout:30000});
    await page.screenshot({path:path.join(artifacts,'tracking-job-ready.png'),fullPage:true});
    await page.locator('[data-apply-track]').click();
    await page.locator('.tracking-object').waitFor();
    const objectId=await page.locator('.tracking-object').getAttribute('data-object-id');
    let object=await api(`/studio?kind=object_track&object_id=${objectId}&include_source=true`);
    assert.ok(object.objects[0].data.frames.length>40);assert.ok(object.objects[0].data.frames.every(f=>f.valid));
    await page.locator('[data-effect-picker]').selectOption('cover');await page.locator('[data-add-effect]').click();
    await page.locator('.tracked-effect').waitFor();await page.locator('.tracked-effect summary').click();
    await page.locator('.tracked-effect input[name=color]').fill('#ff00ff');
    await page.locator('.tracked-effect input[name=padding]').fill('0');
    const savedEffect=page.waitForResponse(r=>r.url().endsWith(`/object-tracks/${objectId}/edit`) && r.request().method()==='POST');
    await page.locator('.tracked-effect').getByRole('button',{name:'Apply effect changes',exact:true}).click();
    const saveResponse=await savedEffect;assert.ok(saveResponse.ok(),await saveResponse.text());
    await page.waitForFunction(revision=>window.OpenEdit.state.editingSelection?.expected_revision>revision,object.graph_revision);
    const context=await api('/editing-context',{selected_ids:[objectId],playhead_sec:2.5});
    assert.ok(context.object_tracks[0].data.current_frame.x>.3);assert.equal(context.object_tracks[0].data.effects[0].color,'#ff00ff');
    assert.ok(!Object.hasOwn(context.object_tracks[0].data,'frames'));assert.ok(JSON.stringify(context).length<10000);
    // Locked tracks protect all effects and manual corrections.
    await page.locator('.tracking-object').getByRole('button',{name:'Lock',exact:true}).click();
    await page.locator('.tracking-object').getByRole('button',{name:'Unlock',exact:true}).waitFor();
    assert.ok(await page.locator('[data-add-effect]').isDisabled());
    await page.locator('.tracking-object').getByRole('button',{name:'Unlock',exact:true}).click();
    await page.locator('.tracking-object').getByRole('button',{name:'Lock',exact:true}).waitFor();
    await page.locator('#media-mark-toolbar select').selectOption('off');
    await page.waitForFunction(()=>document.querySelector('#preview-freshness')?.dataset.status==='current',null,{timeout:60000}).catch(async error=>{
      const detail=await page.locator('#preview-freshness').getAttribute('title');
      const jobs=await api('/preview-chunks');
      fs.writeFileSync(path.join(artifacts,'tracking-preview-debug.json'),JSON.stringify(jobs,null,2));
      throw new Error(`${error.message}; preview: ${detail}; jobs: ${JSON.stringify(jobs)}`);
    });
    await page.waitForFunction(()=>document.querySelector('#preview-player').readyState>=2);
    const checkedPreview=await api('/preview-chunks');
    for(const chunk of checkedPreview.manifest.chunks) {
      const media=path.join(root,'object-tracking-review','.open_edit','preview_chunks',chunk.playback.current.relative_path);
      const probe=spawnSync('ffprobe',['-v','error','-show_streams','-of','json',media],{encoding:'utf8'});
      assert.equal(probe.status,0,probe.stderr);
      const video=JSON.parse(probe.stdout).streams.find(s=>s.codec_type==='video');
      const [num,den]=video.avg_frame_rate.split('/').map(Number);
      assert.equal(num/den,15);assert.equal(Number(video.nb_frames),15);
      assert.ok(Math.abs(Number(video.duration)-1)<.08,`Preview chunk duration: ${video.duration}`);
    }
    await page.screenshot({path:path.join(artifacts,'tracking-controls.png'),fullPage:true});
    // Real local export with following effect burned into the media.
    await page.locator('#btn-render-final').click();await page.locator('#export-dialog').waitFor({state:'visible'});
    const folder=path.join(root,'Local Desktop');
    await page.locator('#export-form [name=folder]').fill(folder);
    await page.locator('#export-form [name=filename]').fill('Tracked object');
    await page.locator('#export-form [name=encoder]').selectOption('cpu');
    await page.locator('#export-submit').click();
    await page.waitForFunction(()=>document.querySelector('#export-status').textContent==='Export verified and saved.',null,{timeout:120000});
    const output=path.join(folder,'Tracked object.mp4');assert.ok(fs.statSync(output).size>1000);
    const exportCopy=path.join(artifacts,'tracked-object-export.mp4');
    fs.copyFileSync(output,exportCopy);
    const report={context_bytes:JSON.stringify(context).length,frame_count:object.objects[0].data.frames.length,output:exportCopy,frames:[]};
    for(const time of [.5,2.5]) {
      const result=spawnSync('ffmpeg',['-v','error','-ss',String(time),'-i',output,'-frames:v','1','-vf','scale=320:180','-f','rawvideo','-pix_fmt','rgb24','-']);
      assert.equal(result.status,0,result.stderr.toString()); assert.equal(result.stdout.length,320*180*3);
      const x=Math.round(20+35*time)+24,y=Math.round(65+8*Math.sin(time*2))+18,index=(y*320+x)*3;
      const color=[...result.stdout.subarray(index,index+3)],background=[...result.stdout.subarray((10*320+10)*3,(10*320+10)*3+3)];
      assert.ok(color[0]>200 && color[1]<60 && color[2]>200,`Effect failed to follow at ${time}s: ${color}`);
      assert.ok(background[0]<70 && background[1]<80 && background[2]<90,`Effect changed background: ${background}`);
      report.frames.push({time,color,background});
    }
    await page.locator('#export-dialog').getByRole('button',{name:'Close export settings'}).click();
    // The same tracked source is consumed by a sliced, full-quality preview.
    await page.locator('#quality-check-form input[name=start_sec]').fill('1');await page.locator('#quality-check-form input[name=end_sec]').fill('2');
    await page.locator('#quality-check-form').getByRole('button',{name:'Check range',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#quality-check-status').textContent==='Full-quality range verified',null,{timeout:120000});
    await page.screenshot({path:path.join(artifacts,'tracking-preview.png'),fullPage:true});
    await page.reload();await page.locator('.tracking-object').waitFor();
    assert.equal(await page.locator('.tracking-object').getAttribute('data-object-id'),objectId);
    object=await api(`/studio?kind=object_track&object_id=${objectId}&include_source=true`);
    assert.equal(object.objects[0].data.effects[0].color,'#ff00ff');assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(artifacts,'tracking-acceptance.json'),JSON.stringify(report,null,2));
    console.log('Video region, local tracking, editable following effect, locks, compact AI context, local export, sliced preview and reopen passed');
  } catch(error) {
    if(page)await page.screenshot({path:path.join(artifacts,'tracking-failure.png'),fullPage:true}).catch(()=>{});
    if(fs.existsSync(path.join(root,'server.log')))fs.copyFileSync(path.join(root,'server.log'),path.join(artifacts,'tracking-server.log'));
    const manifest=path.join(root,'object-tracking-review','.open_edit','preview_chunks','manifest.json');
    if(fs.existsSync(manifest))fs.copyFileSync(manifest,path.join(artifacts,'tracking-manifest-debug.json'));
    const jobsDb=path.join(root,'object-tracking-review','.open_edit','render_jobs.db');
    if(fs.existsSync(jobsDb)) {
      const dump=spawnSync(python,['-c','import sqlite3,json,sys; c=sqlite3.connect(sys.argv[1]); c.row_factory=sqlite3.Row; print(json.dumps([dict(r) for r in c.execute("select * from render_jobs")],indent=2))',jobsDb],{encoding:'utf8'});
      if(dump.status===0)fs.writeFileSync(path.join(artifacts,'tracking-render-jobs-debug.json'),dump.stdout);
    }
    throw error;
  } finally {await browser?.close();server?.kill();fs.rmSync(root,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exit(1);});
