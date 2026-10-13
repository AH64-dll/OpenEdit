"""Client accepts checked local playback before background work completes."""
import json
import subprocess
from pathlib import Path


def test_playhead_preview_is_usable_before_full_timeline_and_stale_work_cannot_replace_it(tmp_path):
    static = (Path(__file__).resolve().parents[1] / 'open_edit/serve/static').as_uri()
    script = tmp_path / 'priority.cjs'
    script.write_text('const STATIC = ' + json.dumps(static) + r""";
const assert = require('node:assert/strict');
(async () => {
  const label={dataset:{},textContent:''};let loaded,release;
  const player={src:'',paused:true,style:{},getAttribute(){return this.src},
    addEventListener(name,fn){if(name==='loadedmetadata')loaded=fn},
    load(){if(loaded)queueMicrotask(loaded)},pause(){this.paused=true},
    removeAttribute(){this.src=''},play(){this.paused=false;return Promise.resolve()}};
  globalThis.document={addEventListener(){},querySelector(id){return id==='#preview-player'?player:id==='#preview-freshness'?label:null}};
  const {state}=await import(STATIC+'/js/state.js');
  const {observePreview}=await import(STATIC+'/js/preview.js');
  Object.assign(state,{currentProjectId:'p',currentProjectState:{graph_revision:1,
    timeline:{total_duration_s:100},timeline_full:{duration_sec:100}},
    capabilities:{timeline:true},autoPreview:true,playheadSec:0});
  const chunks=Array.from({length:50},(_,i)=>({start_sec:i*2,end_sec:(i+1)*2,playback:{status:'red'}}));
  const manifest={duration_sec:100,graph_revision:1,chunks};const posts=[];
  const green=c=>{c.playback={status:'green',current:{url:`/chunk${c.start_sec}.mp4`,artifact_id:String(c.start_sec)}}};
  globalThis.fetch=async(url,options)=>{
    let result;
    if(url.endsWith('/preview-chunks'))result={manifest};
    else if(url.endsWith('/cancel'))result={status:'cancelled'};
    else if(url.endsWith('/render')){
      const body=JSON.parse(options.body);posts.push(body);
      if(body.ranges.length){for(const c of chunks)if(c.start_sec<body.ranges[0].end_sec)green(c);result={job_id:'focus',status:'succeeded'}}
      else {await new Promise(resolve=>release=resolve);chunks.forEach(green);result={job_id:'background',status:'succeeded'}}
    }else throw new Error('Unexpected request '+url);
    return {ok:true,json:async()=>result};
  };
  observePreview(true);
  for(let i=0;i<300&&!release;i++)await new Promise(resolve=>setTimeout(resolve,10));
  assert.ok(release,'Background fill never started');
  assert.ok(posts[0].ranges.length,'First request rendered the whole timeline');
  assert.ok(posts[0].ranges[0].end_sec<100);
  assert.equal(player.src,'/chunk0.mp4','Checked local playback waited for full render');
  assert.equal(label.dataset.status,'partial');
  assert.ok(chunks.some(c=>c.playback.status==='red'));
  state.currentProjectId=null;state.currentProjectState=null;observePreview();
  release();await new Promise(resolve=>setTimeout(resolve,30));
  assert.equal(state.previewManifest,null,'Old background work replaced a new project');
  assert.equal(player.src,'');
})().catch(error=>{console.error(error);process.exitCode=1});
""")
    result = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_frame_precision_uses_the_render_clock_including_fractional_rates(tmp_path):
    state_module = (Path(__file__).resolve().parents[1] / 'open_edit/serve/static/js/state.js').as_uri()
    script = tmp_path / 'frames.cjs'
    script.write_text('const url=' + json.dumps(state_module) + r""";
const assert=require('node:assert/strict');
(async()=>{
  const {state,timelineFrameSeconds}=await import(url);
  state.currentProjectState={assets:[{fps:24}]};
  assert.equal(timelineFrameSeconds(),1/24);
  state.previewManifest={fps_num:30000,fps_den:1001};
  assert.equal(timelineFrameSeconds(),1001/30000);
  state.previewManifest={fps_num:48,fps_den:1};
  assert.equal(timelineFrameSeconds(),1/48);
})().catch(e=>{console.error(e);process.exitCode=1});
""")
    result = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
